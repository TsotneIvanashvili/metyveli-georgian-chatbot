import json
from contextlib import asynccontextmanager

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    status as http_status,
)
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .auth import (
    AuthResponse,
    AuthUser,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    LoginRequest,
    RegisterRequest,
    auth_store,
    bearer_scheme,
    require_user,
)
from .config import get_settings
from .grammar import GrammarAnalyzer
from .ollama_client import (
    OllamaClient,
    OllamaDegenerateResponseError,
    OllamaUnavailableError,
)
from .output import polish_model_response
from .prompts import build_system_prompt
from .rag import KnowledgeBase
from .routing import (
    is_greeting,
    is_grammar_question,
    is_identity_question,
    is_language_learning_question,
    should_analyze_grammar,
    should_use_retrieval,
)
from .schemas import ChatRequest, GrammarRequest, LibrarySearchRequest
from .verified_answers import (
    GRAMMAR_GENRES,
    LITERATURE_GENRES,
    build_verified_answer,
    verified_general_answer,
)


settings = get_settings()
knowledge_base = KnowledgeBase(settings.knowledge_base_path)
grammar_analyzer = GrammarAnalyzer(settings.grammar_model_path)
ollama = OllamaClient(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    auth_store.initialize()
    knowledge_base.load()
    grammar_analyzer.load()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=(
        None
        if settings.is_production
        else r"^https?://(?:localhost|127\.0\.0\.1)(?::\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/")
async def root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }


@app.get("/api/status")
async def status() -> dict:
    ollama_status = await ollama.status()
    return {
        "api": "online",
        "ollama": ollama_status,
        "knowledge_base": {
            "ready": knowledge_base.ready,
            "chunks": len(knowledge_base.records),
        },
        "grammar_model": {
            "ready": grammar_analyzer.model_ready,
            "fallback": "rules",
        },
    }


@app.post(
    "/api/auth/register",
    response_model=AuthResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def register(payload: RegisterRequest) -> AuthResponse:
    try:
        user, token = auth_store.register(
            payload.name,
            payload.email,
            payload.password,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="ამ ელფოსტით ანგარიში უკვე არსებობს.",
        ) from exc
    return AuthResponse(access_token=token, user=AuthUser(**user))


@app.post("/api/auth/login", response_model=AuthResponse)
async def login(payload: LoginRequest) -> AuthResponse:
    try:
        user, token = auth_store.authenticate(
            payload.email,
            payload.password,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="ელფოსტა ან პაროლი არასწორია.",
        ) from exc
    return AuthResponse(access_token=token, user=AuthUser(**user))


@app.get("/api/auth/me", response_model=AuthUser)
async def current_user(
    user: dict = Depends(require_user),
) -> AuthUser:
    return AuthUser(**user)


@app.post(
    "/api/auth/logout",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    _: dict = Depends(require_user),
) -> None:
    auth_store.logout(credentials.credentials)


@app.post("/api/grammar/check")
async def grammar_check(
    payload: GrammarRequest,
    _: dict = Depends(require_user),
) -> dict:
    return grammar_analyzer.analyze(payload.text)


@app.post("/api/library/search")
async def library_search(
    payload: LibrarySearchRequest,
    _: dict = Depends(require_user),
) -> dict:
    results = knowledge_base.search(
        payload.query,
        limit=payload.limit,
        min_score=settings.rag_min_score,
    )
    return {"query": payload.query, "count": len(results), "results": results}


@app.post("/api/chat")
async def chat(
    payload: ChatRequest,
    request: Request,
    _: dict = Depends(require_user),
) -> StreamingResponse:
    greeting = is_greeting(payload.message)
    identity_question = is_identity_question(payload.message)
    allowed_genres = (
        LITERATURE_GENRES
        if payload.mode == "literature"
        else GRAMMAR_GENRES
    )
    contexts = (
        knowledge_base.search(
            payload.message,
            limit=settings.rag_top_k,
            min_score=settings.rag_min_score,
            allowed_genres=allowed_genres,
        )
        if should_use_retrieval(payload.message, payload.mode)
        else []
    )
    grammar_result = (
        grammar_analyzer.analyze(payload.message)
        if (
            payload.mode == "grammar"
            and not greeting
            and not identity_question
            and should_analyze_grammar(payload.message)
        )
        else None
    )
    grammar_summary = (
        grammar_analyzer.prompt_summary(payload.message)
        if grammar_result is not None
        else None
    )
    verified_answer = build_verified_answer(
        payload.mode,
        payload.message,
        contexts,
        grammar_result,
    )
    has_grammar_intent = is_grammar_question(payload.message) or (
        grammar_result is not None
    )
    has_learning_intent = is_language_learning_question(payload.message)
    if not (has_grammar_intent or has_learning_intent):
        has_learning_intent = any(
            is_grammar_question(item.content)
            or is_language_learning_question(item.content)
            for item in payload.history[-4:]
        )
    safe_general_answer = None
    if payload.mode in {"learn", "grammar"} and not (
        has_grammar_intent or has_learning_intent
    ):
        safe_general_answer = verified_general_answer(payload.message)
    prompt_mode = (
        "learn"
        if payload.mode == "grammar" and not has_grammar_intent
        else payload.mode
    )
    system_prompt = build_system_prompt(
        prompt_mode,
        contexts,
        grammar_summary=grammar_summary,
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]
    messages.extend(
        {"role": item.role, "content": item.content}
        for item in payload.history[-12:]
    )
    messages.append({"role": "user", "content": payload.message})

    async def event_stream():
        public_sources = [
            {
                key: value
                for key, value in item.items()
                if key != "text"
            }
            for item in contexts
        ]
        yield sse_event("sources", {"sources": public_sources})
        if grammar_summary:
            yield sse_event(
                "analysis",
                grammar_result or {},
            )
        if greeting:
            yield sse_event(
                "token",
                {
                    "content": (
                        "გამარჯობა! რით შემიძლია დაგეხმარო? შეგიძლია "
                        "ნებისმიერ თემაზე მკითხო — პასუხს ქართულად გაგცემ."
                    )
                },
            )
            yield sse_event("done", {"ok": True})
            return
        if identity_question:
            yield sse_event(
                "token",
                {
                    "content": (
                        "მე ვარ „მეტყველი“, ქართულად მოსაუბრე ზოგადი AI "
                        "ასისტენტი. შემიძლია ნებისმიერ თემაზე დასმულ შეკითხვას "
                        "ვუპასუხო, ხოლო ქართული ენა, გრამატიკა და ლიტერატურა "
                        "ჩემი დამატებითი სპეციალიზაციაა. პასუხებისთვის ვიყენებ "
                        "ლოკალურ Qwen3:8b მოდელს და საჭიროებისას წყაროებზე "
                        "დაფუძნებულ ცოდნის ბაზას."
                    )
                },
            )
            yield sse_event("done", {"ok": True})
            return
        if safe_general_answer:
            yield sse_event(
                "token",
                {"content": safe_general_answer},
            )
            yield sse_event("done", {"ok": True})
            return
        if verified_answer:
            yield sse_event("token", {"content": verified_answer})
            yield sse_event("done", {"ok": True})
            return
        try:
            generated_parts: list[str] = []
            client_disconnected = False
            async for token in ollama.stream_chat(messages):
                if await request.is_disconnected():
                    client_disconnected = True
                    break
                generated_parts.append(token)
            if client_disconnected:
                return
            if generated_parts:
                polished = polish_model_response(
                    "".join(generated_parts),
                    grammar_analyzer,
                    allow_source_markers=bool(contexts),
                )
                if polished:
                    yield sse_event("token", {"content": polished})
                else:
                    yield sse_event(
                        "error",
                        {
                            "message": (
                                "მოდელმა ცარიელი პასუხი დააბრუნა. "
                                "სცადეთ კითხვა თავიდან."
                            )
                        },
                    )
            else:
                yield sse_event(
                    "error",
                    {
                        "message": (
                            "მოდელმა პასუხი ვერ შექმნა. "
                            "სცადეთ კითხვა თავიდან."
                        )
                    },
                )
            yield sse_event("done", {"ok": True})
        except OllamaDegenerateResponseError as exc:
            yield sse_event(
                "error",
                {
                    "message": (
                        "მოდელმა პასუხის გამეორება დაიწყო და პასუხი "
                        "ავტომატურად შეჩერდა. სცადეთ კითხვა თავიდან."
                    ),
                    "detail": str(exc),
                },
            )
        except OllamaUnavailableError as exc:
            yield sse_event(
                "error",
                {
                    "message": (
                        "Ollama-სთან დაკავშირება ვერ მოხერხდა. "
                        "შეამოწმეთ, რომ Ollama გაშვებულია და qwen3:8b დაყენებულია."
                    ),
                    "detail": str(exc),
                },
            )
        except Exception as exc:
            yield sse_event(
                "error",
                {
                    "message": (
                        "პასუხის დამუშავებისას მოულოდნელი შეცდომა მოხდა. "
                        "სცადეთ კითხვა თავიდან."
                    ),
                    "detail": str(exc),
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
