#!/usr/bin/env python3
"""Check everything that can be checked without spending an API call.

Config validity, interface strings, template rendering, SEO output and every
branch of the quality gate. Run it after touching the engine or the config.

    python scripts/tools/selfcheck.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.engine import gate, seo  # noqa: E402
from scripts.engine.images import query_ladder  # noqa: E402
from scripts.engine.store import queue_key  # noqa: E402
from scripts.pipeline.run import (adsense_readiness, draft_problems,  # noqa: E402
                                  missing_primary_for)
from scripts.engine.config import ConfigError, ROOT, load  # noqa: E402
from scripts.engine.i18n import missing_keys, strings  # noqa: E402
from scripts.engine.render import base_context, environment, humanize, render  # noqa: E402
from scripts.engine.util import isoformat, longest_common_run, similarity, utcnow  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  ok    {label}")
    else:
        print(f"  FALHA {label}{(' - ' + detail) if detail else ''}")
        FAILURES.append(label)


def first_category(cfg) -> str:
    return cfg.categories(cfg.default_language)[0]["key"]


def official_source(cfg) -> dict:
    """Primeira fonte oficial (kind: primary) do config, no formato de `sources`."""
    src = next(s for s in cfg.get("sources.rss", []) if s.get("kind") == "primary")
    return {"name": src["name"], "owner": src["owner"], "url": src["url"], "title": "A"}


def fixture(cfg, **overrides) -> dict:
    body = [{"type": "p", "text": " ".join(["palavra"] * 120), "items": []},
            {"type": "p", "text": " ".join(["texto"] * 120), "items": []},
            {"type": "h2", "text": "Um subtitulo", "items": []},
            {"type": "p", "text": " ".join(["conteudo"] * 200), "items": []},
            {"type": "p", "text": "Segundo a Reuters, o numero foi confirmado. "
                                  + " ".join(["fecho"] * 250), "items": []}]
    post = {
        "id": "pt-fixture", "lang": "pt", "slug": "fixture", "story_id": "s1",
        "title": "Titulo de teste do gate de qualidade", "dek": "Linha de apoio.",
        "meta_description": "M" * 155, "keyword": "inteligencia artificial",
        "category": first_category(cfg), "tags": ["tag"], "body": body,
        "image": {"path": "/assets/img/x.jpg", "alt": "Descricao suficientemente longa da imagem",
                  "credit": "Autor / Unsplash"},
        "sources": [{"name": "Reuters", "owner": "reuters", "url": "https://r.com/", "title": "A"},
                    {"name": "Associated Press", "owner": "ap", "url": "https://ap.com/", "title": "B"}],
        "published_at": isoformat(utcnow()), "updated_at": isoformat(utcnow()),
        "status": "published",
    }
    post.update(overrides)
    return post


def main() -> int:
    print("Config")
    try:
        cfg = load()
        check("site.config.yaml carrega e valida", True)
    except ConfigError as exc:
        check("site.config.yaml carrega e valida", False, str(exc))
        return 1

    check("idiomas configurados", len(cfg.languages) >= 1)
    check("toda edicao tem ao menos 3 editorias",
          all(len(cfg.categories(l)) >= 3 for l in cfg.languages))
    # Editoria regional nao pode vazar para as outras edicoes: um leitor
    # americano nao tem por que ver uma secao sobre o Brasil.
    regionais = [c for c in cfg.get("editorial.categories", []) if c.get("languages")]
    check("editoria regional so aparece no idioma dela",
          all(cfg.category(c["slug"][cfg.default_language], outro) is None
              for c in regionais for outro in cfg.languages
              if outro not in c["languages"]),
          "uma editoria com languages: [..] apareceu em idioma fora da lista")
    check("editoria fora do idioma cai na de reserva",
          all(cfg.category_or_fallback(c["slug"][cfg.default_language], outro) is not None
              for c in regionais for outro in cfg.languages
              if outro not in c["languages"]))
    check("gate exige 2+ fontes independentes",
          cfg.get("quality_gate.min_independent_sources") >= 2)
    check("todas as fontes RSS têm owner",
          all(s.get("owner") for s in cfg.get("sources.rss", [])))
    owners = [s["owner"] for s in cfg.get("sources.rss", [])]
    check("há pelo menos 2 grupos independentes por idioma",
          all(len({s["owner"] for s in cfg.get("sources.rss", []) if s.get("lang") == l}) >= 2
              for l in cfg.languages))

    print("\nTextos de interface")
    gaps = missing_keys()
    check("nenhum idioma com string faltando", not gaps, str(gaps))
    for lang in cfg.languages:
        check(f"strings de {lang} carregam", bool(strings(lang).most_read))

    print("\nAssets do logo")
    logos = [cfg.get(f"brand.logo.{k}") for k in ("lockup", "lockup_dark", "icon", "icon_light",
                                                   "icon_dark", "favicon_svg", "favicon_ico")]
    for rel in [l for l in logos if l] + ["/assets/logo/icon-192.png", "/assets/logo/icon-512.png"]:
        path = ROOT / rel.lstrip("/")
        check(f"{path.name} existe e não está vazio", path.exists() and path.stat().st_size > 200)
    check("webfonts auto-hospedadas",
          len(list((ROOT / "assets" / "fonts").glob("*.woff2"))) >= 2)

    print("\nSEO")
    post = seo.enrich(fixture(cfg), [], cfg)
    check("URL do post no formato /lang/slug/", post["url"] == "/pt/fixture/")
    check("canonical absoluto", post["canonical"].startswith("https://"))
    check("schema NewsArticle gerado", '"@type":"NewsArticle"' in post["schema_news_article"])
    check("JSON-LD escapa < e >", "<" not in post["schema_news_article"])
    check("title tag leva o sufixo de nicho",
          cfg.get("site.name") in post["title_tag"] and post["title"] in post["title_tag"])
    other = fixture(cfg, lang="en", slug="fixture-en", id="en-fixture")
    alts = seo.alternates(post, [post, other], cfg)
    check("hreflang liga as versões da mesma pauta", len(alts) == 2)

    print("\nGate de qualidade")
    verdict = gate.evaluate(post, cfg, [])
    check("post correto passa", verdict["passed"], "; ".join(verdict["reasons"]))

    cases = {
        "fonte única reprova": fixture(cfg, sources=[
            {"name": "Reuters", "owner": "reuters", "url": "https://r.com/", "title": "A"}]),
        "texto curto reprova": fixture(cfg, body=[{"type": "p", "text": "curto", "items": []}]),
        "meta description fora da faixa reprova": fixture(cfg, meta_description="curta"),
        "sem H2 reprova": fixture(cfg, body=[
            {"type": "p", "text": " ".join(["palavra"] * 700), "items": []}]),
        "alt-text ausente reprova": fixture(cfg, image={"path": "/x.jpg", "alt": "",
                                                        "credit": "A / Unsplash"}),
        "imagem sem atribuição reprova": fixture(cfg, image={
            "path": "/x.jpg", "alt": "Descricao suficientemente longa da imagem", "credit": ""}),
    }
    # Com images.provider: none o gate não exige imagem, então esses dois casos
    # só fazem sentido quando há banco de imagens configurado.
    if cfg.get("images.provider", "none") == "none":
        cases = {k: v for k, v in cases.items() if "imagem" not in k and "alt-text" not in k}
    elif not cfg.get("images.attribution_required", True):
        cases.pop("imagem sem atribuição reprova", None)
    for label, broken in cases.items():
        enriched = seo.enrich(broken, [], cfg)
        check(label, not gate.evaluate(enriched, cfg, [])["passed"])

    # The internal-links rule must not block the site's very first posts, but
    # must apply once there is something to link to.
    neighbour = fixture(cfg, slug="vizinho", id="pt-vizinho", title="Outra materia",
                        tags=["assunto-sem-relacao"], category="politica")
    lonely = seo.enrich(fixture(cfg), [neighbour], cfg)
    check("site vazio não reprova por link interno",
          gate.evaluate(seo.enrich(fixture(cfg), [], cfg), cfg, [])["passed"])
    check("sem parente tematico, cai para as mais recentes",
          len(lonely["related"]) >= 1, "materia boa nao pode parar por falta de vizinho")

    source_text = " ".join(["conteudo"] * 200)
    copied = seo.enrich(fixture(cfg), [], cfg)
    check("cópia da fonte reprova por similaridade",
          not gate.evaluate(copied, cfg, [source_text])["passed"])
    check("similaridade detecta reciclagem",
          similarity("um dois tres quatro cinco seis", "um dois tres quatro cinco seis") == 1.0)
    check("trecho literal é medido",
          longest_common_run("a b c d e f g", "z a b c d e f g z") == 7)

    print("\nRascunhos do modo Routine")
    frase = ("Segundo a TechCrunch, o fato principal foi confirmado por duas fontes "
             "independentes antes da publicação, e este texto valida a estrutura. ")
    corpo = [{"type": "p", "text": frase * 6, "items": []} for _ in range(5)]
    corpo.insert(2, {"type": "h2", "text": "Subtítulo", "items": []})
    rascunho = {
        "lang": "pt", "slug": "s", "story_id": "x", "title": "T", "dek": "d",
        "keyword": "ia", "category": first_category(cfg), "tags": ["tag"], "body": corpo,
        "meta_description": ("Matéria de teste usada para validar toda a estrutura do arquivo "
                             "de rascunho que é aceita pelo pipeline automatizado do site de "
                             "notícias sobre IA hoje."),
        "image": {"query": "tech", "alt": "Ilustração abstrata representando tecnologia"},
        "sources": [{"name": "TechCrunch", "owner": "techcrunch", "url": "u", "title": "t"},
                    {"name": "MIT Technology Review", "owner": "mit-tr", "url": "u", "title": "t"}],
        "status": "draft",
    }
    check("rascunho correto passa", not draft_problems(rascunho, cfg),
          "; ".join(draft_problems(rascunho, cfg)))
    quebrados = {
        "campo faltando reprova": {k: v for k, v in rascunho.items() if k != "body"},
        "categoria inexistente reprova": {**rascunho, "category": "nao-existe"},
        "fonte unica reprova": {**rascunho, "sources": rascunho["sources"][:1]},
        "comecar com H2 reprova": {**rascunho, "body": corpo[2:] + corpo[:2]},
        "alt-text curto reprova": {**rascunho, "image": {"query": "t", "alt": "curto"}},
    }
    for label, broken in quebrados.items():
        check(label, bool(draft_problems(broken, cfg)))

    # Dois bugs que só apareceram no primeiro fechamento real.
    print("\nFila e busca de imagem")
    check("fila usa chave única por idioma",
          queue_key({"lang": "pt", "slug": "x"}) != queue_key({"lang": "es", "slug": "x"}))
    check("fila não colapsa em 'item' sem id",
          queue_key({"lang": "pt", "slug": "x"}) == "pt-x")
    ladder = query_ladder({"image": {"query": "server room data breach cybersecurity abstract"}}, cfg)
    check("busca de imagem afunila até um termo genérico", len(ladder) >= 4 and len(ladder[-1].split()) <= 3,
          str(ladder))
    check("busca de imagem não repete tentativa", len(ladder) == len(set(ladder)))
    check("query vazia ainda tenta o termo do nicho",
          len(query_ladder({"image": {"query": ""}}, cfg)) >= 1)

    print("\nHierarquia das fontes")
    primarias = [s for s in cfg.get("sources.rss", []) if s.get("kind") == "primary"]
    check("existem fontes primárias configuradas", len(primarias) >= 5,
          f"só {len(primarias)}")
    check("primárias declaram o dono real",
          all(s.get("owner") for s in primarias))
    from collections import Counter
    por_dono = Counter(s["owner"] for s in cfg.get("sources.rss", []))
    check("feeds do mesmo grupo dividem o owner", max(por_dono.values()) >= 2,
          "veículos do mesmo grupo precisam contar como uma fonte só")

    pauta = {"sources": [
        {"name": "OpenAI", "owner": "openai", "kind": "primary"},
        {"name": "TechCrunch", "owner": "techcrunch", "kind": "press"}]}
    so_imprensa = {"sources": [{"name": "TechCrunch", "owner": "techcrunch"}]}
    com_primaria = {"sources": [{"name": "OpenAI", "owner": "openai"},
                                {"name": "TechCrunch", "owner": "techcrunch"}]}
    check("citar só o intermediário reprova",
          bool(missing_primary_for(pauta, so_imprensa)))
    check("citar a primária passa",
          not missing_primary_for(pauta, com_primaria))
    check("pauta sem primária não exige nada",
          not missing_primary_for({"sources": [{"name": "X", "owner": "x", "kind": "press"}]},
                                  so_imprensa))

    print("\nExceção de fonte única (autorização manual do dono)")
    unica = fixture(cfg, sources=[{"name": "Reuters", "owner": "reuters",
                                   "url": "https://openai.com/x", "title": "A"}])
    check("uma fonte sem autorização ainda reprova",
          not gate.evaluate(seo.enrich(unica, [], cfg), cfg, [])["passed"])
    autorizada = {**unica, "editorial_override": "single_source_authorized"}
    check("a mesma matéria, autorizada, passa",
          gate.evaluate(seo.enrich(autorizada, [], cfg), cfg, [])["passed"])
    check("run.check também respeita a autorização",
          not draft_problems({**rascunho, "sources": rascunho["sources"][:1],
                              "editorial_override": "single_source_authorized"}, cfg))
    html_normal = render(env := environment(), "article.html", base_context(
        cfg, "pt", post=humanize(seo.enrich(fixture(cfg), [], cfg), "pt"),
        page_title="t", page_description="d", page_keywords="k",
        canonical="https://example.com/pt/x/", alternates=[], og_type="article",
        legal_pages=[]))
    html_unico = render(env, "article.html", base_context(
        cfg, "pt", post=humanize(seo.enrich(autorizada, [], cfg), "pt"),
        page_title="t", page_description="d", page_keywords="k",
        canonical="https://example.com/pt/x/", alternates=[], og_type="article",
        legal_pages=[]))
    check("matéria normal mostra o aviso de checagem cruzada",
          "duas fontes independentes" in html_normal)
    check("matéria de fonte única mostra o aviso correto, não o de checagem cruzada",
          "autorização direta da direção" in html_unico
          and "duas fontes independentes" not in html_unico)

    print("\nAnúncio oficial como fonte única (decisão do dono, 05/10/2026)")
    oficial_src = official_source(cfg)
    oficial = fixture(cfg, sources=[oficial_src],
                      fonte_unica="anuncio_oficial")
    oficial["body"] = [{**b, "text": b["text"].replace("Reuters", oficial_src["name"])} for b in oficial["body"]]
    check("anúncio oficial marcado passa no gate",
          gate.evaluate(seo.enrich(oficial, [], cfg), cfg, [])["passed"])
    check("a mesma fonte oficial sem a marca reprova",
          not gate.evaluate(seo.enrich({**oficial, "fonte_unica": None}, [], cfg), cfg, [])["passed"])
    imprensa = {**oficial, "sources": [{"name": "Reuters", "owner": "reuters",
                                        "url": "https://r.com/", "title": "A"}]}
    check("marca de anúncio oficial com fonte de imprensa reprova",
          not gate.evaluate(seo.enrich(imprensa, [], cfg), cfg, [])["passed"])
    check("run.check aceita o anúncio oficial marcado",
          not [p for p in draft_problems({**rascunho, "sources": [oficial_src],
                                          "fonte_unica": "anuncio_oficial"}, cfg)
               if "fonte" in p and "independente" in p or "oficial" in p])
    html_oficial = render(environment(), "article.html", base_context(
        cfg, "pt", post=humanize(seo.enrich(oficial, [], cfg), "pt"),
        page_title="t", page_description="d", page_keywords="k",
        canonical="https://example.com/pt/x/", alternates=[], og_type="article",
        legal_pages=[]))
    check("matéria de anúncio oficial mostra o aviso próprio",
          "anúncio oficial da própria empresa" in html_oficial
          and "duas fontes independentes" not in html_oficial)
    html_listing = [s for s in cfg.get("sources.rss", []) if s.get("type") == "html"]
    check("páginas sem RSS declaram link_prefix",
          all(s.get("link_prefix") for s in html_listing))

    print("\nAviso de AdSense")
    ads = adsense_readiness(cfg)
    check("avaliação roda e devolve os critérios", len(ads["criterios"]) == 4)
    check("não anuncia prontidão com o site novo", not ads["pronto"],
          "site com poucos dias e poucas matérias não deveria dar como pronto")
    check("cada critério diz o atual e o exigido",
          all(atual and exigido for atual, exigido, _ in ads["criterios"]))

    print("\nTemplates")
    env = environment()
    try:
        html = render(env, "article.html", base_context(
            cfg, "pt", post=humanize(post, "pt"), page_title=post["title_tag"],
            page_description=post["meta_description"], page_keywords=post["keywords"],
            canonical=post["canonical"], alternates=post["alternates"], og_type="article",
            legal_pages=[]))
        check("article.html renderiza", "<h1>" in html)
        check("ad slot in-content presente", "ad slot: in_content" in html)
        check("hreflang no head", 'rel="alternate"' in html)
        check("fontes listadas no rodapé da matéria", "sources-title" in html)
    except Exception as exc:  # noqa: BLE001 - the point is to report any failure
        check("article.html renderiza", False, f"{type(exc).__name__}: {exc}")

    print("\nCapa, idiomas e tema")
    from scripts.engine import build as site_build  # noqa: E402
    from scripts.engine.build import home_blocks, load_pages  # noqa: E402
    pages = {l: load_pages(l) for l in cfg.languages}
    keys = {l: {p.get("key") for p in pages[l]} for l in cfg.languages}
    check("toda página institucional tem key",
          all(p.get("key") for l in cfg.languages for p in pages[l]))
    check("as mesmas páginas institucionais existem em todos os idiomas",
          len({frozenset(k) for k in keys.values()}) == 1, str(keys))
    check("tema padrão válido", cfg.get("brand.default_theme", "light") in ("light", "dark", "system"))
    for lang in cfg.languages:
        check(f"rótulo do bloco do dia em {lang}",
              "today" not in cfg.get("editorial.home_layout", [])
              or bool(cfg.localized("editorial.today_label", lang, "")))
    pool = [humanize({**seo.enrich(fixture(cfg, slug=f"p{i}", id=f"pt-p{i}",
                                             category=c, published_at=isoformat(utcnow())), [], cfg)},
                     "pt")
            for i, c in enumerate([c["key"] for c in cfg.categories("pt")][:4] * 5)]
    nav = site_build.nav_categories(cfg, "pt", pool)
    blocks = home_blocks(cfg, pool, nav, {})
    shown = [p["slug"] for b in blocks.values() if isinstance(b, dict)
             for key in ("rest", "timeline", "highlights", "most_read")
             for p in (b.get(key) or [])]
    shown += [b["lead"]["slug"] for b in blocks.values() if isinstance(b, dict) and b.get("lead")]
    shown += [p["slug"] for m in blocks.get("by_section", []) for p in m["posts"]]
    check("capa não repete matéria entre blocos", len(shown) == len(set(shown)))
    html_home = render(env, "home.html", base_context(
        cfg, "pt", blocks=blocks, latest_published=pool[0]["published_at"], is_home=True,
        today_label="Hoje", highlights_label="", home_layout=cfg.get("editorial.home_layout", []),
        schema_website="{}", page_title="t", page_description="d",
        canonical="https://example.com/pt/", alternates=seo.home_alternates(cfg),
        legal_pages=[], categories=nav, recent_times=[],
        stats={"today": 0, "week": 0}, edition_count=len(cfg.languages)))
    check("home.html renderiza", "today-title" in html_home)
    check("seletor de idioma com um link por idioma (ou nenhum, com um idioma só)",
          len(cfg.languages) == 1 or all(f'hreflang="{cfg.get(f"site.html_lang.{l}", l)}" lang=' in html_home for l in cfg.languages))
    check("botão de tema presente", "data-theme-toggle" in html_home)

    print("\nRodadas do dia e teto compartilhado")
    from datetime import datetime, timezone
    from scripts.pipeline.run import run_budget
    tz = "America/Sao_Paulo"
    def brt(h): return datetime(2026, 10, 5, h + 3, 5, tzinfo=timezone.utc)
    horas = cfg.run_hours
    check("há mais de uma rodada por dia configurada", len(horas) >= 2, str(horas))
    check("três rodadas dividem o teto de 3 em 1 por rodada",
          [run_budget(r, [7, 12, 18], tz, brt(h)) for r, h in ((3, 7), (2, 12), (1, 18))] == [1, 1, 1])
    check("rodada sem pauta devolve a vaga para a seguinte",
          run_budget(3, [7, 12, 18], tz, brt(12)) == 2 and run_budget(3, [7, 12, 18], tz, brt(18)) == 3)
    check("teto atingido zera a rodada", run_budget(0, [7, 12, 18], tz, brt(12)) == 0)
    check("nunca passa do que resta", run_budget(1, [7, 12, 18], tz, brt(7)) == 1)
    from datetime import datetime as _dt
    from scripts.pipeline.run import same_local_day
    check("briefing das 7h ainda vale no meio-dia do mesmo dia",
          same_local_day(brt(7), tz, now=brt(12)))
    check("briefing das 22h de ontem não vale às 7h de hoje",
          not same_local_day(_dt(2026, 10, 5, 1, 0, tzinfo=timezone.utc), tz, now=brt(7)))
    from scripts.pipeline.run import local_today
    check("coleta antecipada das 6h já divide o teto pelas três rodadas",
          run_budget(4, [7, 12, 18], tz, brt(6)) == 2)
    check("depois das 21h de Brasília ainda é o mesmo dia para o teto",
          str(local_today(tz, now=_dt(2026, 11, 1, 1, 0, tzinfo=timezone.utc))) == "2026-10-31")
    check("dia é o do fuso do site, não o UTC",
          same_local_day(_dt(2026, 10, 5, 2, 0, tzinfo=timezone.utc), tz,
                         now=_dt(2026, 10, 5, 0, 30, tzinfo=timezone.utc)))

    print("\nInstagram")
    import copy
    import json
    from datetime import datetime
    from scripts.social import instagram as ig, pauta as pt
    exemplo = json.loads((ROOT / "social" / "exemplo-pauta.json").read_text(encoding="utf-8"))
    check("pauta de exemplo passa na conferência", pt.conferir(exemplo) == [], "; ".join(pt.conferir(exemplo)))
    ruim = copy.deepcopy(exemplo)
    ruim["legenda"]["hashtags"] = ["#gta6", "#games"]
    ruim["legenda"]["corpo"].append("Leia em pixelzada.com.br")
    erros = " ".join(pt.conferir(ruim))
    check("pauta: hashtag da marca, genérica e link na legenda reprovam",
          "#pixelzada" in erros and "genérica" in erros and "link" in erros, erros)

    def ig_pauta(slug, gta, criado, **extra):
        p = copy.deepcopy(exemplo)
        p.update(slug=slug, gta6=gta, criado=criado, tipo="noticia", **extra)
        return p

    def ig_em(hhmm):
        return datetime.fromisoformat(f"2026-10-08T{hhmm}:00-03:00")

    fila = [ig_pauta("gta-a", True, "2026-10-08T06:00:00-03:00"),
            ig_pauta("outro-a", False, "2026-10-08T06:30:00-03:00"),
            ig_pauta("velha", False, "2026-10-06T06:30:00-03:00")]
    check("8h publica GTA 6", (ig.escolher(ig_em("08:03"), fila) or {}).get("slug") == "gta-a")
    check("antes da hora não publica", ig.escolher(ig_em("07:40"), fila) is None)
    check("10h publica outro jogo", (ig.escolher(ig_em("10:20"), fila) or {}).get("slug") == "outro-a")
    check("notícia vencida não sai", all((ig.escolher(ig_em(h), fila[2:]) or {}).get("slug") != "velha"
                                         for h in ("10:05", "14:05")))
    check("horário das 14h não gasta GTA 6 que vai faltar às 18h e 21h",
          ig.escolher(ig_em("14:05"), fila[:1]) is None)
    feito = ig_pauta("gta-b", True, "2026-10-08T06:00:00-03:00", status="publicado",
                     publicado={"data": "2026-10-08", "horario": "18:00", "em": "2026-10-08T18:04:00-03:00"})
    check("horário já preenchido não publica de novo", ig.escolher(ig_em("18:40"), [feito, fila[0]]) is None)
    check("19h30 faz o Reel do carrossel do dia",
          (ig.escolher(ig_em("19:35"), [feito]) or {}).get("acao") == "reel")
    check("horário perdido não sai colado no seguinte",
          (ig.escolher(ig_em("10:20"), fila[:1]) or {}).get("horario") != "08:00")

    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} verificações passaram")
    if FAILURES:
        print("Falhas: " + ", ".join(FAILURES))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
