"""Dependency-free OCR metrics with Arabic-aware normalization."""

import re
import unicodedata


def normalize_arabic(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u064b-\u065f\u0670\u06d6-\u06ed]", "", text)
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ـ": ""}))
    return " ".join(text.split())


def _distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, expected in enumerate(reference, 1):
        current = [i]
        for j, actual in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (expected != actual)))
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float:
    reference, hypothesis = normalize_arabic(reference), normalize_arabic(hypothesis)
    return _distance(list(reference), list(hypothesis)) / max(1, len(reference))


def word_error_rate(reference: str, hypothesis: str) -> float:
    reference, hypothesis = normalize_arabic(reference), normalize_arabic(hypothesis)
    return _distance(reference.split(), hypothesis.split()) / max(1, len(reference.split()))

