"""Text and date helpers shared by the pipeline. No niche knowledge here."""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlparse

STOPWORDS = {
    "pt": {"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos",
           "nas", "um", "uma", "para", "por", "com", "que", "se", "ao", "aos", "sobre", "mais",
           "como", "foi", "sao", "ser", "sua", "seu", "pela", "pelo", "ja", "nao"},
    "en": {"a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "is", "are",
           "was", "were", "be", "by", "with", "that", "this", "it", "its", "as", "from", "has",
           "have", "will", "not", "but", "into", "after", "over", "new"},
    "es": {"el", "la", "los", "las", "de", "del", "y", "en", "un", "una", "para", "por", "con",
           "que", "se", "al", "sobre", "mas", "como", "fue", "son", "ser", "su", "sus", "no",
           "ya", "the"},
}


# --------------------------------------------------------------------------- text

def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def slugify(text: str, max_words: int = 8) -> str:
    """Short, ASCII, hyphenated slug. Short slugs are an SEO requirement here."""
    clean = strip_accents(text.lower())
    clean = re.sub(r"[^a-z0-9\s-]", " ", clean)
    words = [w for w in clean.split() if w]
    return "-".join(words[:max_words]) or "post"


def normalize(text: str) -> list[str]:
    return re.sub(r"[^\w\s]", " ", strip_accents(text.lower())).split()


def content_words(text: str, lang: str = "en") -> list[str]:
    stop = STOPWORDS.get(lang, STOPWORDS["en"])
    return [w for w in normalize(text) if len(w) > 2 and w not in stop]


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", strip_tags(text)))


def strip_tags(markup: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", markup, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return re.sub(r"\s+", " ", text).strip()


def shingles(text: str, size: int = 5) -> set[str]:
    words = normalize(text)
    return {" ".join(words[i:i + size]) for i in range(max(0, len(words) - size + 1))}


def similarity(a: str, b: str, size: int = 5) -> float:
    """Jaccard over word shingles - how much of `a` is recycled from `b`."""
    sa, sb = shingles(a, size), shingles(b, size)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa)


def longest_common_run(a: str, b: str) -> int:
    """Longest run of identical consecutive words shared by two texts."""
    wa, wb = normalize(a), normalize(b)
    if not wa or not wb:
        return 0
    index: dict[str, list[int]] = {}
    for j, word in enumerate(wb):
        index.setdefault(word, []).append(j)
    best = 0
    prev: dict[int, int] = {}
    for i, word in enumerate(wa):
        current: dict[int, int] = {}
        for j in index.get(word, ()):
            current[j] = prev.get(j - 1, 0) + 1
            best = max(best, current[j])
        prev = current
    return best


def title_overlap(a: str, b: str, lang: str = "en") -> float:
    """Symmetric overlap of meaningful words - used to cluster the same story."""
    wa, wb = set(content_words(a, lang)), set(content_words(b, lang))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def excerpt(text: str, limit: int = 160) -> str:
    text = strip_tags(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:. ") + "..."


# --------------------------------------------------------------------------- misc

def domain_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def fingerprint(*parts: str) -> str:
    digest = hashlib.sha1("␟".join(parts).encode("utf-8"))
    return digest.hexdigest()[:16]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_date(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for parser in (datetime.fromisoformat,):
        try:
            dt = parser(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


MONTHS = {
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
           "setembro", "outubro", "novembro", "dezembro"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"],
}


def format_date(dt: datetime, lang: str) -> str:
    months = MONTHS.get(lang, MONTHS["en"])
    month = months[dt.month - 1]
    if lang == "en":
        return f"{month} {dt.day}, {dt.year}"
    return f"{dt.day} de {month} de {dt.year}" if lang == "pt" else f"{dt.day} de {month} de {dt.year}"
