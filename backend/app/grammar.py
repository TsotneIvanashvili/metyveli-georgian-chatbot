import math
import re
from pathlib import Path

import joblib


COMMON_REPLACEMENTS = {
    "რათქმაუნდა": "რა თქმა უნდა",
    "მიუხედავათ": "მიუხედავად",
    "ალბად": "ალბათ",
    "რამოდენიმე": "რამდენიმე",
    "ერთერთი": "ერთ-ერთი",
    "არააქვს": "არ აქვს",
    "ვინხარ": "ვინ ხარ",
    "დავწერავ": "დავწერ",
    "ავღნიშნავ": "აღვნიშნავ",
    "ვნახამ": "ვნახავ",
}


class GrammarAnalyzer:
    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self.model = None

    @property
    def model_ready(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        self.model = None
        if self.model_path.exists():
            self.model = joblib.load(self.model_path)

    def _model_prediction(self, text: str) -> tuple[str, float] | None:
        if self.model is None:
            return None
        label = str(self.model.predict([text])[0])
        confidence = 0.5
        if hasattr(self.model, "decision_function"):
            raw = self.model.decision_function([text])
            margin = float(raw[0]) if getattr(raw, "ndim", 1) == 1 else float(max(raw[0]))
            confidence = 1 / (1 + math.exp(-abs(margin)))
        return label, round(confidence, 3)

    def analyze(self, text: str) -> dict:
        issues: list[dict] = []
        corrected = text

        for match in re.finditer(r"[ \t]{2,}", text):
            issues.append(
                {
                    "type": "double_space",
                    "message": "ზედმეტი გამოტოვება",
                    "original": match.group(0),
                    "replacement": " ",
                    "start": match.start(),
                    "end": match.end(),
                }
            )
        corrected = re.sub(r"[ \t]{2,}", " ", corrected)

        for match in re.finditer(r"\s+([,.;:!?])", text):
            issues.append(
                {
                    "type": "punctuation_space",
                    "message": "სასვენ ნიშანს წინ გამოტოვება არ სჭირდება",
                    "original": match.group(0),
                    "replacement": match.group(1),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
        corrected = re.sub(r"\s+([,.;:!?])", r"\1", corrected)

        for match in re.finditer(r"([,;:!?])(?=[^\s\d\n])", text):
            issues.append(
                {
                    "type": "missing_space",
                    "message": "სასვენი ნიშნის შემდეგ საჭიროა გამოტოვება",
                    "original": match.group(1),
                    "replacement": match.group(1) + " ",
                    "start": match.start(),
                    "end": match.end(),
                }
            )
        corrected = re.sub(r"([,;:!?])(?=[^\s\d\n])", r"\1 ", corrected)

        for wrong, right in COMMON_REPLACEMENTS.items():
            for match in re.finditer(
                rf"(?<![\u10A0-\u10FF]){re.escape(wrong)}(?![\u10A0-\u10FF])",
                text,
                flags=re.IGNORECASE,
            ):
                issues.append(
                    {
                        "type": "common_spelling",
                        "message": "რეკომენდებულია სალიტერატურო ფორმა",
                        "original": match.group(0),
                        "replacement": right,
                        "start": match.start(),
                        "end": match.end(),
                    }
                )
            corrected = re.sub(
                rf"(?<![\u10A0-\u10FF]){re.escape(wrong)}(?![\u10A0-\u10FF])",
                right,
                corrected,
                flags=re.IGNORECASE,
            )

        latin_match = re.search(r"[A-Za-zА-Яа-я]", text)
        if latin_match:
            issues.append(
                {
                    "type": "mixed_alphabet",
                    "message": "ტექსტში სხვა ანბანის სიმბოლოა გამოყენებული",
                    "original": latin_match.group(0),
                    "replacement": "",
                    "start": latin_match.start(),
                    "end": latin_match.end(),
                }
            )

        prediction = self._model_prediction(text)
        if prediction is None:
            predicted_label = "error" if issues else "correct"
            confidence = 1.0 if issues else 0.6
            method = "rules"
        else:
            predicted_label, confidence = prediction
            method = "trained_model+rules"
            if issues:
                predicted_label = "error"

        return {
            "original": text,
            "corrected": corrected.strip(),
            "label": predicted_label,
            "confidence": confidence,
            "method": method,
            "issues": issues,
        }

    def prompt_summary(self, text: str) -> str:
        result = self.analyze(text)
        if not result["issues"]:
            return (
                f"კლასი: {result['label']}; ავტომატურმა წესებმა კონკრეტული "
                "შეცდომა ვერ იპოვა."
            )
        details = "; ".join(
            f"{item['message']}: „{item['original']}“ -> „{item['replacement']}“"
            for item in result["issues"][:8]
        )
        return (
            f"კლასი: {result['label']}; შესწორებული ვარიანტი: "
            f"{result['corrected']}; დეტალები: {details}"
        )
