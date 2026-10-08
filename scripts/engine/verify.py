"""Step 2 - cross-checking facts. The non-negotiable rule of this project.

A fact may only reach a draft if independent sources confirm it. Independent
means different owners: two outlets from the same group republishing one wire
story count once, not twice.

The step fetches the full text of every item in a cluster, then asks Claude to
break the story into atomic factual claims and mark, for each claim, which
sources actually state it. A story whose central facts are not confirmed by
`quality_gate.min_independent_sources` distinct owners is discarded here - it
never reaches the writing step.
"""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from .config import Config, bot_user_agent
from .llm import LLMError, parse
from .util import isoformat, strip_tags, utcnow

HEADERS = {"User-Agent": bot_user_agent()}
MAX_ARTICLE_CHARS = 6000


# --------------------------------------------------------------------- schemas

class Claim(BaseModel):
    text: str = Field(description="Um fato atomico e verificavel, em uma frase.")
    central: bool = Field(description="True se a materia perde sentido sem este fato.")
    supported_by: list[str] = Field(
        description="Owners (identificadores das fontes) cujo texto afirma este fato.")


class Verification(BaseModel):
    summary: str = Field(description="O fato-base da pauta em uma frase neutra.")
    entities: list[str] = Field(description="Empresas, produtos, pessoas e paises citados.")
    category_key: str = Field(description="Chave da categoria editorial mais adequada.")
    claims: list[Claim]
    notes: str = Field(description="Divergencias entre as fontes, se houver. Vazio se nao houver.")


# ------------------------------------------------------------------- fetching

def fetch_article(url: str, timeout: int = 20) -> str:
    """Best-effort full text. Returns "" when the page cannot be read."""
    return fetch_page(url, timeout)[0]


def fetch_page(url: str, timeout: int = 20) -> tuple[str, str]:
    """Texto integral e imagem de capa (og:image) da página; ("", "") se não abrir.

    A imagem vai para o briefing: é de onde a redação tira o print oficial dos
    carrosséis do Instagram (a Routine não tem internet para procurar)."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return "", ""
    soup = BeautifulSoup(response.text, "html.parser")
    og = soup.find("meta", attrs={"property": "og:image"}) or soup.find("meta", attrs={"name": "twitter:image"})
    image = (og.get("content") or "").strip() if og else ""
    if image.startswith("//"):
        image = "https:" + image
    elif image.startswith("/"):
        image = requests.compat.urljoin(url, image)
    for tag in soup(["script", "style", "nav", "aside", "footer", "form", "figure"]):
        tag.decompose()
    node = soup.find("article") or soup.find("main") or soup.body
    if node is None:
        return "", image
    paragraphs = [p.get_text(" ", strip=True) for p in node.find_all("p")]
    text = " ".join(p for p in paragraphs if len(p) > 40)
    return strip_tags(text)[:MAX_ARTICLE_CHARS], image


def gather(story: dict) -> dict:
    """Attach article bodies (and cover images) to the cluster's items, in place."""
    for item in story["items"]:
        item["body"], item["image"] = fetch_page(item["url"])
        item["body_chars"] = len(item["body"])
    return story


# ---------------------------------------------------------------- the checking

SYSTEM = """Você é o checador de fatos de uma redação. Seu único trabalho é separar
o que as fontes REALMENTE afirmam do que elas sugerem, especulam ou repetem umas das outras.

Regras:
- Um fato só pode ser marcado como suportado por um owner se o texto DAQUELE owner
  afirmar o fato. Nunca infira, nunca complete lacuna, nunca assuma que "deve estar lá".
- Se duas fontes usam frases quase idênticas, provavelmente reproduzem o mesmo release:
  registre isso em `notes`, porque isso NÃO é confirmação independente.
- Números, datas, valores e nomes próprios precisam bater entre as fontes. Divergência
  vai para `notes`, e o fato divergente não deve ser marcado como central e confirmado.
- Não escreva matéria, não opine, não adjetive. Apenas extraia e atribua.
- `category_key` deve ser EXATAMENTE uma das chaves oferecidas."""


def build_prompt(story: dict, cfg: Config) -> str:
    keys = [c["key"] for c in cfg.categories(cfg.default_language)]
    labels = ", ".join(f"{c['key']} ({c['label']})" for c in cfg.categories(cfg.default_language))
    parts = [
        f"Categorias disponíveis (use a chave): {labels}",
        f"Chaves validas: {keys}",
        "",
        "FONTES:",
    ]
    for item in story["items"]:
        body = item.get("body") or item.get("summary", "")
        parts += [
            "",
            f"--- owner: {item['owner']} | veiculo: {item['source']} | {item['published_at']}",
            f"titulo: {item['title']}",
            f"texto: {body if body else '(texto integral indisponível — use apenas o título)'}",
        ]
    return "\n".join(parts)


def independent_owners(claim: Claim, story: dict) -> list[str]:
    valid = {i["owner"] for i in story["items"]}
    return sorted(set(claim.supported_by) & valid)


def verify(story: dict, cfg: Config) -> dict:
    """Returns the story enriched with a verdict. Never raises on rejection."""
    minimum = cfg.get("quality_gate.min_independent_sources", 2)
    story = gather(story)

    readable = [i for i in story["items"] if i.get("body")]
    result = {
        "story_id": story["id"],
        "title": story["title"],
        "checked_at": isoformat(utcnow()),
        "sources": [{
            "name": i["source"], "owner": i["owner"], "url": i["url"],
            "title": i["title"], "published_at": i["published_at"],
            "readable": bool(i.get("body")),
        } for i in story["items"]],
    }

    if len(story["owners"]) < minimum:
        return {**result, "verdict": "insufficient",
                "reason": f"apenas {len(story['owners'])} fonte(s) independente(s), "
                          f"mínimo {minimum}",
                "facts": [], "confirmed_owners": story["owners"]}

    if len(readable) < minimum:
        return {**result, "verdict": "insufficient",
                "reason": f"apenas {len(readable)} fonte(s) com texto legível, mínimo {minimum}",
                "facts": [], "confirmed_owners": [i["owner"] for i in readable]}

    try:
        checked = parse(cfg, system=SYSTEM, user=build_prompt(story, cfg), schema=Verification)
    except LLMError as exc:
        return {**result, "verdict": "error", "reason": str(exc), "facts": [],
                "confirmed_owners": []}

    facts = []
    for claim in checked.claims:
        owners = independent_owners(claim, story)
        facts.append({
            "text": claim.text,
            "central": claim.central,
            "owners": owners,
            "confirmed": len(owners) >= minimum,
        })

    central = [f for f in facts if f["central"]]
    confirmed_central = [f for f in central if f["confirmed"]]
    confirmed_owners = sorted({o for f in confirmed_central for o in f["owners"]})

    verdict = "verified"
    reason = ""
    if not central:
        verdict, reason = "insufficient", "nenhum fato central identificado"
    elif not confirmed_central:
        verdict, reason = "insufficient", (
            f"nenhum fato central confirmado por {minimum}+ fontes independentes")
    elif len(confirmed_central) < len(central) / 2:
        verdict, reason = "insufficient", (
            f"apenas {len(confirmed_central)} de {len(central)} fatos centrais confirmados")

    return {
        **result,
        "verdict": verdict,
        "reason": reason,
        "summary": checked.summary,
        "entities": checked.entities,
        "category_key": checked.category_key,
        "notes": checked.notes,
        "facts": facts,
        "confirmed_facts": [f["text"] for f in confirmed_central],
        "confirmed_owners": confirmed_owners,
    }


def run(stories: list[dict], cfg: Config, limit: int | None = None) -> list[dict]:
    out = []
    for story in stories[:limit] if limit else stories:
        checked = verify(story, cfg)
        mark = {"verified": "OK  ", "insufficient": "CORTA", "error": "ERRO "}[checked["verdict"]]
        print(f"  {mark} {story['title'][:64]}")
        if checked["reason"]:
            print(f"        {checked['reason']}")
        out.append(checked)
    return out
