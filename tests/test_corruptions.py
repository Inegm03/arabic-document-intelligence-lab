import pytest
from PIL import Image

from arabic_doc_lab.corruptions import corrupt


@pytest.mark.parametrize("kind", ["blur", "low_contrast", "dark", "jpeg"])
def test_corruptions_preserve_dimensions(kind):
    image = Image.new("RGB", (64, 32), "white")
    assert corrupt(image, kind, 3).size == image.size


def test_invalid_severity_is_rejected():
    with pytest.raises(ValueError):
        corrupt(Image.new("RGB", (8, 8)), "blur", 0)

