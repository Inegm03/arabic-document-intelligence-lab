from PIL import Image

from arabic_doc_lab.evaluate import evaluate_one


class StubEngine:
    name = "stub"
    def recognize(self, image):
        return "نص صحيح"


def test_evaluation_returns_reproducible_metrics():
    result = evaluate_one(StubEngine(), Image.new("RGB", (8, 8)), "نص صحيح")
    assert result.engine == "stub"
    assert result.cer == result.wer == 0
    assert result.latency_ms >= 0

