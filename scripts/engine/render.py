"""Step 8a - turning post records into HTML.

Jinja environment, the ad-slot helper, and the per-page context. The templates
know nothing about the niche: every label comes from site.config.yaml or i18n.
"""
from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from . import seo
from .config import ROOT, Config
from .i18n import LANGUAGE_NAMES, strings
from .util import format_date, parse_date, utcnow

THEMES = ("light", "dark", "system")

TEMPLATES = ROOT / "templates"

# The in-content ad follows this paragraph - counting paragraphs, not blocks, so
# the slot never lands between a heading and the text it introduces. One single
# in-content slot per article, by design.
AD_AFTER_PARAGRAPH = 3


def ad_slot_factory(cfg: Config, lang: str):
    ads = cfg.get("ads", {}) or {}

    def ad_slot(name: str) -> Markup:
        slot_id = (ads.get("slots") or {}).get(name, "")
        if not ads.get("enabled") or not ads.get("client_id") or not slot_id:
            # The position stays visible in the source so the slot can be filled
            # the day AdSense is approved, without touching the templates.
            return Markup(f"<!-- ad slot: {name} -->")
        label = (ads.get("labels") or {}).get(lang, "")
        label_html = f"<span class='ad-label'>{label}</span>" if label else ""
        client_id = ads["client_id"]
        return Markup(
            f'<div class="ad ad-{name}">'
            f"{label_html}"
            f'<ins class="adsbygoogle" style="display:block" '
            f'data-ad-client="{client_id}" data-ad-slot="{slot_id}" '
            f'data-ad-format="auto" data-full-width-responsive="true"></ins>'
            f"<script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script></div>")

    return ad_slot


def environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["date"] = lambda value, lang: format_date(parse_date(value) or utcnow(), lang)
    return env


def asset_version(name: str) -> str:
    """Hash curto do arquivo, para o endereço mudar quando o conteúdo mudar.

    Sem isso o navegador segue usando o CSS antigo com o HTML novo, e a página
    aparece sem estilo até o leitor forçar a atualização.
    """
    import hashlib
    path = ROOT / "assets" / name
    return hashlib.sha1(path.read_bytes()).hexdigest()[:8] if path.exists() else "0"


def base_context(cfg: Config, lang: str, **extra) -> dict:
    context = {
        "cfg": cfg,
        "site": cfg,
        "lang": lang,
        "html_lang": cfg.get(f"site.html_lang.{lang}", lang),
        "t": strings(lang),
        "categories": cfg.categories(lang),
        # Defaults para os templates (StrictUndefined) não quebrarem num site
        # cujo config ainda não tem anúncio ou newsletter.
        "ads": {"enabled": False, "client_id": "", "slots": {}, "labels": {},
                **(cfg.get("ads") or {})},
        "newsletter": {"enabled": False, "action": "", **(cfg.get("newsletter") or {})},
        "ad_slot": ad_slot_factory(cfg, lang),
        "asset_version": asset_version,
        "ad_after_paragraph": AD_AFTER_PARAGRAPH,
        "year": utcnow().year,
        "active_category": None,
        "is_home": False,
        "alternates": [],
        "og_image": None,
        "page_keywords": "",
        "legal_pages": [],
    }
    context.update(extra)
    context["x_default"] = seo.x_default(cfg, context["alternates"])
    context["lang_links"] = language_links(cfg, lang, context["alternates"],
                                           context.get("canonical"))
    context["default_theme"] = default_theme(cfg)
    return context


def default_theme(cfg: Config) -> str:
    theme = cfg.get("brand.default_theme", "light")
    return theme if theme in THEMES else "light"


def language_links(cfg: Config, lang: str, alternates: list[dict],
                   canonical: str | None = None) -> list[dict]:
    """Um link por idioma para o seletor do topo.

    Leva à mesma página na outra edição quando ela existe; quando não existe
    (editoria regional, por exemplo), leva à capa daquela edição. Nunca
    redireciona sozinho: quem decide o idioma é o leitor, e o Google indexa cada
    versão pela URL dela.
    """
    by_lang = {a["lang"]: a["url"] for a in alternates}
    return [{
        "lang": other,
        "code": other.upper(),
        "name": LANGUAGE_NAMES.get(other, other),
        "hreflang": cfg.get(f"site.html_lang.{other}", other),
        "url": by_lang.get(other) or (canonical if other == lang and canonical
                                      else cfg.url(seo.home_path(other))),
        "current": other == lang,
    } for other in cfg.languages]


def humanize(post: dict, lang: str) -> dict:
    published = parse_date(post.get("published_at"))
    updated = parse_date(post.get("updated_at"))
    return {
        **post,
        "published_human": format_date(published, lang) if published else "",
        "updated_human": format_date(updated, lang) if updated else "",
    }


def render(env: Environment, template: str, context: dict) -> str:
    return env.get_template(template).render(**context)
