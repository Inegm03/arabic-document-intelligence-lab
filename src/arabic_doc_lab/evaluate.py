"""Evaluation primitives used by both experiments and the API."""

from dataclasses import asdict, dataclass
from time import perf_counter

from PIL import Image

from .metrics import character_error_rate, word_error_rate


@dataclass(frozen=True)
class Result:
    engine: str
    prediction: str
    cer: float
    wer: float
    latency_ms: float

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate_one(engine, image: Image.Image, reference: str) -> Result:
    started = perf_counter()
    prediction = engine.recognize(image)
    latency_ms = (perf_counter() - started) * 1000
    return Result(engine.name, prediction, character_error_rate(reference, prediction),
                  word_error_rate(reference, prediction), latency_ms)

