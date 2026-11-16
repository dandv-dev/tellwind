"""Company names -> one entry per company.

Sources name the same company in many ways ("Stripe", "Stripe, Inc.",
"stripe.com", "STRIPE"). We reduce each name to a key (lowercase, no legal
suffix, no punctuation, no domain ending) and fuzzy-match keys we haven't seen
against the workspace's known companies. Every spelling is kept as an alias so
the UI can show how sources referred to it.
"""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

SUFFIXES = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "ltd",
    "limited",
    "llc",
    "plc",
    "pbc",
    "gmbh",
    "ag",
    "sa",
    "srl",
    "bv",
    "oy",
    "ab",
    "pte",
    "pty",
    "holdings",
    "group",
    "technologies",
    "technology",
    "labs",
}
TLDS = (".com", ".io", ".ai", ".dev", ".co", ".org", ".net", ".app")
FUZZY_MIN = 92


def norm_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode() or name
    s = s.lower().strip()
    s = re.sub(r"^the\s+", "", s)
    s = re.sub(r"\(.*?\)", " ", s)
    for tld in TLDS:
        if s.endswith(tld):
            s = s[: -len(tld)]
    s = re.sub(r"[^a-z0-9]+", " ", s)
    words = s.split()
    while len(words) > 1 and words[-1] in SUFFIXES:
        words.pop()
    return " ".join(words)


def display_name(names: list[str]) -> str:
    """Pick the shortest clean spelling seen as the canonical display name."""
    cleaned = []
    for n in names:
        n2 = re.sub(r",?\s+(inc|corp|ltd|llc|plc|gmbh)\.?$", "", n.strip(), flags=re.I)
        cleaned.append(n2 or n)
    return min(cleaned, key=lambda x: (len(x), x.lower() != x and x.upper() == x))


def resolve(name: str, known: dict[str, str]) -> str | None:
    """Return the key of a known company this name refers to, or None if new.

    ``known`` maps norm key -> company id.
    """
    key = norm_key(name)
    if not key:
        return None
    if key in known:
        return key
    if len(key) < 4:  # short names ("xAI", "Arc") fuzzy-match far too easily
        return None
    best, best_score = None, 0
    for k in known:
        if abs(len(k) - len(key)) > 6 or len(k) < 4:
            continue
        sc = fuzz.ratio(key, k)
        if sc > best_score:
            best, best_score = k, sc
    return best if best_score >= FUZZY_MIN else None
