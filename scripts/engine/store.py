"""Persistence for the pipeline: published index, dedupe log, exception queue.

Everything is plain JSON on disk so the site stays a static repo with no
database, and so the daily supervision can be done by reading files.

Layout
    data/published.json        every post ever published (dedupe + related links)
    data/seen.json             fingerprints of stories already processed
    data/gate-log.json         one row per gate decision (feeds the ramp check)
    data/queue/<id>.json       exception queue - what needs the human 10 minutes
    content/<lang>/<slug>.json the post record itself (source of truth for HTML)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import ROOT
from .util import isoformat, utcnow

DATA = ROOT / "data"
QUEUE = DATA / "queue"
CONTENT = ROOT / "content"


def _read(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = path.with_suffix(path.suffix + ".corrupt")
        path.replace(backup)
        print(f"  ! {path.name} ilegível, movido para {backup.name}")
        return fallback


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------- seen

def seen_fingerprints() -> set[str]:
    return set(_read(DATA / "seen.json", []))


def mark_seen(fingerprints) -> None:
    _write(DATA / "seen.json", sorted(seen_fingerprints() | set(fingerprints)))


# --------------------------------------------------------------------- published

def published() -> list[dict]:
    return _read(DATA / "published.json", [])


def record_published(post: dict) -> None:
    rows = [p for p in published() if p.get("id") != post["id"]]
    rows.append({
        "id": post["id"],
        "lang": post["lang"],
        "slug": post["slug"],
        "title": post["title"],
        "category": post["category"],
        "published_at": post["published_at"],
        "story_id": post.get("story_id", ""),
        "url": post.get("url", ""),
    })
    rows.sort(key=lambda p: p["published_at"], reverse=True)
    _write(DATA / "published.json", rows)


def used_today(languages, tz_name: str, now=None) -> dict[str, int]:
    """Matérias do dia de hoje (no fuso do site) por idioma.

    Conta o publicado hoje e o rascunho ainda pendente: o teto diário é de quem
    escreve, e um rascunho que o Finalizar ainda não publicou já gastou a vaga.
    """
    from zoneinfo import ZoneInfo
    from .util import parse_date
    tz = ZoneInfo(tz_name)
    today = (now or utcnow()).astimezone(tz).date()
    counts = {}
    for lang in languages:
        n = 0
        for post in load_posts(lang):
            if post.get("status") == "draft":
                n += 1
                continue
            when = parse_date(post.get("published_at"))
            if when and when.astimezone(tz).date() == today:
                n += 1
        counts[lang] = n
    return counts


def published_in(lang: str) -> list[dict]:
    return [p for p in published() if p["lang"] == lang]


# ------------------------------------------------------------------------ posts

def post_path(lang: str, slug: str) -> Path:
    return CONTENT / lang / f"{slug}.json"


def save_post(post: dict) -> Path:
    path = post_path(post["lang"], post["slug"])
    _write(path, post)
    return path


def load_post(lang: str, slug: str) -> dict | None:
    return _read(post_path(lang, slug), None)


def load_posts(lang: str) -> list[dict]:
    folder = CONTENT / lang
    if not folder.exists():
        return []
    posts = [p for p in (_read(f, None) for f in sorted(folder.glob("*.json"))) if p]
    posts.sort(key=lambda p: p.get("published_at", ""), reverse=True)
    return posts


# ------------------------------------------------------------------------ queue

def queue_key(item: dict) -> str:
    """Nome de arquivo único para um item da fila.

    Os rascunhos escritos pela Routine não trazem `id` - o campo é opcional no
    formato. Sem derivar uma chave aqui, três reprovações no mesmo dia gravavam
    todas em `item.json` e só a última sobrevivia.
    """
    return item.get("id") or f"{item.get('lang', 'xx')}-{item.get('slug', 'item')}"


def enqueue(item: dict, reasons: list[str]) -> Path:
    payload = dict(item)
    payload["queued_at"] = isoformat(utcnow())
    payload["reasons"] = reasons
    path = QUEUE / f"{queue_key(item)}.json"
    _write(path, payload)
    return path


def queue_items() -> list[dict]:
    if not QUEUE.exists():
        return []
    return [p for p in (_read(f, None) for f in sorted(QUEUE.glob("*.json"))) if p]


def dequeue(item_id: str) -> bool:
    path = QUEUE / f"{item_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False


# --------------------------------------------------------------------- gate log

def log_gate(entry: dict) -> None:
    rows = _read(DATA / "gate-log.json", [])
    rows.append({"at": isoformat(utcnow()), **entry})
    _write(DATA / "gate-log.json", rows[-2000:])


def gate_pass_rate(window_days: int) -> tuple[float, int]:
    """(pass rate, sample size) over the last `window_days` days."""
    from datetime import timedelta
    cutoff = utcnow() - timedelta(days=window_days)
    rows = [r for r in _read(DATA / "gate-log.json", [])
            if (r.get("at", "") or "") >= isoformat(cutoff)]
    if not rows:
        return (0.0, 0)
    passed = sum(1 for r in rows if r.get("passed"))
    return (passed / len(rows), len(rows))
