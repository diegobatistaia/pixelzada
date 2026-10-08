"""Step 7 - the quality gate.

Nothing reaches the site without passing every check here. A post that fails
any check goes to the exception queue (data/queue/) for the daily human review;
it is never published with a warning.

Every threshold comes from quality_gate in site.config.yaml.
"""
from __future__ import annotations

from .config import Config
from .seo import body_text
from .util import longest_common_run, similarity, word_count


def primary_owners(cfg: Config) -> set[str]:
    """Donos com canal oficial configurado (fontes `kind: primary`)."""
    return {s["owner"] for s in cfg.get("sources.rss", []) if s.get("kind") == "primary"}


def official_announcement_problems(post: dict, cfg: Config) -> list[str]:
    """Matéria marcada como anúncio oficial: vale com uma fonte só, a da empresa.

    Decisão do dono em 05/10/2026: quando a notícia é o anúncio que a própria
    empresa publicou no canal oficial dela (o blog da OpenAI anunciando o
    produto da OpenAI), o canal oficial é a prova do fato "a empresa anunciou
    isso". O texto atribui tudo à empresa; o que for afirmação sobre terceiros
    continua exigindo duas fontes.
    """
    if not cfg.get("quality_gate.official_announcement_alone", False):
        return ["anúncio oficial como fonte única está desligado em quality_gate"]
    oficiais = primary_owners(cfg)
    citadas = {s.get("owner") for s in post.get("sources", []) if s.get("owner")}
    if not citadas & oficiais:
        return ["marcada como anúncio oficial, mas nenhuma fonte é canal oficial (kind: primary)"]
    return []


def check_sources(post: dict, cfg: Config) -> list[str]:
    # Exceção editorial: o dono do site pode autorizar, ao vivo numa conversa,
    # a publicação de UMA matéria específica com uma única fonte primária - o
    # canal oficial de uma empresa falando sobre si mesma (ex.: o blog da
    # OpenAI anunciando o próprio produto). Nesse caso a fonte primária É a
    # prova do fato "a empresa disse isso"; não existe segunda fonte que
    # confirme a fala da própria empresa sobre ela mesma.
    #
    # Este campo NUNCA deve ser mencionado nas Skills lidas pela Routine
    # automática - só existe quando um humano o define manualmente, artigo por
    # artigo. Sem ele, a regra das duas fontes vale sempre, sem exceção.
    if post.get("editorial_override") == "single_source_authorized":
        return []
    minimum = cfg.get("quality_gate.min_independent_sources", 2)
    owners = {s.get("owner") for s in post.get("sources", []) if s.get("owner")}
    if len(owners) < minimum:
        if post.get("fonte_unica") == "anuncio_oficial":
            return official_announcement_problems(post, cfg)
        return [f"apenas {len(owners)} fonte(s) independente(s), mínimo {minimum}"]
    return []


def check_length(post: dict, cfg: Config) -> list[str]:
    limits = cfg.get("quality_gate.word_count", {})
    count = word_count(body_text(post))
    lo, hi = limits.get("min", 600), limits.get("max", 1000)
    if count < lo:
        return [f"texto com {count} palavras, mínimo {lo}"]
    if count > hi:
        return [f"texto com {count} palavras, máximo {hi}"]
    return []


def check_originality(post: dict, cfg: Config, source_texts: list[str]) -> list[str]:
    """Compare the draft against the source articles it was written from."""
    if not source_texts:
        return []
    max_sim = cfg.get("quality_gate.max_source_similarity", 0.18)
    max_run = cfg.get("quality_gate.max_verbatim_run", 8)
    text = body_text(post)
    problems = []
    worst_sim = max((similarity(text, src) for src in source_texts), default=0.0)
    worst_run = max((longest_common_run(text, src) for src in source_texts), default=0)
    if worst_sim > max_sim:
        problems.append(f"similaridade com a fonte em {worst_sim:.0%}, teto {max_sim:.0%}")
    if worst_run > max_run:
        problems.append(f"trecho literal de {worst_run} palavras em comum com a fonte, "
                        f"teto {max_run}")
    return problems


def check_meta(post: dict, cfg: Config) -> list[str]:
    lo, hi = cfg.get("quality_gate.meta_description_range", [150, 160])
    meta = (post.get("meta_description") or "").strip()
    if not meta:
        return ["sem meta description"]
    if not lo <= len(meta) <= hi:
        return [f"meta description com {len(meta)} caracteres, faixa {lo}-{hi}"]
    return []


def check_image(post: dict, cfg: Config) -> list[str]:
    if cfg.get("images.provider", "none") == "none":
        return []
    image = post.get("image") or {}
    problems = []
    if not image.get("path"):
        problems.append("sem imagem de capa")
    if len((image.get("alt") or "").strip()) < 15:
        problems.append("alt-text da imagem ausente ou curto demais")
    if cfg.get("images.attribution_required", True) and image.get("path") and not image.get("credit"):
        problems.append("imagem sem atribuição de licença")
    return problems


def check_structure(post: dict, cfg: Config) -> list[str]:
    problems = []
    blocks = post.get("body", [])
    if not blocks:
        return ["corpo vazio"]
    if blocks[0]["type"] != "p":
        problems.append("o texto não começa com parágrafo")
    if not any(b["type"] == "h2" for b in blocks):
        problems.append("sem nenhum H2 — falta estrutura de headings")
    if not (post.get("title") or "").strip():
        problems.append("sem título (H1)")
    return problems


def check_citations(post: dict, cfg: Config) -> list[str]:
    """The sources must be named in the running text, not only in the footer."""
    text = body_text(post).lower()
    named = [s for s in post.get("sources", [])
             if s.get("name", "").split()[0].lower() in text]
    return [] if named else ["nenhuma fonte citada no corpo do texto"]


def check_internal_links(post: dict, cfg: Config) -> list[str]:
    """Internal links are required only once there is something to link to.

    Without this exemption the site could never bootstrap: on day one nothing is
    published yet, so every post would fail here and the whole first batch would
    pile up in the exception queue.
    """
    minimum = cfg.get("quality_gate.min_internal_links", 1)
    if post.get("pool_size", 0) < minimum:
        return []
    found = len(post.get("related", []))
    if found < minimum:
        return [f"apenas {found} link(s) interno(s), mínimo {minimum}"]
    return []


def check_schema(post: dict, cfg: Config) -> list[str]:
    return [] if post.get("schema_news_article") else ["sem schema markup NewsArticle"]


CHECKS = {
    "sources_cited": check_citations,
    "meta_description": check_meta,
    "image_alt": check_image,
    "schema_news_article": check_schema,
    "h1_present": check_structure,
    "internal_links": check_internal_links,
}


def evaluate(post: dict, cfg: Config, source_texts: list[str] | None = None) -> dict:
    """Returns {passed, reasons}. Never mutates the post."""
    reasons: list[str] = []
    reasons += check_sources(post, cfg)
    reasons += check_length(post, cfg)
    reasons += check_originality(post, cfg, source_texts or [])

    required = cfg.get("quality_gate.require", [])
    for name in required:
        check = CHECKS.get(name)
        if check is None:
            reasons.append(f"critério '{name}' não existe no motor")
            continue
        reasons += check(post, cfg)

    return {"passed": not reasons, "reasons": sorted(set(reasons))}
