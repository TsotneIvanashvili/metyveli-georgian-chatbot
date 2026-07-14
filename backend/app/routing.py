import re


GREETINGS = {
    "გამარჯობა",
    "გაგიმარჯოს",
    "სალამი",
    "მოგესალმები",
    "ჰეი",
    "hello",
    "hi",
    "დილა მშვიდობისა",
    "საღამო მშვიდობისა",
    "როგორ ხარ",
}

GRAMMAR_KEYWORDS = (
    "ბრუნვ",
    "ზმნ",
    "არსებით",
    "ზედსართავ",
    "ნაცვალსახ",
    "მეტყველების ნაწილ",
    "გრამატიკ",
    "მართლწერ",
    "პუნქტუაც",
    "სინტაქს",
    "მორფოლოგ",
    "მძიმე",
    "წერტილ",
    "ტირე",
    "ბრჭყალ",
    "მრავლობით",
    "ერთობით",
    "წინადადებ",
    "სიტყვა",
    "გრამატიკული წესი",
    "მართლწერის წესი",
)

GRAMMAR_CORRECTION_KEYWORDS = (
    "გამისწორ",
    "შეასწორ",
    "შესწორ",
    "შეამოწმ",
    "სწორია",
    "არასწორია",
    "შეცდომ",
    "როგორ იწერ",
    "რომელია სწორი",
)

LANGUAGE_LEARNING_KEYWORDS = (
    "ქართული",
    "ენის სწავლ",
    "ვისწავლ",
    "სწავლა",
    "სავარჯიშ",
    "დამწყებ",
    "თარგმნ",
    "ლაპარაკ",
    "მეტყველ",
    "ლექსიკ",
    "მაგალით",
)

IDENTITY_PATTERNS = (
    "ვინ ხარ",
    "ვინხარ",
    "შენ ვინ",
    "რა ხარ",
    "რა გქვია",
    "შენი სახელი",
    "ვინ შეგქმნა",
    "შენი დავალება",
    "რა არის შენი დავალება",
    "რა შეგიძლია",
    "რას აკეთებ",
)


def normalize_query(value: str) -> str:
    value = value.casefold().strip()
    value = re.sub(r"[^\w\u10A0-\u10FF\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def is_greeting(value: str) -> bool:
    normalized = normalize_query(value)
    if normalized in GREETINGS:
        return True
    words = normalized.split()
    return len(words) <= 4 and any(greeting in words for greeting in GREETINGS)


def is_identity_question(value: str) -> bool:
    normalized = normalize_query(value)
    return any(pattern in normalized for pattern in IDENTITY_PATTERNS)


def is_grammar_question(value: str) -> bool:
    normalized = normalize_query(value)
    return any(keyword in normalized for keyword in GRAMMAR_KEYWORDS)


def should_analyze_grammar(value: str) -> bool:
    normalized = normalize_query(value)
    if not normalized:
        return False
    if any(
        keyword in normalized
        for keyword in GRAMMAR_CORRECTION_KEYWORDS
    ):
        return True
    # Grammar mode also accepts pasted text without an explicit "correct this"
    # instruction. A normal question is left to the language model.
    return not value.rstrip().endswith("?") and len(normalized.split()) >= 2


def is_language_learning_question(value: str) -> bool:
    normalized = normalize_query(value)
    return any(
        keyword in normalized for keyword in LANGUAGE_LEARNING_KEYWORDS
    )


def should_use_retrieval(message: str, mode: str) -> bool:
    if is_greeting(message) or is_identity_question(message):
        return False

    normalized = normalize_query(message)
    if not normalized:
        return False

    if mode == "literature":
        return True

    return is_grammar_question(normalized)
