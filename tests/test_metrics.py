from arabic_doc_lab.metrics import character_error_rate, normalize_arabic, word_error_rate


def test_arabic_normalization_handles_diacritics_and_alef_variants():
    assert normalize_arabic("إِنَّ  العِلْمَ") == "ان العلم"


def test_identical_text_scores_zero():
    assert character_error_rate("مرحبا بالعالم", "مرحبا بالعالم") == 0
    assert word_error_rate("مرحبا بالعالم", "مرحبا بالعالم") == 0


def test_word_substitution():
    assert word_error_rate("واحد اثنان ثلاثة", "واحد اربعة ثلاثة") == 1 / 3

