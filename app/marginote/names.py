"""People's names: as written ('Baruch Spinoza'), as in an index ('Spinoza, Baruch'), and a key to match them."""

import re
import unicodedata

# words that belong to the family name when they come before it: 'Charles de Gaulle' -> 'Gaulle, Charles de'
PARTICLES = {"de", "du", "des", "d'", "d’", "la", "le", "van", "von", "der", "den", "di", "da", "del", "della", "dos", "ten", "ter"}
_DATES = re.compile(r"\s*\(([^)]*\d[^)]*)\)\s*$")


def clean(name: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", name or "")).strip(" ,;.")


def split_dates(name: str) -> tuple[str, str | None]:
    """'Camus, Albert (1913-1960)' -> ('Camus, Albert', '1913–1960')."""
    m = _DATES.search(name)
    if not m:
        return clean(name), None
    dates = re.sub(r"\s*-\s*", "–", m.group(1)).replace("....", "").strip("– ") or None
    return clean(name[: m.start()]), dates


def display_and_sort(name: str) -> tuple[str, str]:
    """('Baruch Spinoza', 'Spinoza, Baruch') from either form."""
    name = clean(name)
    if name.count(",") == 1:
        last, first = (part.strip() for part in name.split(","))
        if first and last:
            return f"{first} {last}", f"{last}, {first}"
        name = first or last
    words = name.split(" ")
    if len(words) == 1:
        return name, name
    k = len(words) - 1
    while k > 1 and words[k - 1].lower() in PARTICLES:   # keep 'de' with 'Gaulle', but never empty the first name
        k -= 1
    first, last = " ".join(words[:k]), " ".join(words[k:])
    # library style puts the particle after the first name: 'Gaulle, Charles de'
    particles = [w for w in last.split(" ")[:-1] if w.lower() in PARTICLES]
    family = " ".join(last.split(" ")[len(particles):])
    sort = f"{family}, {first}" + (f" {' '.join(particles)}" if particles else "")
    return name, sort


def match_key(name: str) -> str:
    """Lowercase, no accents, no punctuation, words sorted: 'Spinoza, Baruch' and 'Baruch Spinoza' match."""
    name, _ = split_dates(name)
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return " ".join(sorted(re.findall(r"[a-z0-9]+", plain)))


def split_list(text: str | None) -> list[str]:
    """Several people written in one field: 'Gilles Deleuze, Félix Guattari' or 'Deleuze; Guattari'.

    'Lordon, Frédéric' (one name written family name first) stays one person.
    """
    if not text or not text.strip():
        return []
    parts = [p.strip() for p in re.split(r"\s*;\s*|\s+&\s+|\s+(?:et|and)\s+", text) if p.strip()]
    out: list[str] = []
    for part in parts:
        bare, _ = split_dates(part)
        pieces = [p.strip() for p in bare.split(",") if p.strip()]
        if len(pieces) == 2 and len(pieces[0].split()) == 1 and len(pieces[1].split()) <= 2:
            out.append(part)          # 'Lordon, Frédéric' or 'Camus, Albert (1913-1960)': one person
        else:
            out.extend(pieces)
    seen, unique = set(), []
    for name in out:
        key = match_key(name)
        if key and key not in seen:
            seen.add(key)
            unique.append(clean(name))
    return unique
