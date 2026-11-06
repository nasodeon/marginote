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


def test_year_in_the_first_line_is_not_taken_for_the_page_number():
    words = [
        w(0, "1902", 0, x=500, y=40),       # a year alone near the top edge
        w(1, "Première", 1, x=100, y=300), w(2, "édition", 1, x=300, y=300),
        w(3, "45", 2, x=500, y=1640),       # the real page number at the bottom
    ]
    for word in words:
        word.h = 30
    assert ocr.detect_page(words, 1200, 1700) == "45"


def test_words_in_a_spine_shadow_are_still_read():
    """Text running to the page edge with a dark gradient along it, like the spine of an open book."""
    import collections

    from conftest import _font
    from PIL import Image, ImageDraw, ImageFilter, ImageOps

    words = ("On fait la science avec des faits comme on fait une maison avec des pierres mais une "
             "accumulation de faits n’est pas plus une science qu’un tas de pierres n’est une maison").split()
    img = Image.new("L", (1800, 1200), 236)
    draw, font, truth, k, y = ImageDraw.Draw(img), _font(46), [], 0, 120
    while y < 1080:
        x = 6
        while x + draw.textlength(words[k % len(words)], font=font) < 1794:
            word = words[k % len(words)]
            draw.text((x, y), word, font=font, fill=30)
            truth.append(word)
            x += draw.textlength(word + " ", font=font)
            k += 1
        y += 74
    shade = ImageOps.invert(Image.linear_gradient("L").rotate(90, expand=True).resize((380, 1200)))
    img.paste(Image.composite(Image.new("L", (380, 1200), 70), img.crop((0, 0, 380, 1200)),
                              shade.point(lambda v: int(v * 0.85))), (0, 0))
    img = img.filter(ImageFilter.GaussianBlur(0.8)).convert("RGB")

    got = collections.Counter(w.text.strip(".,;:") for w in ocr.recognize(img, "fra+eng"))
    want = collections.Counter(truth)
    recall = sum(min(got[w], n) for w, n in want.items()) / sum(want.values())
    assert recall > 0.93, recall      # about 0.83 without the lighting correction
