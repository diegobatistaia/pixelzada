"""Step 1 - collection.

Pulls recent items from the configured RSS feeds, keeps only what matches the
niche keywords, drops anything already processed, and clusters items that are
telling the same story. A cluster is what the next step tries to verify.
"""
from __future__ import annotations

import json
import re
import warnings
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .config import Config, bot_user_agent
from .store import seen_fingerprints
from .util import (content_words, domain_of, excerpt, fingerprint, isoformat, parse_date,
                   strip_tags, title_overlap, utcnow)


warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

HTML_HEADERS = {"User-Agent": bot_user_agent()}


def _page_date(soup: BeautifulSoup):
    """Data de publicação declarada pela própria página, ou None."""
    for attrs in ({"property": "article:published_time"}, {"name": "article:published_time"},
                  {"itemprop": "datePublished"}, {"name": "date"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and parse_date(tag.get("content")):
            return parse_date(tag.get("content"))
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except ValueError:
            continue
        for node in data if isinstance(data, list) else [data]:
            if isinstance(node, dict) and parse_date(node.get("datePublished")):
                return parse_date(node.get("datePublished"))
    tag = soup.find("time", attrs={"datetime": True})
    return parse_date(tag["datetime"]) if tag else None


def _url_date(url: str, pattern: str | None):
    match = re.search(pattern, url) if pattern else None
    if not match:
        return None
    year = int(match["y"])
    try:
        return datetime(year + 2000 if year < 100 else year, int(match["m"]), int(match["d"]),
                        12, tzinfo=timezone.utc)
    except ValueError:
        return None


def fetch_listing(source: dict, timeout: int = 20) -> list[dict]:
    """Empresa sem RSS: lê a página de notícias e abre os links mais recentes.

    `link_prefix` diz quais links da página são matérias (ex.: "/news/");
    `exclude` tira caminhos que não são matéria (ex.: "/category/"). Só entra o
    que tem data: a da própria página ou, se a página não declara, a que a
    empresa põe no endereço (`url_date`, regex com os grupos y, m e d).
    """
    try:
        page = requests.get(source["url"], headers=HTML_HEADERS, timeout=timeout)
        page.raise_for_status()
    except requests.RequestException as exc:
        print(f"  ! {source['name']}: {exc}")
        return []
    base = urlparse(source["url"])
    prefix = source.get("link_prefix", "/")
    links: list[str] = []
    for a in BeautifulSoup(page.text, "html.parser").find_all("a", href=True):
        url = urljoin(source["url"], a["href"]).split("#")[0].split("?")[0].rstrip("/")
        parts = urlparse(url)
        if (parts.netloc == base.netloc and parts.path.startswith(prefix)
                and parts.path.rstrip("/") != prefix.rstrip("/") and url not in links
                and not any(x in parts.path for x in source.get("exclude", []))):
            links.append(url)
    items = []
    for link in links[:source.get("max_links", 20)]:
        try:
            resp = requests.get(link, headers=HTML_HEADERS, timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        published = _page_date(soup) or _url_date(link, source.get("url_date"))
        og_title = soup.find("meta", attrs={"property": "og:title"})
        title = strip_tags((og_title.get("content") if og_title else "")
                           or (soup.title.string if soup.title else "") or "").strip()
        title = title.split(" | ")[0].strip()  # "Título | Mistral AI" -> "Título"
        og_desc = (soup.find("meta", attrs={"property": "og:description"})
                   or soup.find("meta", attrs={"name": "description"}))
        if not published or not title:
            continue
        items.append(_item(source, link, title,
                           strip_tags(og_desc.get("content", "") if og_desc else ""), published))
    return items


def _item(source: dict, link: str, title: str, summary: str, published) -> dict:
    return {
        "title": title,
        "url": link,
        "summary": summary,
        "published_at": isoformat(published) if published else "",
        "published_dt": published,
        "source": source["name"],
        "owner": source["owner"],
        "lang": source.get("lang", "en"),
        "tier": source.get("tier", 2),
        "kind": source.get("kind", "press"),
        "domain": domain_of(link),
    }


def fetch_feed(source: dict, timeout: int = 20) -> list[dict]:
    if source.get("type") == "html":
        return fetch_listing(source, timeout)
    parsed = feedparser.parse(source["url"], agent=HTML_HEADERS["User-Agent"])
    if parsed.bozo and not parsed.entries:
        print(f"  ! {source['name']}: {parsed.get('bozo_exception', 'feed ilegível')}")
        return []
    items = []
    for entry in parsed.entries:
        link = entry.get("link") or ""
        title = strip_tags(entry.get("title") or "").strip()
        if not link or not title:
            continue
        summary = strip_tags(entry.get("summary") or entry.get("description") or "")
        published = (parse_date(entry.get("published") or entry.get("updated"))
                     or parse_date(entry.get("published_parsed")))
        items.append(_item(source, link, title, summary, published))
    return items


def blocked(item: dict, cfg: Config) -> bool:
    """Promocao e cupom nao viram materia, venha de onde vier."""
    haystack = f"{item['title']} {item['summary']}".lower()
    return any(bad.lower() in haystack for bad in cfg.get("keywords.exclude", []))


def matches_keywords(item: dict, cfg: Config) -> bool:
    haystack = f"{item['title']} {item['summary']}".lower()
    if blocked(item, cfg):
        return False
    return any(good.lower() in haystack for good in cfg.get("keywords.include", []))


def is_recent(item: dict, hours: int) -> bool:
    if not item.get("published_dt"):
        return False
    age = (utcnow() - item["published_dt"]).total_seconds() / 3600
    return 0 <= age <= hours


def cluster(items: list[dict], threshold: float = 0.5) -> list[dict]:
    """Group items that describe the same event.

    Overlap of meaningful title words is a blunt instrument, but it is
    deliberate: the cluster is only a candidate. Nothing is treated as
    confirmed until verify.py checks the facts against independent owners.
    """
    clusters: list[dict] = []
    for item in sorted(items, key=lambda i: (-i["tier"], i["published_at"]), reverse=True):
        for group in clusters:
            if title_overlap(item["title"], group["items"][0]["title"], item["lang"]) >= threshold:
                group["items"].append(item)
                break
        else:
            clusters.append({"items": [item]})

    out = []
    for group in clusters:
        # A primaria lidera a pauta. O titulo e o resumo saem dela, nao do
        # veiculo que a leu - e a diferenca entre noticiar o anuncio e
        # noticiar quem falou do anuncio.
        members = sorted(group["items"],
                         key=lambda i: (i.get("kind") != "primary", i["tier"], i["published_at"]))
        lead = members[0]
        owners = sorted({m["owner"] for m in members})
        out.append({
            "id": fingerprint(lead["title"], owners[0]),
            "title": lead["title"],
            "summary": excerpt(lead["summary"], 400),
            "lang_hint": lead["lang"],
            "owners": owners,
            "owner_count": len(owners),
            "primary_owners": sorted({m["owner"] for m in members
                                      if m.get("kind") == "primary"}),
            "items": members,
            "first_seen": isoformat(utcnow()),
            "keywords": content_words(lead["title"], lead["lang"])[:12],
        })
    out.sort(key=lambda c: (-c["owner_count"], c["items"][0]["published_at"]), reverse=False)
    out.sort(key=lambda c: c["owner_count"], reverse=True)
    return out


def run(cfg: Config, *, include_seen: bool = False) -> list[dict]:
    sources = cfg.get("sources.rss", [])
    hours = cfg.get("collection.lookback_hours", 48)
    hours_primary = cfg.get("collection.lookback_hours_primary", hours)
    min_title = cfg.get("collection.min_title_chars", 25)
    seen = set() if include_seen else seen_fingerprints()

    raw: list[dict] = []
    for source in sources:
        items = fetch_feed(source)
        primaria = source.get("kind") == "primary"
        janela = hours_primary if primaria else hours
        kept = [i for i in items
                if len(i["title"]) >= min_title and is_recent(i, janela)
                # Um blog corporativo de IA nao precisa dizer "IA" para ser
                # sobre IA - ele fala em primeira pessoa. Exigir palavra-chave
                # da primaria descarta justamente o anuncio original.
                and (primaria or matches_keywords(i, cfg))
                and not blocked(i, cfg)]
        raw.extend(kept)
        print(f"  {source['name']:28} {len(kept):3}/{len(items):3} itens no filtro")

    unique, urls = [], set()
    for item in raw:
        key = fingerprint(item["url"])
        if item["url"] in urls or key in seen:
            continue
        urls.add(item["url"])
        item["fingerprint"] = key
        unique.append(item)

    clusters = cluster(unique, cfg.get("collection.cluster_threshold", 0.42))
    limit = cfg.get("collection.max_candidates", 60)
    return clusters[:limit]


if __name__ == "__main__":
    from .config import load
    cfg = load()
    print(f"Coletando de {len(cfg.get('sources.rss', []))} feeds "
          f"(últimas {cfg.get('collection.lookback_hours')}h)\n")
    clusters = run(cfg, include_seen=True)
    print(f"\n{len(clusters)} pautas candidatas\n")
    for c in clusters[:12]:
        mark = ("OK " if c["owner_count"] >= cfg.get("quality_gate.min_independent_sources", 2)
                else "1P " if c.get("primary_owners") else "-- ")
        print(f"{mark}[{c['owner_count']} fontes] {c['title'][:78]}")
        print(f"      {', '.join(c['owners'])}")
