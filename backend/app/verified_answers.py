from __future__ import annotations

from collections.abc import Sequence

from .routing import is_grammar_question, normalize_query


GRAMMAR_GENRES = {
    "გრამატიკა",
    "მართლწერა",
    "პუნქტუაცია",
    "სინტაქსი",
    "ენა",
}

LITERATURE_GENRES = {
    "ლიტერატურული ტექსტი",
    "ლექსი",
    "მოთხრობა",
    "პოემა",
    "რომანი",
    "ზღაპარი",
    "იგავი",
    "ნოველა",
    "დრამა",
}


def verified_general_answer(message: str) -> str | None:
    normalized = normalize_query(message)
    asks_for_largest_river = (
        "მდინარე" in normalized
        and any(
            phrase in normalized
            for phrase in (
                "ყველაზე დიდი",
                "უდიდესი",
                "ყველაზე გრძელი",
                "უგრძესი",
                "ყველაზე წყალუხვი",
                "წყალუხვი",
            )
        )
    )
    if asks_for_largest_river:
        return (
            "„ყველაზე დიდი“ კრიტერიუმზეა დამოკიდებული: მსოფლიოში "
            "წყალუხვობითა და აუზის ფართობით უდიდესია ამაზონი, ხოლო სიგრძით "
            "ყველაზე გრძელ მდინარედ ხშირად ნილოსს ასახელებენ; ნილოსისა და "
            "ამაზონის სიგრძის გაზომვაზე განსხვავებული შეფასებებიც არსებობს. "
            "თუ საქართველოს მდინარეებს გულისხმობ, დამიზუსტე — სიგრძით, "
            "წყალუხვობით თუ აუზის ფართობით."
        )

    asks_for_highest_mountain = (
        "მთა" in normalized
        and any(
            phrase in normalized
            for phrase in (
                "ყველაზე დიდი",
                "ყველაზე მაღალი",
                "უმაღლესი",
            )
        )
    )
    if asks_for_highest_mountain:
        return (
            "თუ ზღვის დონიდან სიმაღლეს გულისხმობ, მსოფლიოში უმაღლესი მთა "
            "ევერესტია — 8 848,86 მეტრი."
        )
    return None


def grammar_correction_answer(result: dict) -> str:
    issues = result.get("issues", [])
    if not issues:
        return (
            "ავტომატურმა შემოწმებამ აშკარა მართლწერის ან პუნქტუაციის შეცდომა "
            "ვერ აღმოაჩინა. ეს შედეგი საბოლოო რედაქტორულ შეფასებას არ ცვლის."
        )

    explanations = []
    for issue in issues[:8]:
        original = issue.get("original", "")
        replacement = issue.get("replacement", "")
        explanations.append(
            f"- {issue['message']}: „{original}“ → „{replacement}“"
        )
    return "\n".join(
        [
            "შესწორებული ვარიანტი:",
            result["corrected"],
            "",
            "ცვლილებების ახსნა:",
            *explanations,
        ]
    )


def verified_grammar_answer(context: dict) -> str:
    return "\n\n".join(
        [
            context["title"],
            context["text"],
            "თუ გინდა, ამ წესზე მოკლე სავარჯიშოსაც შეგიდგენ.",
        ]
    )


def verified_literature_answer(
    message: str,
    contexts: Sequence[dict],
) -> str | None:
    if not contexts:
        return None

    top = contexts[0]
    title = top["title"]
    author = top.get("author") or "ავტორი წყაროში მითითებული არ არის"
    genre = top.get("genre") or "ლიტერატურული ტექსტი"
    lowered = message.casefold()

    if "ვინ დაწერა" in lowered or "ავტორი" in lowered:
        return f"„{title}“-ის ავტორია {author}."

    excerpt = top["text"].strip()
    if len(excerpt) > 700:
        excerpt = excerpt[:700].rsplit(" ", 1)[0].rstrip() + "…"
    return "\n\n".join(
        [
            f"მოძიებული ნაწარმოები: „{title}“",
            f"ავტორი: {author}\nწყაროს კატეგორია: {genre}",
            f"წყაროს შესაბამისი ფრაგმენტი:\n„{excerpt}“",
            (
                "თუ გჭირდება სიუჟეტი, პერსონაჟის დახასიათება ან კონკრეტული "
                "მხატვრული ხერხის განხილვა, კითხვა უფრო ზუსტად ჩამოაყალიბე."
            ),
        ]
    )


def build_verified_answer(
    mode: str,
    message: str,
    contexts: Sequence[dict],
    grammar_result: dict | None,
) -> str | None:
    if mode == "grammar":
        if grammar_result and grammar_result.get("issues"):
            return grammar_correction_answer(grammar_result)
        if (
            is_grammar_question(message)
            and contexts
            and contexts[0].get("genre") in GRAMMAR_GENRES
        ):
            return verified_grammar_answer(contexts[0])
        if grammar_result:
            return grammar_correction_answer(grammar_result)

    if mode == "learn":
        if (
            is_grammar_question(message)
            and contexts
            and contexts[0].get("genre") in GRAMMAR_GENRES
        ):
            return verified_grammar_answer(contexts[0])

    if mode == "literature":
        return verified_literature_answer(message, contexts)

    return None
