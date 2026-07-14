from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion
from sklearn.preprocessing import FunctionTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.ml_features import extract_rule_features


def make_pipeline(classifier) -> Pipeline:
    return Pipeline(
        [
            (
                "features",
                FeatureUnion(
                    [
                        (
                            "tfidf",
                            TfidfVectorizer(
                                analyzer="char_wb",
                                ngram_range=(2, 5),
                                min_df=1,
                                sublinear_tf=True,
                                max_features=45_000,
                            ),
                        ),
                        (
                            "grammar_signals",
                            FunctionTransformer(
                                extract_rule_features,
                                validate=False,
                            ),
                        ),
                    ]
                ),
            ),
            ("classifier", classifier),
        ]
    )


def split_by_source(data: pd.DataFrame):
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    train_indices, test_indices = next(
        splitter.split(data, data["label"], groups=data["source_id"])
    )
    return data.iloc[train_indices].copy(), data.iloc[test_indices].copy()


def evaluate(name: str, model, test: pd.DataFrame) -> tuple[dict, list[str]]:
    predictions = model.predict(test["text"])
    metrics = {
        "model": name,
        "accuracy": round(accuracy_score(test["label"], predictions), 4),
        "macro_f1": round(
            f1_score(test["label"], predictions, average="macro"),
            4,
        ),
    }
    return metrics, list(predictions)


def train(
    dataset_path: Path,
    model_path: Path,
    reports_dir: Path,
) -> dict:
    data = pd.read_csv(dataset_path, encoding="utf-8-sig").dropna()
    train_data, test_data = split_by_source(data)

    baseline = DummyClassifier(strategy="most_frequent")
    baseline.fit([[0]] * len(train_data), train_data["label"])
    baseline_predictions = baseline.predict([[0]] * len(test_data))
    results = [
        {
            "model": "Majority baseline",
            "accuracy": round(
                accuracy_score(test_data["label"], baseline_predictions),
                4,
            ),
            "macro_f1": round(
                f1_score(
                    test_data["label"],
                    baseline_predictions,
                    average="macro",
                ),
                4,
            ),
        }
    ]

    candidates = {
        "Logistic Regression": make_pipeline(
            LogisticRegression(
                max_iter=2_000,
                class_weight="balanced",
                random_state=42,
            )
        ),
        "Linear SVM": make_pipeline(
            LinearSVC(class_weight="balanced", random_state=42)
        ),
        "Multinomial Naive Bayes": make_pipeline(
            MultinomialNB(alpha=0.35)
        ),
    }

    trained: dict[str, Pipeline] = {}
    prediction_map: dict[str, list[str]] = {}
    for name, model in candidates.items():
        model.fit(train_data["text"], train_data["label"])
        metrics, predictions = evaluate(name, model, test_data)
        results.append(metrics)
        trained[name] = model
        prediction_map[name] = predictions

    best_result = max(results[1:], key=lambda item: item["macro_f1"])
    best_name = best_result["model"]
    best_model = trained[best_name]
    best_predictions = prediction_map[best_name]

    model_path.parent.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, model_path)

    comparison = pd.DataFrame(results).sort_values(
        "macro_f1",
        ascending=False,
    )
    comparison.to_csv(
        reports_dir / "model_comparison.csv",
        index=False,
        encoding="utf-8-sig",
    )

    labels = ["correct", "error"]
    matrix = confusion_matrix(
        test_data["label"],
        best_predictions,
        labels=labels,
    )
    plt.figure(figsize=(6, 5))
    sns.heatmap(
        matrix,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=labels,
        yticklabels=labels,
    )
    plt.title(f"Confusion matrix: {best_name}")
    plt.xlabel("Prediction")
    plt.ylabel("True label")
    plt.tight_layout()
    plt.savefig(reports_dir / "confusion_matrix.png", dpi=180)
    plt.close()

    examples = test_data[
        ["source_id", "text", "label", "error_type", "correct_text"]
    ].copy()
    examples["prediction"] = best_predictions
    examples["is_correct_prediction"] = (
        examples["label"] == examples["prediction"]
    )
    good = examples[examples["is_correct_prediction"]].head(8)
    bad = examples[~examples["is_correct_prediction"]].head(8)
    pd.concat([good, bad]).to_csv(
        reports_dir / "good_bad_predictions.csv",
        index=False,
        encoding="utf-8-sig",
    )

    summary = {
        "dataset_rows": len(data),
        "train_rows": len(train_data),
        "test_rows": len(test_data),
        "split": "GroupShuffleSplit by source sentence",
        "best_model": best_name,
        "best_metrics": best_result,
        "baseline_metrics": results[0],
        "all_results": results,
        "model_path": str(model_path),
    }
    with (reports_dir / "metrics.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/processed/grammar_dataset.csv"),
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("models/grammar_classifier.joblib"),
    )
    parser.add_argument(
        "--reports",
        type=Path,
        default=Path("reports/model"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(
        json.dumps(
            train(args.dataset, args.model, args.reports),
            ensure_ascii=False,
            indent=2,
        )
    )
