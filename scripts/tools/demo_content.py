#!/usr/bin/env python3
"""Fill the site with obviously fake posts to check the layout, then remove them.

This exists so template work does not require burning API calls or waiting for
a real publishing run. The text is placeholder on purpose - it must never reach
production, which is why --clean deletes every file it created.

    python scripts/tools/demo_content.py          # create
    python scripts/tools/demo_content.py --clean  # remove
"""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.engine.config import load  # noqa: E402
from scripts.engine.store import CONTENT  # noqa: E402
from scripts.engine.util import isoformat, slugify, utcnow  # noqa: E402

MARK = "__demo__"

HEADLINES = {
    "pt": [
        ("DEMO: modelo aberto de IA chega a marca de 1 trilhao de parametros", "modelos"),
        ("DEMO: investimento em startups de IA cresce 40% no trimestre", "mercado"),
        ("DEMO: industria brasileira acelera adocao de agentes de IA", "brasil"),
        ("DEMO: hospitais testam IA para triagem de exames de imagem", "aplicacoes"),
        ("DEMO: novo marco regulatorio de IA entra em consulta publica", "politica"),
        ("DEMO: laboratorio anuncia modelo multimodal de baixo custo", "modelos"),
    ],
    "en": [
        ("DEMO: open-weight AI model crosses the trillion-parameter mark", "modelos"),
        ("DEMO: funding for AI startups climbs 40% in the quarter", "mercado"),
        ("DEMO: Brazilian industry speeds up adoption of AI agents", "brasil"),
        ("DEMO: hospitals pilot AI triage for medical imaging", "aplicacoes"),
        ("DEMO: new AI regulation opens for public consultation", "politica"),
        ("DEMO: lab announces a low-cost multimodal model", "modelos"),
    ],
    "es": [
        ("DEMO: modelo abierto de IA llega al billon de parametros", "modelos"),
        ("DEMO: la inversion en startups de IA sube 40% en el trimestre", "mercado"),
        ("DEMO: la industria brasilena acelera el uso de agentes de IA", "brasil"),
        ("DEMO: hospitales prueban IA para triaje de imagenes medicas", "aplicacoes"),
        ("DEMO: nueva regulacion de IA entra en consulta publica", "politica"),
        ("DEMO: laboratorio anuncia un modelo multimodal de bajo costo", "modelos"),
    ],
}

LOREM = ("Texto de demonstracao usado apenas para conferir o layout. Nao e uma materia real "
         "e nao deve ser publicado. O conteudo verdadeiro e gerado pelo pipeline a partir de "
         "fatos confirmados em pelo menos duas fontes independentes, segundo a Reuters e a "
         "Associated Press, e passa pelo gate de qualidade antes de ir ao ar.")


def body(index: int) -> list[dict]:
    def p(text):
        return {"type": "p", "text": text, "items": []}
    return [
        p(LOREM), p(LOREM),
        {"type": "h2", "text": "Subtitulo de demonstracao", "items": []},
        p(LOREM), p(LOREM),
        {"type": "list", "text": "", "items": ["Item de exemplo um", "Item de exemplo dois",
                                               "Item de exemplo tres"]},
        {"type": "h2", "text": "Segundo subtitulo", "items": []},
        p(LOREM), p(LOREM),
    ]


def create(cfg) -> int:
    now = utcnow()
    made = 0
    for lang in cfg.languages:
        for i, (title, category) in enumerate(HEADLINES.get(lang, HEADLINES["en"])):
            slug = slugify(title)
            post = {
                MARK: True,
                "id": f"{lang}-{slug}",
                "lang": lang,
                "slug": slug,
                "story_id": f"demo-story-{i}",
                "title": title,
                "dek": "Linha de apoio de demonstracao, com uma frase explicando o fato.",
                "meta_description": (
                    "Materia de demonstracao usada para conferir o layout do site antes da "
                    "primeira publicacao real do pipeline automatizado."),
                "keyword": "inteligencia artificial",
                "category": category,
                "tags": ["ia", "demo", "layout"],
                "body": body(i),
                "image": {
                    "query": "abstract technology",
                    "alt": "Ilustracao abstrata de demonstracao representando tecnologia",
                    "path": "/assets/img/demo-placeholder.svg",
                    "credit": "Demo / Placeholder",
                    "author": "Demo",
                    "author_url": "#",
                    "provider": "Placeholder",
                    "source_url": "#",
                },
                "sources": [
                    {"name": "Reuters", "owner": "reuters", "url": "https://www.reuters.com/",
                     "title": "Fonte de demonstracao 1", "published_at": isoformat(now)},
                    {"name": "Associated Press", "owner": "ap", "url": "https://apnews.com/",
                     "title": "Fonte de demonstracao 2", "published_at": isoformat(now)},
                ],
                "facts_used": ["Fato de demonstracao confirmado por duas fontes."],
                "published_at": isoformat(now - timedelta(hours=i * 7)),
                "updated_at": isoformat(now - timedelta(hours=i * 7)),
                "status": "published",
            }
            path = CONTENT / lang / f"{slug}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
            made += 1
    placeholder()
    return made


def placeholder() -> None:
    """A neutral SVG so image slots are not empty while previewing."""
    from scripts.engine.config import ROOT
    path = ROOT / "assets" / "img" / "demo-placeholder.svg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 675" role="img" '
        'aria-label="Demo"><rect width="1200" height="675" fill="#E4E2DB"/>'
        '<text x="600" y="345" text-anchor="middle" font-family="monospace" font-size="34" '
        'fill="#8A887E">imagem de demonstracao</text></svg>\n', encoding="utf-8")


def clean(cfg) -> int:
    removed = 0
    for lang in cfg.languages:
        folder = CONTENT / lang
        if not folder.exists():
            continue
        for path in folder.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if data.get(MARK):
                path.unlink()
                removed += 1
    from scripts.engine.config import ROOT
    for extra in [ROOT / "assets" / "img" / "demo-placeholder.svg"]:
        if extra.exists():
            extra.unlink()
    # Drop the generated pages too, so a cleaned tree has no demo HTML left.
    for lang in cfg.languages:
        for folder in (ROOT / lang).glob("*"):
            index = folder / "index.html"
            if folder.is_dir() and index.exists() and "DEMO:" in index.read_text(encoding="utf-8"):
                for child in folder.rglob("*"):
                    child.unlink()
                folder.rmdir()
                removed += 1
    return removed


if __name__ == "__main__":
    cfg = load()
    if "--clean" in sys.argv:
        print(f"{clean(cfg)} arquivos de demonstracao removidos")
    else:
        print(f"{create(cfg)} materias de demonstracao criadas "
              f"(rode com --clean para remover)")
