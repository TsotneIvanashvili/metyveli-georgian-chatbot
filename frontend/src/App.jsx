import {
  ArrowClockwise,
  ArrowUp,
  BookOpenText,
  Books,
  ChatCircleDots,
  CheckCircle,
  ClockCounterClockwise,
  Copy,
  Database,
  DownloadSimple,
  EnvelopeSimple,
  GearSix,
  GraduationCap,
  House,
  List,
  LockKey,
  MagnifyingGlass,
  Moon,
  Plus,
  Quotes,
  ShieldCheck,
  SignIn,
  SignOut,
  Sparkle,
  Stop,
  Sun,
  TextAa,
  Trash,
  UserCircle,
  UserPlus,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");
const CHAT_STORAGE_KEY = "metyveli-conversations-v1";
const PROFILE_STORAGE_KEY = "metyveli-profile-v1";
const THEME_STORAGE_KEY = "metyveli-theme-v2";
const AUTH_STORAGE_KEY = "metyveli-auth-v1";

const MODES = [
  {
    id: "learn",
    label: "ზოგადი ასისტენტი",
    shortLabel: "ზოგადი",
    headline: "ნებისმიერი საკითხის ახსნა",
    description: "პასუხები ნებისმიერ თემაზე ქართულად",
    icon: GraduationCap,
    prompts: [
      "მარტივად ამიხსენი, როგორ მუშაობს ხელოვნური ინტელექტი",
      "შემიდგინე ერთი კვირის სასწავლო გეგმა",
      "მომიყევი საინტერესო ფაქტი საქართველოს შესახებ",
    ],
  },
  {
    id: "grammar",
    label: "გრამატიკა",
    shortLabel: "გრამატიკა",
    headline: "ტექსტის გამართვა",
    description: "ტექსტის გასწორება და წესების ახსნა",
    icon: TextAa,
    prompts: [
      "გამისწორე: რათქმაუნდა ,ამას ავღნიშნავ.",
      "სად უნდა დავსვა მძიმე ამ წინადადებაში?",
      "შეამოწმე ტექსტი და თითოეული ცვლილება ამიხსენი",
    ],
  },
  {
    id: "literature",
    label: "ლიტერატურა",
    shortLabel: "ლიტერატურა",
    headline: "ავტორები და ნაწარმოებები",
    description: "ავტორები, ნაწარმოებები და ანალიზი",
    icon: BookOpenText,
    prompts: [
      "მომიყევი ვაჟა-ფშაველას პოეზიის მთავარ თემებზე",
      "როგორ დავახასიათო მოთხრობის პერსონაჟი?",
      "ამიხსენი მეტაფორა და შედარება ლიტერატურაში",
    ],
  },
];

const INITIAL_STATUS = {
  loading: true,
  apiOnline: false,
  ollamaOnline: false,
  modelAvailable: false,
  knowledgeReady: false,
  chunks: 0,
};

const DEFAULT_PROFILE = {
  name: "სტუმარი",
  level: "დამწყები",
  goal: "სასარგებლო პასუხების მიღება ქართულად",
};

function readStoredValue(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem(key));
    return value ?? fallback;
  } catch {
    return fallback;
  }
}

function readStoredString(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function writeStoredValue(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

function writeStoredString(key, value) {
  try {
    localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

function removeStoredValue(key) {
  try {
    localStorage.removeItem(key);
  } catch {
    // The in-memory session remains usable when browser storage is unavailable.
  }
}

function createId() {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  const random = globalThis.crypto?.getRandomValues
    ? globalThis.crypto.getRandomValues(new Uint32Array(2)).join("-")
    : Math.random().toString(36).slice(2);
  return `${Date.now()}-${random}`;
}

function normalizeStoredProfile(value, fallbackName) {
  const profile = value && typeof value === "object" ? value : {};
  const allowedLevels = new Set([
    "დამწყები",
    "საშუალო",
    "მოწინავე",
    "მშობლიური",
  ]);
  return {
    name:
      typeof profile.name === "string" && profile.name.trim()
        ? profile.name.trim().slice(0, 40)
        : fallbackName,
    level: allowedLevels.has(profile.level) ? profile.level : "დამწყები",
    goal:
      typeof profile.goal === "string"
        ? profile.goal.trim().slice(0, 100)
        : DEFAULT_PROFILE.goal,
  };
}

function normalizeStoredConversations(value) {
  if (!Array.isArray(value)) return [];
  const validModes = new Set(MODES.map((mode) => mode.id));
  return value
    .filter(
      (conversation) =>
        conversation &&
        typeof conversation === "object" &&
        Array.isArray(conversation.messages),
    )
    .slice(0, 250)
    .map((conversation) => {
      const messages = conversation.messages
        .filter(
          (message) =>
            message &&
            ["user", "assistant"].includes(message.role) &&
            typeof message.content === "string",
        )
        .slice(-200)
        .map((message) => ({
          ...message,
          id:
            typeof message.id === "string" && message.id
              ? message.id
              : createId(),
          content: message.content.slice(0, 12_000),
          error: Boolean(message.error),
          stopped: Boolean(message.stopped),
          sources: Array.isArray(message.sources) ? message.sources : [],
        }));
      const firstUserMessage = messages.find(
        (message) => message.role === "user",
      );
      const fallbackTitle = firstUserMessage
        ? createConversationTitle(firstUserMessage.content)
        : "შენახული საუბარი";
      const now = new Date().toISOString();
      return {
        ...conversation,
        id:
          typeof conversation.id === "string" && conversation.id
            ? conversation.id
            : createId(),
        title:
          typeof conversation.title === "string" &&
          conversation.title.trim()
            ? conversation.title.trim().slice(0, 80)
            : fallbackTitle,
        mode: validModes.has(conversation.mode)
          ? conversation.mode
          : "learn",
        createdAt:
          typeof conversation.createdAt === "string"
            ? conversation.createdAt
            : now,
        updatedAt:
          typeof conversation.updatedAt === "string"
            ? conversation.updatedAt
            : now,
        messages,
      };
    });
}

function safeExternalUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 20_000) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timeout);
  }
}

function parseSseBlock(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

function apiErrorMessage(payload, fallback) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail) && payload.detail[0]?.msg) {
    return payload.detail[0].msg.replace(/^Value error,\s*/i, "");
  }
  return fallback;
}

function createConversationTitle(content) {
  const normalized = content.replace(/\s+/g, " ").trim();
  return normalized.length > 46 ? `${normalized.slice(0, 46)}…` : normalized;
}

function formatShortDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ka-GE", {
    day: "numeric",
    month: "short",
  }).format(date);
}

function getHistoryGroup(value) {
  const date = new Date(value);
  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const dateStart = new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
  );
  const days = Math.floor((todayStart - dateStart) / 86_400_000);
  if (days <= 0) return "დღეს";
  if (days === 1) return "გუშინ";
  if (days < 7) return "ბოლო 7 დღე";
  return "უფრო ადრე";
}

function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark" aria-hidden="true">
        მ
      </span>
      <span className="brand-copy">
        <strong>მეტყველი</strong>
        <small>ქართულენოვანი AI ასისტენტი</small>
      </span>
    </div>
  );
}

function SponsorMark() {
  return (
    <div className="sponsor" aria-label="თიბისი ტექნოლოგიური სკოლა">
      <span className="sponsor-logo">
        <img src="/tbc-mark.svg" alt="" width="18" height="18" />
      </span>
      <span>
        <strong>თიბისი</strong>
        <small>ტექნოლოგიური სკოლა</small>
      </span>
    </div>
  );
}

function ThemeButton({ theme, onToggle }) {
  const Icon = theme === "dark" ? Sun : Moon;
  return (
    <button
      className="icon-button"
      type="button"
      onClick={onToggle}
      aria-label={theme === "dark" ? "ღია თემაზე გადასვლა" : "მუქ თემაზე გადასვლა"}
      title={theme === "dark" ? "ღია თემა" : "მუქი თემა"}
    >
      <Icon size={19} />
    </button>
  );
}

function ConnectionStatus({ status, onRetry }) {
  const connected =
    status.apiOnline && status.ollamaOnline && status.modelAvailable;
  const label = status.loading
    ? "ვამოწმებ"
    : connected
      ? "Qwen3 მზადაა"
      : "კავშირის პრობლემა";

  return (
    <button
      className={`connection ${connected ? "is-online" : "is-offline"}`}
      type="button"
      onClick={onRetry}
      title="კავშირის სტატუსის განახლება"
    >
      <span className="status-dot" aria-hidden="true" />
      <span>{label}</span>
      <ArrowClockwise size={14} />
    </button>
  );
}

function AuthScreen({ onAuthenticated, theme, onToggleTheme }) {
  const [mode, setMode] = useState("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isRegister = mode === "register";

  function changeMode(nextMode) {
    setMode(nextMode);
    setError("");
    setPassword("");
    setConfirmPassword("");
  }

  async function submit(event) {
    event.preventDefault();
    if (submitting) return;
    if (isRegister && password !== confirmPassword) {
      setError("პაროლები ერთმანეთს არ ემთხვევა.");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const response = await fetchWithTimeout(
        `${API_BASE}/api/auth/${isRegister ? "register" : "login"}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(
            isRegister ? { name, email, password } : { email, password },
          ),
        },
        20_000,
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(
          apiErrorMessage(
            data,
            isRegister
              ? "რეგისტრაცია ვერ დასრულდა."
              : "ავტორიზაცია ვერ შესრულდა.",
          ),
        );
      }
      onAuthenticated(data);
    } catch (requestError) {
      setError(
        requestError.name === "AbortError"
          ? "სერვერმა დროულად არ უპასუხა. სცადე თავიდან."
          : requestError instanceof TypeError
          ? "სერვერთან დაკავშირება ვერ მოხერხდა."
          : requestError.message,
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-story">
        <div className="auth-story-top">
          <Brand />
          <SponsorMark />
        </div>

        <div className="auth-story-copy">
          <span className="auth-story-mark" aria-hidden="true">
            ა
          </span>
          <h1>ნებისმიერი კითხვა — ერთი ქართული საუბარი.</h1>
          <p>
            ზოგადი AI ასისტენტი, რომელიც ქართულად გიპასუხებს და დამატებით
            გრამატიკაში, ენის პრაქტიკასა და ლიტერატურაშიც დაგეხმარება.
          </p>
        </div>

        <div className="auth-benefits" aria-label="მეტყველის შესაძლებლობები">
          <div>
            <TextAa size={20} />
            <span>
              <strong>გასაგები ახსნა</strong>
              <small>რთული წესები მარტივი ქართულით</small>
            </span>
          </div>
          <div>
            <Books size={20} />
            <span>
              <strong>ქართული წყაროები</strong>
              <small>ზოგადი ცოდნა და სასწავლო მასალა</small>
            </span>
          </div>
          <div>
            <ClockCounterClockwise size={20} />
            <span>
              <strong>შენახული პროგრესი</strong>
              <small>დაუბრუნდი ნებისმიერ წინა საუბარს</small>
            </span>
          </div>
        </div>

        <div className="auth-letter-field" aria-hidden="true">
          <span>ა</span>
          <span>ბ</span>
          <span>გ</span>
        </div>
      </section>

      <section className="auth-access">
        <div className="auth-access-top">
          <div className="auth-mobile-brand">
            <Brand />
          </div>
          <ThemeButton theme={theme} onToggle={onToggleTheme} />
        </div>

        <div className="auth-form-wrap">
          <div className="auth-tabs" role="group" aria-label="ანგარიშის რეჟიმი">
            <button
              type="button"
              aria-pressed={!isRegister}
              className={!isRegister ? "is-active" : ""}
              onClick={() => changeMode("login")}
            >
              შესვლა
            </button>
            <button
              type="button"
              aria-pressed={isRegister}
              className={isRegister ? "is-active" : ""}
              onClick={() => changeMode("register")}
            >
              რეგისტრაცია
            </button>
          </div>

          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              className="auth-form-stage"
              key={mode}
              initial={{ opacity: 0, x: isRegister ? 10 : -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: isRegister ? -10 : 10 }}
              transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="auth-heading">
                <span className="auth-heading-icon">
                  {isRegister ? <UserPlus size={21} /> : <SignIn size={21} />}
                </span>
                <h2>
                  {isRegister ? "შექმენი შენი სივრცე" : "კეთილი იყოს დაბრუნება"}
                </h2>
                <p>
                  {isRegister
                    ? "შეინახე საუბრები და ნებისმიერ თემაზე ქართულად იკითხე."
                    : "შედი ანგარიშში და გააგრძელე შენახული საუბრები."}
                </p>
              </div>

              <form className="auth-form" onSubmit={submit}>
                {isRegister && (
                  <label>
                    <span>სახელი</span>
                    <div className="auth-input">
                      <UserCircle size={19} />
                      <input
                        value={name}
                        onChange={(event) => setName(event.target.value)}
                        minLength={2}
                        maxLength={60}
                        autoComplete="name"
                        placeholder="როგორ მოგმართოთ?"
                        required
                      />
                    </div>
                  </label>
                )}

                <label>
                  <span>ელფოსტა</span>
                  <div className="auth-input">
                    <EnvelopeSimple size={19} />
                    <input
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      maxLength={254}
                      autoComplete="email"
                      placeholder="name@example.com"
                      required
                    />
                  </div>
                </label>

                <label>
                  <span>პაროლი</span>
                  <div className="auth-input">
                    <LockKey size={19} />
                    <input
                      type="password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      minLength={isRegister ? 8 : 1}
                      maxLength={128}
                      autoComplete={
                        isRegister ? "new-password" : "current-password"
                      }
                      placeholder={
                        isRegister ? "მინიმუმ 8 სიმბოლო" : "შენი პაროლი"
                      }
                      required
                    />
                  </div>
                </label>

                {isRegister && (
                  <label>
                    <span>გაიმეორე პაროლი</span>
                    <div className="auth-input">
                      <ShieldCheck size={19} />
                      <input
                        type="password"
                        value={confirmPassword}
                        onChange={(event) =>
                          setConfirmPassword(event.target.value)
                        }
                        minLength={8}
                        maxLength={128}
                        autoComplete="new-password"
                        placeholder="პაროლი კიდევ ერთხელ"
                        required
                      />
                    </div>
                  </label>
                )}

                {error && (
                  <div className="auth-error" role="alert">
                    <WarningCircle size={18} />
                    <span>{error}</span>
                  </div>
                )}

                <button
                  className="auth-submit"
                  type="submit"
                  disabled={submitting}
                >
                  {submitting ? (
                    <span className="auth-submit-loading">
                      <span />
                      <span />
                      <span />
                      <span className="sr-only">მიმდინარეობს</span>
                    </span>
                  ) : (
                    <>
                      {isRegister ? <UserPlus size={19} /> : <SignIn size={19} />}
                      {isRegister ? "ანგარიშის შექმნა" : "ანგარიშში შესვლა"}
                    </>
                  )}
                </button>
              </form>

              <p className="auth-switch-copy">
                {isRegister ? "უკვე გაქვს ანგარიში?" : "ჯერ არ გაქვს ანგარიში?"}
                <button
                  type="button"
                  onClick={() =>
                    changeMode(isRegister ? "login" : "register")
                  }
                >
                  {isRegister ? "შესვლა" : "დარეგისტრირდი"}
                </button>
              </p>
            </motion.div>
          </AnimatePresence>
        </div>

        <p className="auth-privacy">
          <ShieldCheck size={15} />
          პაროლი დაცულია უსაფრთხო ჰეშირებით და ღია ტექსტად არ ინახება.
        </p>
      </section>
    </main>
  );
}

function SessionLoading() {
  return (
    <main className="session-loading">
      <Brand />
      <span className="session-loading-line" aria-hidden="true" />
      <p>სესია მოწმდება…</p>
    </main>
  );
}

function Sidebar({
  activeConversationId,
  activeView,
  conversations,
  mobileOpen,
  onClose,
  onDeleteConversation,
  onNewChat,
  onOpenHistory,
  onOpenConversation,
  onOpenProfile,
  search,
  setSearch,
}) {
  const drawerRef = useRef(null);
  const previousFocusRef = useRef(null);
  const groupedHistory = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("ka-GE");
    const filtered = conversations.filter((conversation) =>
      conversation.title.toLocaleLowerCase("ka-GE").includes(query),
    );
    return filtered.reduce((groups, conversation) => {
      const label = getHistoryGroup(conversation.updatedAt);
      const group = groups.find((item) => item.label === label);
      if (group) group.items.push(conversation);
      else groups.push({ label, items: [conversation] });
      return groups;
    }, []);
  }, [conversations, search]);

  useEffect(() => {
    if (!mobileOpen) return undefined;
    previousFocusRef.current = document.activeElement;
    const focusTimer = window.setTimeout(() => {
      drawerRef.current?.querySelector('input[type="search"]')?.focus();
    }, 0);
    const handleKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", handleKeyDown);
      previousFocusRef.current?.focus?.();
    };
  }, [mobileOpen, onClose]);

  return (
    <>
      <AnimatePresence>
        {mobileOpen && (
          <motion.button
            className="mobile-scrim"
            aria-label="ისტორიის დახურვა"
            type="button"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
        )}
      </AnimatePresence>

      <aside className="sidebar" aria-label="მთავარი ნავიგაცია">
        <button
          className="rail-brand"
          type="button"
          onClick={onNewChat}
          aria-label="მეტყველი — ახალი საუბარი"
          title="მეტყველი"
        >
          მ
        </button>

        <nav className="rail-nav">
          <button
            type="button"
            className={activeView === "chat" ? "is-active" : ""}
            onClick={onNewChat}
            aria-label="მთავარი"
            title="მთავარი"
          >
            <House
              size={20}
              weight={activeView === "chat" ? "fill" : "regular"}
            />
          </button>
          <button
            type="button"
            onClick={onOpenHistory}
            aria-label="წინა საუბრები"
            title="წინა საუბრები"
          >
            <ChatCircleDots size={20} />
            {!!conversations.length && (
              <span className="rail-count">
                {conversations.length > 99 ? "99+" : conversations.length}
              </span>
            )}
          </button>
          <button
            type="button"
            className={activeView === "profile" ? "is-active" : ""}
            onClick={onOpenProfile}
            aria-label="პროფილი"
            title="პროფილი"
          >
            <UserCircle size={20} />
          </button>
        </nav>

        <div className="rail-bottom">
          <button
            type="button"
            onClick={onOpenProfile}
            aria-label="პარამეტრები"
            title="პარამეტრები"
          >
            <GearSix size={20} />
          </button>
          <span className="rail-tbc" title="თიბისი ტექნოლოგიური სკოლა">
            <img src="/tbc-mark.svg" alt="თიბისი" width="18" height="18" />
          </span>
        </div>
      </aside>

      <aside
        ref={drawerRef}
        className={`history-drawer ${mobileOpen ? "is-open" : ""}`}
        role="dialog"
        aria-label="წინა საუბრების ისტორია"
        aria-hidden={!mobileOpen}
        inert={!mobileOpen}
      >
        <div className="history-drawer-head">
          <div>
            <strong>შენი საუბრები</strong>
            <small>{conversations.length} შენახული ჩატი</small>
          </div>
          <button
            className="icon-button"
            type="button"
            onClick={onClose}
            aria-label="ისტორიის დახურვა"
          >
            <X size={19} />
          </button>
        </div>

        <button className="new-chat-button" type="button" onClick={onNewChat}>
          <Plus size={18} weight="bold" />
          <span>ახალი საუბარი</span>
        </button>

        <label className="history-search">
          <MagnifyingGlass size={17} aria-hidden="true" />
          <span className="sr-only">საუბრების ძიება</span>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="მოძებნე საუბარი"
          />
        </label>

        <nav className="history-list" aria-label="წინა საუბრები">
          {groupedHistory.length ? (
            groupedHistory.map((group) => (
              <section className="history-group" key={group.label}>
                <h2>{group.label}</h2>
                {group.items.map((conversation) => {
                  const mode =
                    MODES.find((item) => item.id === conversation.mode) ||
                    MODES[0];
                  const ModeIcon = mode.icon;
                  const active =
                    activeView === "chat" &&
                    activeConversationId === conversation.id;
                  return (
                    <div
                      className={`history-row ${active ? "is-active" : ""}`}
                      key={conversation.id}
                    >
                      <button
                        className="history-open"
                        type="button"
                        onClick={() => onOpenConversation(conversation.id)}
                        aria-current={active ? "page" : undefined}
                      >
                        <ModeIcon size={16} />
                        <span>
                          <strong>{conversation.title}</strong>
                          <small>
                            {mode.shortLabel} ·{" "}
                            {formatShortDate(conversation.updatedAt)}
                          </small>
                        </span>
                      </button>
                      <button
                        className="history-delete"
                        type="button"
                        onClick={() => onDeleteConversation(conversation.id)}
                        aria-label={`წაშალე საუბარი: ${conversation.title}`}
                        title="საუბრის წაშლა"
                      >
                        <Trash size={15} />
                      </button>
                    </div>
                  );
                })}
              </section>
            ))
          ) : (
            <div className="history-empty">
              <ChatCircleDots size={23} />
              <p>
                {search
                  ? "ამ სახელით საუბარი ვერ მოიძებნა."
                  : "პირველი საუბარი აქ ავტომატურად შეინახება."}
              </p>
            </div>
          )}
        </nav>
      </aside>
    </>
  );
}

function EmptyState({
  activeMode,
  onSuggestion,
  profile,
  status,
}) {
  const firstName = profile.name.trim().split(/\s+/)[0];
  const displayName =
    firstName && firstName !== "სტუმარი" ? `, ${firstName}` : "";

  return (
    <motion.section
      className="empty-state"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="welcome-copy">
        <h1>
          გამარჯობა{displayName}
          <span>რით შემიძლია დაგეხმარო?</span>
        </h1>
      </div>

      <div className="suggestion-grid" aria-label="საუბრის მიმართულებები">
        {MODES.map((mode) => {
          const Icon = mode.icon;
          const selected = mode.id === activeMode;
          return (
            <button
              className={`suggestion-card suggestion-${mode.id} ${
                selected ? "is-active" : ""
              }`}
              type="button"
              key={mode.id}
              onClick={() => onSuggestion(mode.id, mode.prompts[0])}
              aria-label={`${mode.label}: ${mode.prompts[0]}`}
            >
              <span className="suggestion-label">
                <Icon size={14} weight={selected ? "fill" : "regular"} />
                {mode.shortLabel}
              </span>
              <strong>{mode.headline}</strong>
              <small>{mode.description}</small>
            </button>
          );
        })}
      </div>

      <p className="empty-library-status">
        <ShieldCheck size={15} />
        {status.chunks
          ? `${status.chunks.toLocaleString("ka-GE")} ქართული წყარო მზადაა`
          : status.loading
            ? "ცოდნის ბაზა იტვირთება"
            : status.knowledgeReady
              ? "ცოდნის ბაზა ცარიელია"
              : "ცოდნის ბაზა მიუწვდომელია"}
      </p>
    </motion.section>
  );
}

function LoadingText() {
  return (
    <span className="thinking" role="status">
      <span />
      <span />
      <span />
      <span className="sr-only">პასუხი მზადდება</span>
    </span>
  );
}

function GrammarAnalysis({ analysis }) {
  if (!analysis) return null;
  const changed = analysis.corrected !== analysis.original;
  return (
    <div className={`grammar-result ${changed ? "has-changes" : ""}`}>
      <div className="grammar-result-title">
        {changed ? <TextAa size={18} /> : <CheckCircle size={18} />}
        <strong>
          {changed ? "ავტომატური შესწორება" : "აშკარა შეცდომა ვერ მოიძებნა"}
        </strong>
      </div>
      {changed && <p>{analysis.corrected}</p>}
      {!!analysis.issues?.length && (
        <span>{analysis.issues.length} აღმოჩენილი საკითხი</span>
      )}
    </div>
  );
}

function SourceList({ sources }) {
  const linkableSources = (sources || [])
    .map((source) => ({
      ...source,
      safeUrl: safeExternalUrl(source.source_url),
    }))
    .filter((source) => source.safeUrl);
  if (!linkableSources.length) return null;
  return (
    <div className="sources">
      <div className="sources-title">
        <Quotes size={17} />
        <strong>გამოყენებული წყაროები</strong>
      </div>
      <div className="source-links">
        {linkableSources.map((source, index) => (
          <a
            key={`${source.id}-${index}`}
            href={source.safeUrl}
            target="_blank"
            rel="noreferrer"
          >
            <span>{index + 1}</span>
            <span>
              <strong>{source.title}</strong>
              <small>
                {[source.author, source.genre].filter(Boolean).join(" / ")}
              </small>
            </span>
          </a>
        ))}
      </div>
    </div>
  );
}

function Message({ message, reduceMotion, profile }) {
  const [copyStatus, setCopyStatus] = useState("idle");
  const copyTimerRef = useRef(null);
  const isAssistant = message.role === "assistant";

  useEffect(
    () => () => {
      window.clearTimeout(copyTimerRef.current);
    },
    [],
  );

  async function copyMessage() {
    if (!message.content) return;
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard API is unavailable.");
      }
      await navigator.clipboard.writeText(message.content);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("error");
    }
    window.clearTimeout(copyTimerRef.current);
    copyTimerRef.current = window.setTimeout(
      () => setCopyStatus("idle"),
      1_800,
    );
  }

  return (
    <motion.article
      className={`message ${isAssistant ? "assistant" : "user"}`}
      initial={reduceMotion ? false : { opacity: 0, y: 7 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="message-avatar" aria-hidden="true">
        {isAssistant ? "მ" : profile.name.trim().charAt(0) || "შ"}
      </div>
      <div className="message-body">
        <div className="message-meta">
          <strong>{isAssistant ? "მეტყველი" : profile.name || "შენ"}</strong>
          {message.error && (
            <span className="message-error-label">
              <WarningCircle size={15} /> შეცდომა
            </span>
          )}
          {message.stopped && <span className="message-stopped">შეჩერებულია</span>}
        </div>
        <GrammarAnalysis analysis={message.analysis} />
        <div className={`message-content ${message.error ? "error-copy" : ""}`}>
          {message.content ? message.content : <LoadingText />}
        </div>
        {isAssistant && message.content && !message.error && (
          <button
            className="copy-button"
            type="button"
            onClick={copyMessage}
            aria-label="პასუხის კოპირება"
            aria-live="polite"
          >
            {copyStatus === "copied" ? (
              <CheckCircle size={16} />
            ) : copyStatus === "error" ? (
              <WarningCircle size={16} />
            ) : (
              <Copy size={16} />
            )}
            {copyStatus === "copied"
              ? "დაკოპირდა"
              : copyStatus === "error"
                ? "ვერ დაკოპირდა"
                : "კოპირება"}
          </button>
        )}
        <SourceList sources={message.sources} />
      </div>
    </motion.article>
  );
}

function Composer({
  focusKey,
  isStreaming,
  mode,
  onChange,
  onStop,
  onSubmit,
  value,
}) {
  const textareaRef = useRef(null);

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!isStreaming && value.trim()) onSubmit();
    }
  }

  function resize(event) {
    const element = event.currentTarget;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 176)}px`;
  }

  useEffect(() => {
    textareaRef.current?.focus();
  }, [focusKey, mode]);

  useEffect(() => {
    if (!value && textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value]);

  return (
    <div className="composer-wrap">
      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          if (!isStreaming && value.trim()) onSubmit();
        }}
      >
        <label htmlFor="chat-message" className="sr-only">
          დაწერე შეკითხვა
        </label>
        <Sparkle
          className="composer-sparkle"
          size={18}
          weight="fill"
          aria-hidden="true"
        />
        <textarea
          ref={textareaRef}
          id="chat-message"
          rows="1"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onInput={resize}
          onKeyDown={handleKeyDown}
          placeholder={
            mode === "grammar"
              ? "ჩასვი შესამოწმებელი ქართული ტექსტი"
              : mode === "literature"
                ? "ჰკითხე ქართულ ნაწარმოებს ან ავტორს"
                : "დაწერე ნებისმიერი შეკითხვა"
          }
          maxLength={4000}
        />
        <span className="composer-hint">Enter გასაგზავნად</span>
        {isStreaming ? (
          <button
            className="send-button stop"
            type="button"
            onClick={onStop}
            aria-label="პასუხის შეჩერება"
          >
            <Stop size={18} weight="fill" />
          </button>
        ) : (
          <button
            className="send-button"
            type="submit"
            disabled={!value.trim()}
            aria-label="შეკითხვის გაგზავნა"
          >
            <ArrowUp size={19} weight="bold" />
          </button>
        )}
      </form>
      <p>მეტყველი შეიძლება შეცდეს — მნიშვნელოვანი ინფორმაცია გადაამოწმე წყაროში.</p>
    </div>
  );
}

function ChatWorkspace({
  activeConversation,
  activeMode,
  input,
  isStreaming,
  onChangeMode,
  onInputChange,
  onSend,
  onSuggestion,
  onStop,
  profile,
  reduceMotion,
  status,
  bottomRef,
}) {
  const activeModeData =
    MODES.find((mode) => mode.id === activeMode) || MODES[0];
  const messages = activeConversation?.messages || [];

  return (
    <section
      className={`chat-workspace ${messages.length === 0 ? "is-empty" : ""}`}
    >
      <div className="mode-toolbar">
        <div className="mode-tabs" role="group" aria-label="საუბრის რეჟიმი">
          {MODES.map((mode) => {
            const Icon = mode.icon;
            const selected = activeMode === mode.id;
            return (
              <button
                key={mode.id}
                type="button"
                aria-pressed={selected}
                className={selected ? "is-active" : ""}
                onClick={() => onChangeMode(mode.id)}
              >
                <Icon size={17} weight={selected ? "fill" : "regular"} />
                <span>{mode.shortLabel}</span>
              </button>
            );
          })}
        </div>
        <span className="mode-description">{activeModeData.description}</span>
      </div>

      <div className="chat-scroll">
        <div className="chat-content">
          {messages.length === 0 ? (
            <EmptyState
              activeMode={activeMode}
              onSuggestion={onSuggestion}
              profile={profile}
              status={status}
            />
          ) : (
            <div className="message-list">
              {messages.map((message) => (
                <Message
                  key={message.id}
                  message={message}
                  profile={profile}
                  reduceMotion={reduceMotion}
                />
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <Composer
        focusKey={activeConversation?.id || "new"}
        value={input}
        onChange={onInputChange}
        onSubmit={() => onSend()}
        isStreaming={isStreaming}
        onStop={onStop}
        mode={activeMode}
      />
    </section>
  );
}

function ProfilePage({
  account,
  conversations,
  onBack,
  onClearHistory,
  onExportHistory,
  onLogout,
  profile,
  setProfile,
  status,
  theme,
  setTheme,
}) {
  const userMessages = conversations.reduce(
    (total, conversation) =>
      total +
      conversation.messages.filter((message) => message.role === "user").length,
    0,
  );
  const lastActivity = conversations[0]?.updatedAt;
  const connected =
    status.apiOnline && status.ollamaOnline && status.modelAvailable;

  return (
    <section className="profile-page">
      <div className="profile-intro">
        <div className="profile-large-avatar" aria-hidden="true">
          {profile.name.trim().charAt(0) || "მ"}
        </div>
        <div>
          <p>შენი პირადი სივრცე</p>
          <h1>{profile.name || "სტუმარი"}</h1>
          <span>{account.email}</span>
        </div>
        <button className="secondary-button profile-back" type="button" onClick={onBack}>
          <ChatCircleDots size={18} />
          ჩატში დაბრუნება
        </button>
      </div>

      <div className="profile-stats" aria-label="აქტივობის სტატისტიკა">
        <div>
          <ChatCircleDots size={21} />
          <span>
            <strong>{conversations.length}</strong>
            შენახული საუბარი
          </span>
        </div>
        <div>
          <TextAa size={21} />
          <span>
            <strong>{userMessages}</strong>
            დასმული შეკითხვა
          </span>
        </div>
        <div>
          <ClockCounterClockwise size={21} />
          <span>
            <strong>{lastActivity ? formatShortDate(lastActivity) : "ჯერ არა"}</strong>
            ბოლო აქტივობა
          </span>
        </div>
      </div>

      <div className="profile-layout">
        <div className="settings-section">
          <div className="section-heading">
            <div>
              <h2>პირადი პარამეტრები</h2>
              <p>მეტყველი ამ ინფორმაციას პასუხებისა და სასწავლო გამოცდილების მოსარგებად იყენებს.</p>
            </div>
            <span className="saved-label">
              <CheckCircle size={16} />
              ავტომატურად ინახება
            </span>
          </div>

          <div className="settings-form">
            <label>
              <span>სახელი</span>
              <input
                value={profile.name}
                maxLength={40}
                onChange={(event) =>
                  setProfile((current) => ({
                    ...current,
                    name: event.target.value,
                  }))
                }
                placeholder="როგორ მოგმართოთ?"
              />
            </label>
            <label>
              <span>ქართული ენის დონე</span>
              <select
                value={profile.level}
                onChange={(event) =>
                  setProfile((current) => ({
                    ...current,
                    level: event.target.value,
                  }))
                }
              >
                <option>დამწყები</option>
                <option>საშუალო</option>
                <option>მოწინავე</option>
                <option>მშობლიური</option>
              </select>
            </label>
            <label className="goal-field">
              <span>მთავარი ინტერესი</span>
              <input
                value={profile.goal}
                maxLength={100}
                onChange={(event) =>
                  setProfile((current) => ({
                    ...current,
                    goal: event.target.value,
                  }))
                }
                placeholder="მაგალითად: ტექნოლოგია და ქართული ენა"
              />
            </label>
          </div>

          <div className="theme-setting">
            <span>
              <Moon size={19} />
              ინტერფეისის თემა
            </span>
            <div
              className="segmented-control"
              role="group"
              aria-label="თემის არჩევა"
            >
              <button
                type="button"
                className={theme === "light" ? "is-active" : ""}
                onClick={() => setTheme("light")}
                aria-pressed={theme === "light"}
              >
                <Sun size={16} /> ღია
              </button>
              <button
                type="button"
                className={theme === "dark" ? "is-active" : ""}
                onClick={() => setTheme("dark")}
                aria-pressed={theme === "dark"}
              >
                <Moon size={16} /> მუქი
              </button>
            </div>
          </div>
        </div>

        <aside className="profile-side">
          <section className="system-section">
            <div className="section-heading compact">
              <div>
                <h2>სისტემის მდგომარეობა</h2>
                <p>ლოკალური AI და ცოდნის ბაზა</p>
              </div>
            </div>
            <dl className="system-list">
              <div>
                <dt>
                  <Database size={18} />
                  Qwen3 მოდელი
                </dt>
                <dd className={connected ? "positive" : "negative"}>
                  {connected ? "მზადაა" : "შესამოწმებელია"}
                </dd>
              </div>
              <div>
                <dt>
                  <Books size={18} />
                  ცოდნის ბაზა
                </dt>
                <dd>
                  {status.chunks
                    ? `${status.chunks.toLocaleString("ka-GE")} ფრაგმენტი`
                    : status.loading
                      ? "იტვირთება"
                      : status.knowledgeReady
                        ? "ცარიელია"
                        : "მიუწვდომელია"}
                </dd>
              </div>
              <div>
                <dt>
                  <ShieldCheck size={18} />
                  კონფიდენციალურობა
                </dt>
                <dd>დაცული ანგარიში</dd>
              </div>
            </dl>
          </section>

          <section className="account-section">
            <div className="section-heading compact">
              <div>
                <h2>ანგარიში</h2>
                <p>ავტორიზაცია და მიმდინარე სესია</p>
              </div>
            </div>
            <div className="account-identity">
              <span className="profile-avatar" aria-hidden="true">
                {account.name.trim().charAt(0) || "მ"}
              </span>
              <span>
                <strong>{account.name}</strong>
                <small>{account.email}</small>
              </span>
            </div>
            <button
              className="data-action danger"
              type="button"
              onClick={onLogout}
            >
              <SignOut size={18} />
              <span>
                <strong>ანგარიშიდან გასვლა</strong>
                <small>ამ მოწყობილობაზე სესიის დასრულება</small>
              </span>
            </button>
          </section>

          <section className="data-section">
            <div className="section-heading compact">
              <div>
                <h2>ჩემი მონაცემები</h2>
                <p>შეინახე ასლი ან გაასუფთავე ისტორია.</p>
              </div>
            </div>
            <button
              className="data-action"
              type="button"
              onClick={onExportHistory}
              disabled={!conversations.length}
            >
              <DownloadSimple size={18} />
              <span>
                <strong>ისტორიის ექსპორტი</strong>
                <small>JSON ფაილად ჩამოტვირთვა</small>
              </span>
            </button>
            <button
              className="data-action danger"
              type="button"
              onClick={onClearHistory}
              disabled={!conversations.length}
            >
              <Trash size={18} />
              <span>
                <strong>ისტორიის გასუფთავება</strong>
                <small>ყველა შენახული საუბრის წაშლა</small>
              </span>
            </button>
          </section>
        </aside>
      </div>
    </section>
  );
}

function AuthenticatedApp({
  onLogout,
  onSessionExpired,
  session,
  setTheme,
  theme,
}) {
  const reduceMotion = useReducedMotion();
  const chatStorageKey = `${CHAT_STORAGE_KEY}:${session.user.id}`;
  const profileStorageKey = `${PROFILE_STORAGE_KEY}:${session.user.id}`;
  const [profile, setProfile] = useState(() =>
    normalizeStoredProfile(
      readStoredValue(profileStorageKey, {}),
      session.user.name,
    ),
  );
  const [conversations, setConversations] = useState(() =>
    normalizeStoredConversations(readStoredValue(chatStorageKey, [])),
  );
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [activeMode, setActiveMode] = useState("learn");
  const [activeView, setActiveView] = useState("chat");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [status, setStatus] = useState(INITIAL_STATUS);
  const [storageWarning, setStorageWarning] = useState("");
  const abortRef = useRef(null);
  const streamRef = useRef(null);
  const bottomRef = useRef(null);
  const closeHistory = useCallback(() => setMobileOpen(false), []);
  const openHistory = useCallback(() => setMobileOpen(true), []);

  const sortedConversations = useMemo(
    () =>
      [...conversations].sort(
        (first, second) =>
          new Date(second.updatedAt).getTime() -
          new Date(first.updatedAt).getTime(),
      ),
    [conversations],
  );

  const activeConversation = useMemo(
    () =>
      conversations.find(
        (conversation) => conversation.id === activeConversationId,
      ) || null,
    [activeConversationId, conversations],
  );

  useEffect(() => {
    if (!writeStoredValue(profileStorageKey, profile)) {
      setStorageWarning(
        "პროფილის ცვლილება ბრაუზერში ვერ შეინახა. შეამოწმე საცავის ნებართვა.",
      );
    }
  }, [profile, profileStorageKey]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      if (!writeStoredValue(chatStorageKey, conversations)) {
        setStorageWarning(
          "საუბრები ბრაუზერში ვერ შეინახა. გააკეთე ისტორიის ექსპორტი ან გაათავისუფლე საცავი.",
        );
      }
    }, 220);
    return () => window.clearTimeout(timeout);
  }, [chatStorageKey, conversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: reduceMotion ? "auto" : "smooth",
      block: "end",
    });
  }, [activeConversation?.messages, reduceMotion]);

  const loadStatus = useCallback(async () => {
    setStatus((current) => ({ ...current, loading: true }));
    try {
      const response = await fetchWithTimeout(
        `${API_BASE}/api/status`,
        {},
        8_000,
      );
      if (!response.ok) throw new Error("API offline");
      const data = await response.json();
      setStatus({
        loading: false,
        apiOnline: true,
        ollamaOnline: Boolean(data.ollama?.connected),
        modelAvailable: Boolean(data.ollama?.model_available),
        knowledgeReady: Boolean(data.knowledge_base?.ready),
        chunks: data.knowledge_base?.chunks || 0,
      });
    } catch {
      setStatus({ ...INITIAL_STATUS, loading: false });
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  function updateAssistant(conversationId, assistantId, patch) {
    setConversations((current) =>
      current.map((conversation) => {
        if (conversation.id !== conversationId) return conversation;
        return {
          ...conversation,
          updatedAt: new Date().toISOString(),
          messages: conversation.messages.map((message) =>
            message.id === assistantId
              ? {
                  ...message,
                  ...(typeof patch === "function" ? patch(message) : patch),
                }
              : message,
          ),
        };
      }),
    );
  }

  async function sendMessage(prefilled) {
    const content = (prefilled ?? input).trim();
    if (!content || isStreaming) return;

    const existingConversation = activeConversation;
    const conversationId =
      existingConversation?.id || createId();
    const assistantId = createId();
    const now = new Date().toISOString();
    const userMessage = {
      id: createId(),
      role: "user",
      content,
    };
    const assistantMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      sources: [],
      analysis: null,
      error: false,
    };
    const history = (existingConversation?.messages || [])
      .filter((item) => item.content && !item.error)
      .slice(-12)
      .map(({ role, content: messageContent }) => ({
        role,
        content: messageContent,
      }));

    if (existingConversation) {
      setConversations((current) =>
        current.map((conversation) =>
          conversation.id === conversationId
            ? {
                ...conversation,
                updatedAt: now,
                messages: [
                  ...conversation.messages,
                  userMessage,
                  assistantMessage,
                ],
              }
            : conversation,
        ),
      );
    } else {
      setConversations((current) => [
        {
          id: conversationId,
          title: createConversationTitle(content),
          mode: activeMode,
          createdAt: now,
          updatedAt: now,
          messages: [userMessage, assistantMessage],
        },
        ...current,
      ]);
      setActiveConversationId(conversationId);
    }

    setInput("");
    setIsStreaming(true);
    setActiveView("chat");

    const controller = new AbortController();
    abortRef.current = controller;
    streamRef.current = { conversationId, assistantId };

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          message: content,
          mode: activeMode,
          history,
        }),
        signal: controller.signal,
      });
      if (response.status === 401) {
        updateAssistant(conversationId, assistantId, {
          error: true,
          content: "სესია დასრულდა. ანგარიშში თავიდან შედი.",
        });
        onSessionExpired();
        return;
      }
      if (!response.ok || !response.body) {
        const data = await response.json().catch(() => ({}));
        throw new Error(
          apiErrorMessage(data, `სერვერის შეცდომა (${response.status}).`),
        );
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finished = false;
      let receivedContent = false;
      let receivedError = false;

      function processBlock(block) {
        const parsed = parseSseBlock(block);
        if (!parsed) return;
        if (parsed.event === "token") {
          const token = parsed.data.content || "";
          if (token) receivedContent = true;
          updateAssistant(conversationId, assistantId, (current) => ({
            content: current.content + token,
          }));
        }
        if (parsed.event === "sources") {
          updateAssistant(conversationId, assistantId, {
            sources: parsed.data.sources || [],
          });
        }
        if (parsed.event === "analysis") {
          updateAssistant(conversationId, assistantId, {
            analysis: parsed.data,
          });
        }
        if (parsed.event === "error") {
          receivedError = true;
          updateAssistant(conversationId, assistantId, {
            error: true,
            content: parsed.data.message || "პასუხის მიღება ვერ მოხერხდა.",
          });
        }
      }

      while (!finished) {
        const result = await reader.read();
        finished = result.done;
        buffer += decoder.decode(result.value || new Uint8Array(), {
          stream: !finished,
        });
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() || "";

        for (const block of blocks) {
          processBlock(block);
        }
      }
      if (buffer.trim()) processBlock(buffer);
      if (!receivedContent && !receivedError) {
        updateAssistant(conversationId, assistantId, {
          error: true,
          content: "მოდელმა ცარიელი პასუხი დააბრუნა. სცადე კითხვა თავიდან.",
        });
      }
    } catch (error) {
      if (error.name !== "AbortError") {
        updateAssistant(conversationId, assistantId, {
          error: true,
          content:
            error instanceof TypeError
              ? "სერვერთან დაკავშირება ვერ მოხერხდა. შეამოწმე FastAPI და ქსელი."
              : error.message || "პასუხის მიღება ვერ მოხერხდა.",
        });
      }
    } finally {
      abortRef.current = null;
      streamRef.current = null;
      setIsStreaming(false);
      loadStatus();
    }
  }

  function stopGeneration() {
    const stream = streamRef.current;
    abortRef.current?.abort();
    if (stream) {
      updateAssistant(
        stream.conversationId,
        stream.assistantId,
        (message) => ({
          content: message.content || "პასუხი შეჩერებულია.",
          stopped: true,
        }),
      );
    }
    streamRef.current = null;
    setIsStreaming(false);
  }

  function startNewChat(mode = activeMode) {
    if (isStreaming) stopGeneration();
    setActiveConversationId(null);
    setActiveMode(mode);
    setActiveView("chat");
    setInput("");
    setMobileOpen(false);
  }

  function changeMode(mode) {
    if (mode === activeMode && !activeConversation) return;
    startNewChat(mode);
  }

  function chooseSuggestion(mode, prompt) {
    if (isStreaming) stopGeneration();
    setActiveConversationId(null);
    setActiveMode(mode);
    setActiveView("chat");
    setInput(prompt);
  }

  function openConversation(id) {
    if (isStreaming) stopGeneration();
    const conversation = conversations.find((item) => item.id === id);
    if (!conversation) return;
    setActiveConversationId(id);
    setActiveMode(conversation.mode || "learn");
    setActiveView("chat");
    setInput("");
    setMobileOpen(false);
  }

  function deleteConversation(id) {
    const conversation = conversations.find((item) => item.id === id);
    if (!conversation) return;
    if (!window.confirm(`წავშალოთ საუბარი „${conversation.title}“?`)) return;
    if (activeConversationId === id && isStreaming) stopGeneration();
    setConversations((current) =>
      current.filter((item) => item.id !== id),
    );
    if (activeConversationId === id) setActiveConversationId(null);
  }

  function clearHistory() {
    if (
      !window.confirm(
        "ნამდვილად გსურს ყველა შენახული საუბრის წაშლა? ამ მოქმედების გაუქმება შეუძლებელია.",
      )
    ) {
      return;
    }
    if (isStreaming) stopGeneration();
    setConversations([]);
    setActiveConversationId(null);
    setActiveView("chat");
  }

  function exportHistory() {
    if (!conversations.length) return;
    const exportData = {
      exportedAt: new Date().toISOString(),
      profile,
      conversations: sortedConversations,
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `metyveli-history-${new Date().toISOString().slice(0, 10)}.json`;
    link.hidden = true;
    document.body.append(link);
    link.click();
    window.setTimeout(() => {
      link.remove();
      URL.revokeObjectURL(url);
    }, 0);
  }

  const headerTitle =
    activeView === "profile"
      ? "პროფილი"
      : activeConversation?.title || "ახალი საუბარი";

  return (
    <div className="app-shell">
      <Sidebar
        activeConversationId={activeConversationId}
        activeView={activeView}
        conversations={sortedConversations}
        mobileOpen={mobileOpen}
        onClose={closeHistory}
        onDeleteConversation={deleteConversation}
        onNewChat={() => startNewChat()}
        onOpenHistory={openHistory}
        onOpenConversation={openConversation}
        onOpenProfile={() => {
          if (isStreaming) stopGeneration();
          setActiveView("profile");
          setMobileOpen(false);
        }}
        search={search}
        setSearch={setSearch}
      />

      <main className="main-area">
        <header className="app-header">
          <div className="app-header-title">
            <button
              className="icon-button mobile-menu"
              type="button"
              onClick={() => setMobileOpen(true)}
              aria-label="მენიუს გახსნა"
            >
              <List size={20} />
            </button>
            <div>
              <strong>{headerTitle}</strong>
              <small>
                {activeView === "profile"
                  ? "პარამეტრები და საუბრის აქტივობა"
                  : activeConversation
                    ? `${activeConversation.messages.filter((item) => item.role === "user").length} შეკითხვა`
                    : "საუბარი ავტომატურად შეინახება"}
              </small>
            </div>
          </div>

          <div className="app-header-actions">
            <ConnectionStatus status={status} onRetry={loadStatus} />
            <ThemeButton
              theme={theme}
              onToggle={() =>
                setTheme((current) => (current === "dark" ? "light" : "dark"))
              }
            />
            <button
              className="header-account"
              type="button"
              onClick={() => setActiveView("profile")}
              aria-label="პროფილის გახსნა"
            >
              <span className="profile-avatar" aria-hidden="true">
                {profile.name.trim().charAt(0) || "მ"}
              </span>
              <span>
                <strong>{profile.name}</strong>
                <small>{session.user.email}</small>
              </span>
            </button>
          </div>
        </header>

        {storageWarning && (
          <div className="storage-warning" role="alert">
            <WarningCircle size={18} />
            <span>{storageWarning}</span>
            <button
              type="button"
              onClick={() => setStorageWarning("")}
              aria-label="შეტყობინების დახურვა"
            >
              <X size={16} />
            </button>
          </div>
        )}

        {activeView === "profile" ? (
          <ProfilePage
            account={session.user}
            conversations={sortedConversations}
            onBack={() => setActiveView("chat")}
            onClearHistory={clearHistory}
            onExportHistory={exportHistory}
            onLogout={onLogout}
            profile={profile}
            setProfile={setProfile}
            status={status}
            theme={theme}
            setTheme={setTheme}
          />
        ) : (
          <ChatWorkspace
            activeConversation={activeConversation}
            activeMode={activeMode}
            bottomRef={bottomRef}
            input={input}
            isStreaming={isStreaming}
            onChangeMode={changeMode}
            onInputChange={setInput}
            onSend={sendMessage}
            onSuggestion={chooseSuggestion}
            onStop={stopGeneration}
            profile={profile}
            reduceMotion={reduceMotion}
            status={status}
          />
        )}
      </main>
    </div>
  );
}

export default function App() {
  const [theme, setTheme] = useState(() => {
    const stored = readStoredString(THEME_STORAGE_KEY, "dark");
    return ["light", "dark"].includes(stored) ? stored : "dark";
  });
  const [session, setSession] = useState(() =>
    readStoredValue(AUTH_STORAGE_KEY, null),
  );
  const [checkingSession, setCheckingSession] = useState(
    () => Boolean(session?.access_token),
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    writeStoredString(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    let active = true;

    async function validateSession() {
      if (!session?.access_token) {
        setCheckingSession(false);
        return;
      }
      setCheckingSession(true);
      try {
        const response = await fetchWithTimeout(
          `${API_BASE}/api/auth/me`,
          {
            headers: {
              Authorization: `Bearer ${session.access_token}`,
            },
          },
          12_000,
        );
        if ([401, 403].includes(response.status)) {
          if (!active) return;
          removeStoredValue(AUTH_STORAGE_KEY);
          setSession(null);
          return;
        }
        if (!response.ok) throw new Error("Session validation failed");
        const user = await response.json();
        if (!active) return;
        const validated = { ...session, user };
        writeStoredValue(AUTH_STORAGE_KEY, validated);
        setSession(validated);
      } catch {
        if (!active) return;
        // Keep the local session during temporary network/API outages.
        // Protected endpoints will still reject an invalid token with 401.
      } finally {
        if (active) setCheckingSession(false);
      }
    }

    validateSession();
    return () => {
      active = false;
    };
  }, [session?.access_token]);

  function authenticate(nextSession) {
    writeStoredValue(AUTH_STORAGE_KEY, nextSession);
    setSession(nextSession);
    setCheckingSession(false);
  }

  function expireSession() {
    removeStoredValue(AUTH_STORAGE_KEY);
    setSession(null);
    setCheckingSession(false);
  }

  async function logout() {
    const token = session?.access_token;
    expireSession();
    if (!token) return;
    try {
      await fetchWithTimeout(
        `${API_BASE}/api/auth/logout`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        },
        10_000,
      );
    } catch {
      // The local session is already cleared; server cleanup can expire later.
    }
  }

  if (checkingSession) return <SessionLoading />;

  if (!session?.access_token || !session?.user) {
    return (
      <AuthScreen
        onAuthenticated={authenticate}
        theme={theme}
        onToggleTheme={() =>
          setTheme((current) => (current === "dark" ? "light" : "dark"))
        }
      />
    );
  }

  return (
    <AuthenticatedApp
      key={session.user.id}
      onLogout={logout}
      onSessionExpired={expireSession}
      session={session}
      setTheme={setTheme}
      theme={theme}
    />
  );
}
