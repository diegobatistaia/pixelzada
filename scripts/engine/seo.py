"""Step 5 - on-page SEO, per language.

URLs, canonical, hreflang between the three versions of the same story, JSON-LD
(NewsArticle + BreadcrumbList), Open Graph, and the internal links that connect
a post to related posts on the site.
"""
from __future__ import annotations

import json

from .config import Config
from .util import content_words, excerpt, parse_date, strip_tags

CATEGORY_PREFIX = "c"


# json.dumps leaves "<" alone, so a headline containing "</script>" would close
# the block early and spill markup into the page. Rewriting the three characters
# that matter as JSON unicode escapes keeps the JSON valid and the page intact.
BACKSLASH = chr(92)
SCRIPT_SAFE = str.maketrans({ch: f"{BACKSLASH}u{ord(ch):04x}" for ch in "<>&"})


def _json_ld(data: dict) -> str:
    """JSON-LD safe to drop inside a <script> tag."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).translate(SCRIPT_SAFE)


# ------------------------------------------------------------------------ urls

def post_path(post: dict) -> str:
    return f"/{post['lang']}/{post['slug']}/"


def home_path(lang: str) -> str:
    return f"/{lang}/"


def category_path(lang: str, slug: str) -> str:
    return f"/{lang}/{CATEGORY_PREFIX}/{slug}/"


def page_path(lang: str, slug: str) -> str:
    return f"/{lang}/{slug}/"


def absolute(cfg: Config, path: str) -> str:
    return cfg.url(path)


# -------------------------------------------------------------------- hreflang

def alternates(post: dict, everything: list[dict], cfg: Config) -> list[dict]:
    """The same story in the other languages, for hreflang."""
    out = []
    for other in everything:
        if other.get("story_id") and other["story_id"] == post.get("story_id"):
            out.append({
                "lang": other["lang"],
                "hreflang": cfg.get(f"site.html_lang.{other['lang']}", other["lang"]),
                "url": absolute(cfg, post_path(other)),
            })
    out.sort(key=lambda a: a["lang"])
    return out


def home_alternates(cfg: Config) -> list[dict]:
    return [{"lang": lang,
             "hreflang": cfg.get(f"site.html_lang.{lang}", lang),
             "url": absolute(cfg, home_path(lang))}
            for lang in cfg.languages]


def category_alternates(cfg: Config, key: str) -> list[dict]:
    """A mesma editoria nas outras edições, pela chave - o slug muda por idioma.

    Editoria regional (languages: [pt]) só tem a própria versão: apontar a
    seção sobre o Brasil para outra editoria da edição em inglês diria ao Google
    que as duas páginas são a mesma coisa, e não são.
    """
    out = []
    for lang in cfg.languages:
        category = cfg.category(key, lang)
        if category:
            out.append({"lang": lang,
                        "hreflang": cfg.get(f"site.html_lang.{lang}", lang),
                        "url": absolute(cfg, category_path(lang, category["slug"]))})
    return out if len(out) > 1 else []


def page_alternates(cfg: Config, page: dict, pages_by_lang: dict[str, list[dict]]) -> list[dict]:
    """Páginas institucionais equivalentes (sobre/about/acerca), pelo campo `key`."""
    key = page.get("key")
    if not key:
        return []
    out = []
    for lang in cfg.languages:
        for other in pages_by_lang.get(lang, []):
            if other.get("key") == key:
                out.append({"lang": lang,
                            "hreflang": cfg.get(f"site.html_lang.{lang}", lang),
                            "url": absolute(cfg, page_path(lang, other["slug"]))})
                break
    return out if len(out) > 1 else []


def x_default(cfg: Config, alts: list[dict]) -> str | None:
    """Versão para quem fala um idioma que o site não tem.

    É a mesma página no idioma padrão, não a home: mandar quem chegou numa
    matéria para a capa jogaria fora o motivo de ele ter chegado.
    """
    if not alts:
        return None
    by_lang = {a["lang"]: a["url"] for a in alts}
    return by_lang.get(cfg.default_language) or alts[0]["url"]


# --------------------------------------------------------------- related posts

def related(post: dict, pool: list[dict], cfg: Config) -> list[dict]:
    """Internal links: same category first, then keyword overlap, newest first.

    Quando nada é de fato relacionado, cai para as matérias mais recentes do
    mesmo idioma. É o que um site de notícias faz de verdade - e é melhor que a
    alternativa que essa regra criava antes: uma matéria boa parada na fila
    porque o assunto dela ainda não tinha vizinho no site.
    """
    limit = cfg.get("editorial.related_posts", 3)
    mine = set(post.get("tags", [])) | set(content_words(post["title"], post["lang"]))
    candidates = [o for o in pool
                  if o["slug"] != post["slug"] and o["lang"] == post["lang"]]

    scored = []
    for other in candidates:
        theirs = set(other.get("tags", [])) | set(content_words(other["title"], other["lang"]))
        score = (2 if other.get("category") == post.get("category") else 0) + len(mine & theirs)
        if score:
            scored.append((score, other.get("published_at", ""), other))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    chosen = [o for _, _, o in scored[:limit]]

    if not chosen:
        chosen = sorted(candidates, key=lambda o: o.get("published_at", ""), reverse=True)[:limit]

    def card(o: dict) -> dict:
        category = cfg.category_or_fallback(o.get("category", ""), o["lang"]) or {}
        return {"title": o["title"], "url": post_path(o), "category": o.get("category", ""),
                "category_label": category.get("label", ""),
                "image": (o.get("image") or {}).get("path", ""),
                "published_at": o.get("published_at", "")}

    return [card(o) for o in chosen]


# ----------------------------------------------------------------------- meta

def title_tag(post: dict, cfg: Config) -> str:
    suffix = cfg.localized("seo.title_suffix", post["lang"], "")
    title = post["title"]
    return title if title.endswith(suffix) else f"{title}{suffix}"


def body_text(post: dict) -> str:
    parts = []
    for block in post.get("body", []):
        if block["type"] == "list":
            parts.extend(block.get("items", []))
        else:
            parts.append(block.get("text", ""))
    return strip_tags(" ".join(p for p in parts if p))


def keywords(post: dict, cfg: Config) -> str:
    niche = cfg.localized("niche.term", post["lang"], "")
    return ", ".join(dict.fromkeys([post.get("keyword", ""), niche, *post.get("tags", [])]).keys())


# --------------------------------------------------------------------- json-ld

def publisher(cfg: Config) -> dict:
    return {
        "@type": cfg.get("seo.organization_type", "Organization"),
        "name": cfg.get("site.name"),
        "url": cfg.base_url,
        "logo": {
            "@type": "ImageObject",
            "url": absolute(cfg, cfg.get("brand.logo.lockup", "")),
        },
    }


def news_article_schema(post: dict, cfg: Config, alts: list[dict]) -> str:
    url = absolute(cfg, post_path(post))
    published = parse_date(post.get("published_at"))
    data = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": post["title"][:110],
        "description": post.get("meta_description", ""),
        "inLanguage": cfg.get(f"site.html_lang.{post['lang']}", post["lang"]),
        "datePublished": post.get("published_at"),
        "dateModified": post.get("updated_at", post.get("published_at")),
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "url": url,
        "author": {"@type": "Organization", "name": cfg.get("site.name"), "url": cfg.base_url},
        "publisher": publisher(cfg),
        "keywords": keywords(post, cfg),
        "articleSection": post.get("category_label", post.get("category", "")),
        "wordCount": len(body_text(post).split()),
        "isAccessibleForFree": True,
    }
    if post.get("image", {}).get("path"):
        data["image"] = [absolute(cfg, post["image"]["path"])]
    if post.get("sources"):
        data["citation"] = [{"@type": "CreativeWork", "name": s["name"], "url": s["url"]}
                            for s in post["sources"]]
    if alts:
        data["workTranslation"] = [{"@type": "NewsArticle", "url": a["url"],
                                    "inLanguage": a["hreflang"]}
                                   for a in alts if a["lang"] != post["lang"]]
    if published:
        data["dateline"] = published.strftime("%Y-%m-%d")
    return _json_ld(data)


def breadcrumb_schema(post: dict, cfg: Config) -> str:
    trail = [
        {"name": cfg.get("site.name"), "url": absolute(cfg, home_path(post["lang"]))},
    ]
    if post.get("category_label") and post.get("category_slug"):
        trail.append({"name": post["category_label"],
                      "url": absolute(cfg, category_path(post["lang"], post["category_slug"]))})
    trail.append({"name": post["title"], "url": absolute(cfg, post_path(post))})
    return _json_ld({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": t["name"], "item": t["url"]}
            for i, t in enumerate(trail)],
    })


def website_schema(cfg: Config, lang: str) -> str:
    return _json_ld({
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": cfg.get("site.name"),
        "alternateName": cfg.localized("site.tagline", lang, ""),
        "url": absolute(cfg, home_path(lang)),
        "inLanguage": cfg.get(f"site.html_lang.{lang}", lang),
        "description": cfg.localized("site.description", lang, ""),
        "publisher": publisher(cfg),
    })


# ------------------------------------------------------------------ enrichment

def enrich(post: dict, pool: list[dict], cfg: Config) -> dict:
    """Attach everything the templates need. Pure function of post + pool."""
    lang = post["lang"]
    category = cfg.category_or_fallback(post.get("category", ""), lang) or {}
    alts = alternates(post, pool, cfg)
    enriched = {
        **post,
        "url": post_path(post),
        "canonical": absolute(cfg, post_path(post)),
        "category_label": category.get("label", ""),
        "category_slug": category.get("slug", ""),
        "category_color": category.get("color", cfg.get("brand.primary")),
        "category_url": category_path(lang, category["slug"]) if category else "",
        "alternates": alts,
        "related": related(post, pool, cfg),
        # How many published posts exist to link to; the gate uses it to skip
        # the internal-links requirement while the site is still empty.
        "pool_size": len([p for p in pool if p.get("lang") == lang and p.get("slug") != post["slug"]]),
        "title_tag": title_tag(post, cfg),
        "keywords": keywords(post, cfg),
        "reading_time": max(1, round(len(body_text(post).split()) / 220)),
        "summary": post.get("dek") or excerpt(body_text(post), 180),
    }
    enriched["schema_news_article"] = news_article_schema(enriched, cfg, alts)
    enriched["schema_breadcrumb"] = breadcrumb_schema(enriched, cfg)
    return enriched
