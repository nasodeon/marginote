from conftest import make_page

from marginote import ocr
from marginote.db import page_sort_key


def w(i, text, line, x=0, y=0):
    return ocr.Word(i=i, text=text, conf=95.0, x=x, y=y, w=10, h=10, line=line)


def test_hyphen_at_line_end_is_glued_back():
    words = [w(0, "tas", 0), w(1, "de", 0), w(2, "pier-", 0), w(3, "res", 1), w(4, "n’est", 1)]
    assert ocr.join_words(words) == "tas de pierres n’est"


def test_hyphen_inside_a_line_is_kept():
    words = [w(0, "peut-être", 0), w(1, "demain", 0)]
    assert ocr.join_words(words) == "peut-être demain"


def test_space_before_comma_is_removed_but_french_semicolon_spacing_kept():
    words = [w(0, "pierres", 0), w(1, ";", 0), w(2, "mais", 0), w(3, "une", 0), w(4, ",", 0)]
    assert ocr.join_words(words) == "pierres ; mais une,"


def test_page_sort_keys():
    assert page_sort_key("168") == 168
    assert page_sort_key("xii") < page_sort_key("1")
    assert page_sort_key(None) is None


def test_real_ocr_reads_text_page_number_and_selection():
    img, jpeg = ocr.normalize_photo(make_page("168"))
    assert jpeg[:2] == b"\xff\xd8"
    words = ocr.recognize(img, "fra+eng")
    texts = [x.text for x in words]
    assert len(words) > 40
    assert "science" in texts and "maison" in texts

    assert ocr.detect_page(words, img.width, img.height) == "168"

    first = texts.index("On")
    last = next(x.i for x in words if x.text.startswith("maison.") or x.text == "maison.")
    passage = ocr.select_range(words, first, last)
    assert passage.startswith("On fait la science")
    assert "pierres n" in passage and "pier-" not in passage
    assert passage.endswith("maison.")


def test_page_number_not_confused_with_numbers_in_text():
    img, _ = ocr.normalize_photo(make_page("27"))
    words = ocr.recognize(img, "fra+eng")
    assert ocr.detect_page(words, img.width, img.height) == "27"
