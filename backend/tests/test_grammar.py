from pathlib import Path

from backend.app.grammar import GrammarAnalyzer
from backend.app.ollama_client import response_is_repetitive
from backend.app.prompts import build_system_prompt
from backend.app.output import polish_model_response
from backend.app.rag import chunk_text, normalize_georgian_text
from backend.app.routing import (
    is_greeting,
    is_grammar_question,
    is_identity_question,
    is_language_learning_question,
    should_analyze_grammar,
    should_use_retrieval,
)
from backend.app.verified_answers import (
    build_verified_answer,
    verified_general_answer,
)


def analyzer() -> GrammarAnalyzer:
    return GrammarAnalyzer(Path("missing-model.joblib"))


def test_common_spelling_correction() -> None:
    result = analyzer().analyze("რათქმაუნდა, ამას ავღნიშნავ.")
    assert result["label"] == "error"
    assert result["corrected"] == "რა თქმა უნდა, ამას აღვნიშნავ."


def test_punctuation_spacing() -> None:
    result = analyzer().analyze("გამარჯობა ,როგორ ხარ?")
    assert result["corrected"] == "გამარჯობა, როგორ ხარ?"
    assert len(result["issues"]) == 2


def test_normalization_and_chunking() -> None:
    text = ("ქართული   ტექსტი. " * 120).strip()
    normalized = normalize_georgian_text(text)
    chunks = chunk_text(normalized, size=240, overlap=40)
    assert "  " not in normalized
    assert len(chunks) > 1
    assert all(chunk for chunk in chunks)


def test_greeting_does_not_trigger_retrieval() -> None:
    assert is_greeting("სალამი")
    assert is_greeting("გამარჯობა, როგორ ხარ?")
    assert not should_use_retrieval("სალამი", "grammar")
    assert should_use_retrieval("რა არის არსებითი სახელი?", "learn")


def test_repetition_guard() -> None:
    assert response_is_repetitive("სიტყვა " * 12)
    assert not response_is_repetitive(
        "ქართული ენა მდიდარია და მისი სწავლა ყოველდღიურ პრაქტიკას მოითხოვს."
    )


def test_identity_routing_and_output_polishing() -> None:
    assert is_identity_question("შენ ვინხარ?")
    assert is_identity_question("რა არის შენი დავალება?")
    assert not should_use_retrieval("შენ ვინ ხარ?", "grammar")
    result = polish_model_response(
        "**მე გურამი ვარ** 😊 ვინხარ?",
        analyzer(),
    )
    assert result == "მე გურამი ვარ ვინ ხარ?"
    assert (
        polish_model_response("ყველაზე დიდი მთა მთა ევერესტია.", analyzer())
        == "ყველაზე დიდი მთა ევერესტია."
    )
    assert (
        polish_model_response(
            "ევერესტი ყველაზე მაღალი მთაა. [წყარო 1]",
            analyzer(),
            allow_source_markers=False,
        )
        == "ევერესტი ყველაზე მაღალი მთაა."
    )
    technical = polish_model_response(
        "ფორმულაა 2 * 3 = 6. მისამართია https://example.com/a:b. "
        "კოდი: `const value={a:1};`",
        analyzer(),
    )
    assert "2 * 3 = 6" in technical
    assert "https://example.com/a:b" in technical
    assert "`const value={a:1};`" in technical


def test_verified_grammar_answer() -> None:
    contexts = [
        {
            "title": "არსებითი სახელი",
            "text": "არსებითი სახელი აღნიშნავს საგანს და პასუხობს კითხვებს: ვინ? რა?",
            "genre": "გრამატიკა",
        }
    ]
    answer = build_verified_answer("learn", "რა არის არსებითი სახელი?", contexts, None)
    assert answer is not None
    assert "ვინ? რა?" in answer


def test_general_question_does_not_trigger_grammar_answer() -> None:
    question = "რომელია ყველაზე დიდი მთა?"
    misleading_context = [
        {
            "title": "მრავლობითი რიცხვი",
            "text": "თანამედროვე ქართულში მრავლობითის რამდენიმე ფორმაა.",
            "genre": "გრამატიკა",
        }
    ]

    assert not is_grammar_question(question)
    assert not is_grammar_question("რომელია ყველაზე დიდი რიცხვი?")
    assert not should_use_retrieval(question, "learn")
    assert not should_use_retrieval(question, "grammar")
    assert not should_analyze_grammar(question)
    assert not is_language_learning_question(question)
    assert "ევერესტია" in (verified_general_answer(question) or "")
    assert (
        build_verified_answer(
            "learn",
            question,
            misleading_context,
            None,
        )
        is None
    )


def test_ambiguous_largest_river_answer_uses_explicit_criteria() -> None:
    answer = verified_general_answer("რომელია ყველაზე დიდი მდინარე?")

    assert answer is not None
    assert "ამაზონი" in answer
    assert "ნილოსს" in answer
    assert "კრიტერიუმზეა დამოკიდებული" in answer
    assert "არაგვი" not in answer


def test_general_mode_accepts_questions_from_any_topic() -> None:
    prompt = build_system_prompt("learn", [], None)

    assert "ზოგადი AI" in prompt
    assert "ნებისმიერ შეკითხვას" in prompt
    assert "ამ თემებით შეზღუდული არ ხარ" in prompt
    assert "კითხვის ქართული ენა არ ნიშნავს" in prompt
    assert "ძირითად სფეროს არ ეხება" not in prompt


def test_specialized_modes_are_not_hard_topic_limits() -> None:
    grammar_prompt = " ".join(
        build_system_prompt("grammar", [], None).split()
    )
    literature_prompt = " ".join(
        build_system_prompt("literature", [], None).split()
    )

    assert "თუ შეკითხვა გრამატიკას არ ეხება" in grammar_prompt
    assert "თუ შეკითხვა ლიტერატურას არ ეხება" in literature_prompt


def test_grammar_intent_still_uses_verified_material() -> None:
    question = "რა არის მრავლობითი რიცხვი?"
    assert is_grammar_question(question)
    assert should_use_retrieval(question, "learn")
    assert should_analyze_grammar("გამისწორე: მე სკოლაში წავალ.")
    assert is_language_learning_question(
        "როგორ ვისწავლო ქართული ენა?"
    )
