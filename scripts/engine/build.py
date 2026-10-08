"""Step 8b - build the static site from the post records.

Reads content/<lang>/*.json plus content/pages/<lang>/*.json and writes the
whole public site: article pages, homes, category pages, institutional pages,
sitemaps, RSS, robots.txt, the manifest and the generated CSS.

The build is deterministic and idempotent: running it twice produces the same
bytes, which keeps git diffs meaningful.
"""
from __future__ import annotations

import json
import shutil
from datetime import timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from . import seo
from .config import ROOT, Config
from .i18n import strings
from .render import base_context, default_theme, environment, humanize, render
from .store import CONTENT, DATA, load_posts
from .util import excerpt, isoformat, parse_date, utcnow

PAGES = CONTENT / "pages"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _page_path(raw: str) -> str:
    """'/en/x/?ref=newsletter' e '/en/x' contam como a mesma página: '/en/x/'."""
    path = str(raw).split("?", 1)[0].split("#", 1)[0]
    return path if path.endswith("/") else f"{path}/"


def views() -> dict[str, int]:
    """Pageviews per URL path.

    Two sources, summed: data/analytics.json, which the "Métricas" workflow
    refreshes every week from GA4, and data/views.json, a manual export.
    """
    counts: dict[str, int] = {}

    def add(path: str, value) -> None:
        try:
            counts[_page_path(path)] = counts.get(_page_path(path), 0) + int(value)
        except (TypeError, ValueError):
            pass

    manual = DATA / "views.json"
    if manual.exists():
        try:
            for path, value in json.loads(manual.read_text(encoding="utf-8")).items():
                add(path, value)
        except (json.JSONDecodeError, AttributeError, OSError, UnicodeDecodeError):
            pass

    weekly = DATA / "analytics.json"
    if weekly.exists():
        try:
            raw = json.loads(weekly.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            raw = {}
        ga4 = raw.get("ga4") if isinstance(raw, dict) else None
        ga4 = ga4 if isinstance(ga4, dict) else {}
        by_path = ga4.get("views_by_path")
        if isinstance(by_path, dict):
            for path, value in by_path.items():
                add(path, value)
        elif isinstance(ga4.get("top_pages"), list):
            for row in ga4["top_pages"]:
                if isinstance(row, dict):
                    add(row.get("path", ""), row.get("page_views", 0))
    return counts


def owner_count(post: dict) -> int:
    """Quantos grupos independentes cobriram a pauta - o peso editorial dela."""
    return len({s.get("owner") or s.get("name") for s in post.get("sources", [])})


def rank_most_read(pool: list[dict], counts: dict[str, int], limit: int,
                   min_views: int = 1) -> list[dict]:
    """Só entra o que tem audiência medida acima do piso: "mais lidas" sem dado
    de audiência seria "mais recentes" com outro rótulo, e uma visita isolada
    em 28 dias é ruído, não leitura."""
    read = [p for p in pool if counts.get(p["url"], 0) >= max(min_views, 1)]
    read.sort(key=lambda p: (counts[p["url"]], p["published_at"]), reverse=True)
    return read[:limit]


def pick_highlights(pool: list[dict], limit: int, days: int) -> list[dict]:
    """Destaques da semana: o que mais veículos independentes cobriram.

    Popularidade já tem o bloco dela (mais lidas). Aqui o critério é peso
    editorial, e a melhor medida disso que o site tem é quantos grupos de
    mídia diferentes confirmaram a pauta. O primeiro item vira o card grande,
    então ele precisa ter foto.
    """
    cutoff = utcnow().timestamp() - days * 86400

    def recent(p: dict) -> bool:
        published = parse_date(p.get("published_at"))
        return bool(published) and published.timestamp() >= cutoff

    def weight(p: dict):
        return (owner_count(p), p["published_at"])

    # Sem completar com matéria antiga: um destaque de um mês atrás sob o
    # título "da semana" seria o bloco mentindo. Semana fraca, bloco menor.
    chosen = sorted((p for p in pool if recent(p)), key=weight, reverse=True)[:limit]
    with_image = [p for p in chosen if p.get("image", {}).get("path")]
    if with_image and chosen[0] is not with_image[0]:
        chosen.remove(with_image[0])
        chosen.insert(0, with_image[0])
    return chosen


# --------------------------------------------------------------------- pieces

def build_posts(env, cfg: Config, pool: list[dict], out: Path, nav: list[dict]) -> list[dict]:
    built = []
    for post in pool:
        enriched = humanize(post, post["lang"])
        context = base_context(
            cfg, post["lang"],
            post=enriched,
            page_title=enriched["title_tag"],
            page_description=enriched["meta_description"],
            page_keywords=enriched["keywords"],
            canonical=enriched["canonical"],
            alternates=enriched["alternates"],
            active_category=enriched.get("category"),
            og_type="article",
            og_image=cfg.url(enriched["image"]["path"]) if enriched.get("image", {}).get("path") else None,
            og_image_alt=enriched.get("image", {}).get("alt", ""),
            legal_pages=legal_links(cfg, post["lang"]),
            categories=nav,
        )
        write(out / post["lang"] / post["slug"] / "index.html",
              render(env, "article.html", context))
        built.append(enriched)
    return built


def home_blocks(cfg: Config, posts: list[dict], nav: list[dict], counts: dict[str, int]) -> dict:
    """Monta os blocos da home na ordem do config, sem repetir matéria.

    Cada bloco só recebe o que ainda não apareceu acima dele. Sem isso, com
    poucas matérias no site, a mesma manchete saía no destaque, nas mais lidas
    e no módulo da editoria — e a home de 7 matérias parecia ter 3.
    """
    used: set[str] = set()

    def fresh() -> list[dict]:
        return [p for p in posts if p["slug"] not in used]

    def take(items: list[dict]) -> list[dict]:
        used.update(p["slug"] for p in items)
        return items

    def sections(per_column: int, columns: int) -> list[dict]:
        """As editorias com matéria mais recente ganham as colunas; a ordem na
        tela segue o config, para cada editoria ter lugar previsível."""
        per_column, columns = max(per_column, 0), max(columns, 0)
        candidates = []
        for position, category in enumerate(nav):
            in_category = [p for p in fresh() if p.get("category") == category["key"]][:per_column]
            if in_category:
                candidates.append((in_category[0]["published_at"], position, category, in_category))
        chosen = sorted(candidates, key=lambda c: c[0], reverse=True)[:columns]
        return [{**category, "posts": take(items)}
                for _, _, category, items in sorted(chosen, key=lambda c: c[1])]

    most_read_count = cfg.get("editorial.most_read_count", 5)
    min_views = cfg.get("editorial.most_read_min_views", 2)
    module_count = cfg.get("editorial.topic_module_count", 4)
    blocks: dict = {}
    for block in cfg.get("editorial.home_layout", []):
        if block in blocks:
            continue  # o config.validate já recusa; aqui só não consome matéria
        if block in ("today", "hero"):
            count = cfg.get("editorial.today_count", 4) if block == "today" else 4
            items = take(fresh()[:count])
            blocks[block] = {"lead": items[0] if items else None, "rest": items[1:]}
        elif block == "feed":
            # Ordem de escolha, do critério mais escasso para o mais farto: os
            # destaques precisam ser da semana, as mais lidas precisam de
            # audiência medida, e a linha do tempo aceita qualquer coisa recente.
            # Na ordem inversa, a linha do tempo esvaziava os outros dois.
            highlights = take(pick_highlights(fresh(), cfg.get("editorial.highlights_count", 3),
                                              cfg.get("editorial.highlights_days", 7)))
            most_read = take(rank_most_read(fresh(), counts, most_read_count, min_views))
            timeline = take(fresh()[:cfg.get("editorial.timeline_count", 7)])
            blocks["feed"] = {"timeline": timeline, "highlights": highlights,
                              "most_read": most_read}
        elif block == "most_read":
            blocks["most_read"] = take(rank_most_read(fresh(), counts, most_read_count, min_views))
        elif block == "by_section":
            blocks["by_section"] = sections(cfg.get("editorial.section_posts", 3),
                                            cfg.get("editorial.section_columns", module_count))
        elif block == "topic_modules":
            blocks["topic_modules"] = sections(3, module_count)
    return blocks


def recent_times(posts: list[dict], days: int = 7) -> list[str]:
    cutoff = utcnow() - timedelta(days=days)
    return [p["published_at"] for p in posts
            if (parse_date(p.get("published_at")) or cutoff) > cutoff]


def home_stats(cfg: Config, times: list[str]) -> dict:
    """Contagem do topo na hora do build, no fuso do site. Vale para quem lê
    sem JavaScript; com ele, o site.js refaz a conta pelo relógio do leitor."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(cfg.get("site.timezone", "UTC"))
    except Exception:
        tz = None
    today = utcnow().astimezone(tz).date()
    days = [parse_date(t).astimezone(tz).date() for t in times if parse_date(t)]
    return {"today": sum(1 for d in days if d == today), "week": len(days)}


def build_home(env, cfg: Config, lang: str, posts: list[dict], out: Path, nav: list[dict]) -> None:
    context = base_context(
        cfg, lang,
        is_home=True,
        blocks=home_blocks(cfg, posts, nav, views()),
        latest_published=posts[0]["published_at"] if posts else "",
        # Datas da última semana para os contadores do topo. O HTML fica no ar
        # por dias; o JavaScript recalcula "hoje" pelo relógio de quem lê.
        recent_times=recent_times(posts),
        stats=home_stats(cfg, recent_times(posts)),
        edition_count=len(cfg.languages),
        today_label=cfg.localized("editorial.today_label", lang, ""),
        highlights_label=cfg.localized("editorial.highlights_label", lang, ""),
        home_layout=cfg.get("editorial.home_layout", []),
        schema_website=seo.website_schema(cfg, lang),
        page_title=f"{cfg.get('site.name')} - {cfg.localized('site.tagline', lang)}",
        page_description=cfg.localized("site.description", lang),
        page_keywords=cfg.localized("niche.term", lang),
        canonical=cfg.url(seo.home_path(lang)),
        alternates=seo.home_alternates(cfg),
        og_image=cfg.url("/assets/logo/icon-512.png"),
        legal_pages=legal_links(cfg, lang),
        categories=nav,
    )
    write(out / lang / "index.html", render(env, "home.html", context))


def nav_categories(cfg: Config, lang: str, posts: list[dict]) -> list[dict]:
    """Editorias que já têm ao menos uma matéria.

    Um menu que leva a "Ainda não há matérias publicadas nesta editoria" faz o
    site parecer abandonado no dia em que ele mais precisa parecer vivo. A
    editoria volta ao menu sozinha assim que a primeira matéria dela sai.
    """
    com_materia = {p.get("category") for p in posts}
    return [c for c in cfg.categories(lang) if c["key"] in com_materia]


def prune_categories(cfg: Config, lang: str, out: Path, nav: list[dict]) -> list[str]:
    """Apaga páginas de editorias que não existem mais neste idioma.

    Sem isso, tirar uma editoria do config deixa a página antiga no ar: órfã do
    menu, mas acessível e indexável pelo Google. Aconteceu quando "IA no Brasil"
    passou a ser exclusiva da edição em português.
    """
    root = out / lang / seo.CATEGORY_PREFIX
    if not root.exists():
        return []
    validas = {c["slug"] for c in nav}
    removidas = []
    for folder in root.iterdir():
        if folder.is_dir() and folder.name not in validas:
            shutil.rmtree(folder)
            removidas.append(f"{lang}/{seo.CATEGORY_PREFIX}/{folder.name}")
    return removidas


def build_categories(env, cfg: Config, lang: str, posts: list[dict], out: Path, nav: list[dict],
                     nav_keys: dict[str, set[str]]) -> None:
    t = strings(lang)
    for category in nav:
        in_category = [p for p in posts if p.get("category") == category["key"]]
        # Só liga às edições onde a editoria tem página de verdade: hreflang
        # para um 404 faz o Google descartar o conjunto inteiro.
        alts = [a for a in seo.category_alternates(cfg, category["key"])
                if category["key"] in nav_keys.get(a["lang"], set())]
        description = t["category_description"].format(
            label=category["label"], niche=cfg.localized("niche.term", lang))
        context = base_context(
            cfg, lang,
            category=category,
            posts=in_category,
            active_category=category["key"],
            page_title=f"{category['label']}{cfg.localized('seo.title_suffix', lang, '')}",
            page_description=description,
            page_keywords=f"{category['label']}, {cfg.localized('niche.term', lang)}",
            canonical=cfg.url(seo.category_path(lang, category["slug"])),
            alternates=alts if len(alts) > 1 else [],
            legal_pages=legal_links(cfg, lang),
            categories=nav,
        )
        write(out / lang / seo.CATEGORY_PREFIX / category["slug"] / "index.html",
              render(env, "category.html", context))


def load_pages(lang: str) -> list[dict]:
    folder = PAGES / lang
    if not folder.exists():
        return []
    pages = []
    for path in sorted(folder.glob("*.json")):
        pages.append(json.loads(path.read_text(encoding="utf-8")))
    return pages


def legal_links(cfg: Config, lang: str) -> list[dict]:
    return [{"title": p["title"], "url": seo.page_path(lang, p["slug"])}
            for p in load_pages(lang)]


def build_pages(env, cfg: Config, lang: str, out: Path, nav: list[dict],
                pages_by_lang: dict[str, list[dict]]) -> list[dict]:
    built = []
    for page in pages_by_lang.get(lang, []):
        enriched = humanize(page, lang)
        context = base_context(
            cfg, lang,
            page=enriched,
            page_title=f"{page['title']}{cfg.localized('seo.title_suffix', lang, '')}",
            page_description=page.get("description", ""),
            canonical=cfg.url(seo.page_path(lang, page["slug"])),
            alternates=seo.page_alternates(cfg, page, pages_by_lang),
            legal_pages=legal_links(cfg, lang),
            categories=nav,
        )
        write(out / lang / page["slug"] / "index.html", render(env, "page.html", context))
        built.append(page)
    return built


# ------------------------------------------------------------------ feeds etc

def build_sitemap(cfg: Config, lang: str, posts: list[dict], pages: list[dict], out: Path,
                  nav: list[dict]) -> None:
    urls = [(cfg.url(seo.home_path(lang)), isoformat(utcnow()), "daily", "1.0")]
    for category in nav:
        urls.append((cfg.url(seo.category_path(lang, category["slug"])),
                     isoformat(utcnow()), "daily", "0.7"))
    for post in posts:
        urls.append((post["canonical"], post.get("updated_at", post["published_at"]),
                     "monthly", "0.9"))
    for page in pages:
        urls.append((cfg.url(seo.page_path(lang, page["slug"])),
                     page.get("updated_at", isoformat(utcnow())), "yearly", "0.3"))

    body = "\n".join(
        f"  <url><loc>{escape(loc)}</loc><lastmod>{escape(mod)}</lastmod>"
        f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>"
        for loc, mod, freq, prio in urls)
    write(out / f"sitemap-{lang}.xml",
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          f"{body}\n</urlset>\n")


def build_sitemap_index(cfg: Config, out: Path) -> None:
    entries = "\n".join(
        f"  <sitemap><loc>{cfg.url(f'/sitemap-{lang}.xml')}</loc>"
        f"<lastmod>{isoformat(utcnow())}</lastmod></sitemap>"
        for lang in cfg.languages)
    write(out / "sitemap.xml",
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
          f"{entries}\n</sitemapindex>\n")


def build_rss(cfg: Config, lang: str, posts: list[dict], out: Path) -> None:
    items = []
    for post in posts[:30]:
        published = parse_date(post["published_at"])
        items.append(
            "    <item>\n"
            f"      <title>{escape(post['title'])}</title>\n"
            f"      <link>{escape(post['canonical'])}</link>\n"
            f"      <guid isPermaLink=\"true\">{escape(post['canonical'])}</guid>\n"
            f"      <description>{escape(post.get('meta_description', ''))}</description>\n"
            f"      <category>{escape(post.get('category_label', ''))}</category>\n"
            f"      <pubDate>{published.strftime('%a, %d %b %Y %H:%M:%S +0000') if published else ''}</pubDate>\n"
            "    </item>")
    write(out / f"rss-{lang}.xml",
          '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n  <channel>\n'
          f"    <title>{escape(str(cfg.get('site.name')))} - {escape(cfg.localized('site.tagline', lang))}</title>\n"
          f"    <link>{escape(cfg.url(seo.home_path(lang)))}</link>\n"
          f"    <description>{escape(cfg.localized('site.description', lang))}</description>\n"
          f"    <language>{cfg.get(f'site.html_lang.{lang}', lang)}</language>\n"
          f"    <lastBuildDate>{utcnow().strftime('%a, %d %b %Y %H:%M:%S +0000')}</lastBuildDate>\n"
          f'    <atom:link href="{escape(cfg.url(f"/rss-{lang}.xml"))}" rel="self" type="application/rss+xml"/>\n'
          + "\n".join(items) + "\n  </channel>\n</rss>\n")


def build_robots(cfg: Config, out: Path) -> None:
    lines = ["User-agent: *", "Allow: /", ""]
    for lang in cfg.languages:
        lines.append(f"Sitemap: {cfg.url(f'/sitemap-{lang}.xml')}")
    lines.append(f"Sitemap: {cfg.url('/sitemap.xml')}")
    write(out / "robots.txt", "\n".join(lines) + "\n")


def build_manifest(cfg: Config, out: Path) -> None:
    write(out / "site.webmanifest", json.dumps({
        "name": cfg.get("site.name"),
        "short_name": cfg.get("site.name"),
        "description": cfg.localized("site.description", cfg.default_language),
        "start_url": seo.home_path(cfg.default_language),
        "display": "standalone",
        "background_color": cfg.get("brand.paper"),
        "theme_color": cfg.get("brand.primary"),
        "icons": [
            {"src": "/assets/logo/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/assets/logo/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }, ensure_ascii=False, indent=2) + "\n")


def build_root(cfg: Config, out: Path) -> None:
    """Root URL sends visitors to the default language; hreflang tells Google
    that the three versions are equals, not a redirect chain."""
    default = cfg.default_language
    alts = "\n".join(
        f'<link rel="alternate" hreflang="{cfg.get(f"site.html_lang.{l}", l)}" '
        f'href="{cfg.url(seo.home_path(l))}">'
        for l in cfg.languages)
    write(out / "index.html",
          f"""<!DOCTYPE html>
<html lang="{cfg.get(f'site.html_lang.{default}', default)}">
<head>
<meta charset="utf-8">
<title>{cfg.get('site.name')} - {cfg.localized('site.tagline', default)}</title>
<link rel="canonical" href="{cfg.url(seo.home_path(default))}">
{alts}
<link rel="alternate" hreflang="x-default" href="{cfg.url(seo.home_path(default))}">
<meta http-equiv="refresh" content="0; url={seo.home_path(default)}">
</head>
<body>
<p><a href="{seo.home_path(default)}">{cfg.get('site.name')}</a></p>
<script>
  var supported = {json.dumps(cfg.languages)};
  var preferred = (navigator.languages || [navigator.language || ""])
    .map(function (l) {{ return String(l).slice(0, 2).toLowerCase(); }})
    .filter(function (l) {{ return supported.indexOf(l) !== -1; }})[0];
  location.replace("/" + (preferred || "{default}") + "/");
</script>
</body>
</html>
""")


def build_favicon(cfg: Config, out: Path) -> None:
    """Browsers, feed readers and link previews ask for /favicon.ico at the root
    regardless of what the <link> tags say. Keep a copy there."""
    source = out / "assets" / "logo" / "favicon.ico"
    if source.exists():
        shutil.copyfile(source, out / "favicon.ico")


def build_css(env, cfg: Config, out: Path) -> None:
    # CSS is not HTML: rendering it with autoescape on would turn the font
    # stack's quotes into entities.
    plain = env.overlay(autoescape=False)
    css = plain.get_template("site.css.j2").render(
        b=cfg.get("brand", {}), default_theme=default_theme(cfg),
        section_columns=max(1, cfg.get("editorial.section_columns",
                                       cfg.get("editorial.topic_module_count", 4))))
    write(out / "assets" / "css" / "site.css", css)


# ----------------------------------------------------------------------- main

def normalize(post: dict, cfg: Config) -> dict:
    """Resolve uma vez o que todo o resto do build assume.

    - Editoria: uma pauta "IA no Brasil" escrita em inglês vai para a editoria
      de reserva daquele idioma. Resolvendo aqui, menu, página da editoria,
      capa e rótulo concordam sobre onde ela está.
    - Imagem: matéria sem foto ainda tem o campo, vazio, e os templates tratam
      a ausência em vez de quebrar.
    """
    category = cfg.category_or_fallback(post.get("category", ""), post["lang"])
    image = post.get("image") if isinstance(post.get("image"), dict) else {}
    return {**post,
            "category": category["key"] if category else post.get("category", ""),
            "image": {"path": "", "alt": "", "credit": "", **image}}


def run(cfg: Config, out: Path = ROOT) -> dict:
    env = environment()
    everything = [normalize(p, cfg) for lang in cfg.languages for p in load_posts(lang)
                  if p.get("status") == "published"]
    enriched_all = [seo.enrich(p, everything, cfg) for p in everything]

    by_lang = {}
    for lang in cfg.languages:
        posts = [p for p in enriched_all if p["lang"] == lang]
        posts.sort(key=lambda p: p["published_at"], reverse=True)
        by_lang[lang] = posts
    navs = {lang: nav_categories(cfg, lang, by_lang[lang]) for lang in cfg.languages}
    nav_keys = {lang: {c["key"] for c in nav} for lang, nav in navs.items()}
    pages_by_lang = {lang: load_pages(lang) for lang in cfg.languages}

    stats = {"posts": 0, "pages": 0, "languages": {}}
    for lang in cfg.languages:
        posts, nav = by_lang[lang], navs[lang]
        built = build_posts(env, cfg, posts, out, nav)
        pages = build_pages(env, cfg, lang, out, nav, pages_by_lang)
        build_home(env, cfg, lang, [humanize(p, lang) for p in posts], out, nav)
        build_categories(env, cfg, lang, [humanize(p, lang) for p in posts], out, nav, nav_keys)
        for removida in prune_categories(cfg, lang, out, nav):
            print(f"  - editoria sem materia, pagina removida: /{removida}/")
        build_sitemap(cfg, lang, posts, pages, out, nav)
        build_rss(cfg, lang, posts, out)
        stats["languages"][lang] = {"posts": len(built), "pages": len(pages)}
        stats["posts"] += len(built)
        stats["pages"] += len(pages)

    build_sitemap_index(cfg, out)
    build_robots(cfg, out)
    build_manifest(cfg, out)
    build_root(cfg, out)
    build_favicon(cfg, out)
    build_css(env, cfg, out)
    return stats


if __name__ == "__main__":
    from .config import load
    cfg = load()
    stats = run(cfg)
    for lang, counts in stats["languages"].items():
        print(f"  /{lang}/  {counts['posts']} materias, {counts['pages']} paginas")
    print(f"total: {stats['posts']} materias, {stats['pages']} paginas institucionais")
