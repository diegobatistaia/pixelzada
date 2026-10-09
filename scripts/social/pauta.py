"""Pauta do Instagram: o arquivo que a redação escreve e o gerador desenha.

Uma pauta por post, em social/pautas/<slug>.json. Ela é ao mesmo tempo o
contrato com a redação (texto dos slides, legenda, imagem) e o registro do que
já saiu (campos `publicado`, `story` e `reel`, gravados pelo workflow).
O formato está descrito em .claude/skills/instagram-pixelzada/SKILL.md.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
PAUTAS = ROOT / "social" / "pautas"
SAIDA = ROOT / "social" / "saida"
TZ = ZoneInfo("America/Sao_Paulo")

TIPOS = {
    # tipo: (classe de cor da moldura, rótulo da etiqueta, validade em horas)
    "noticia": ("", "Notícia", 36),
    "checagem": ("checagem", "Checagem", 96),
    "guia": ("guia", "Guia", 168),
}
SELOS = {"confirmado": "Confirmado", "boato": "Boato", "falso": "Falso", "sem-info": "Sem confirmação"}
STATUS = {"pronto", "publicado", "descartado", "reprovado"}

# Limites de texto. O desenho encolhe o título até um mínimo e reprova o que
# ainda assim não couber; estes limites pegam o excesso antes, sem navegador.
LIM = {
    "assunto": 16, "fonte": 46, "capa.titulo": 80, "capa.apoio": 150,
    "rotulo": 22, "titulo": 60, "texto": 460, "item": 64, "final": 70,
    "gancho": 125, "legenda_min": 350, "legenda_max": 1100, "alt": 120,
}
# Campos opcionais da capa que liberam estilos de carrossel, com o tamanho máximo.
EXTRAS = {"numero": 6, "numero_legenda": 30, "citacao": 90, "autor": 50, "local": 20,
          "palavra": 12, "chefe": 20, "fala": 40}
MARCA = "#pixelzada"
AVISO_LINK = "Matéria completa no link da bio."
GENERICAS = {"#games", "#game", "#gamer", "#gaming", "#videogame", "#jogos", "#instagood", "#love"}
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
LINK = re.compile(r"https?://|www\.|\.com\b|\.com\.br\b", re.I)


def caminho(slug: str) -> Path:
    return PAUTAS / f"{slug}.json"


def carregar(slug: str) -> dict:
    return json.loads(caminho(slug).read_text(encoding="utf-8"))


def salvar(p: dict) -> None:
    PAUTAS.mkdir(parents=True, exist_ok=True)
    caminho(p["slug"]).write_text(json.dumps(p, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def todas() -> list[dict]:
    if not PAUTAS.exists():
        return []
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(PAUTAS.glob("*.json"))]


def criado_em(p: dict) -> datetime:
    return datetime.fromisoformat(p["criado"]).astimezone(TZ)


def vencida(p: dict, agora: datetime) -> bool:
    horas = p.get("validade_horas") or TIPOS.get(p.get("tipo"), TIPOS["noticia"])[2]
    return agora - criado_em(p) > timedelta(hours=horas)


def slides(p: dict) -> list[dict]:
    """Os slides do carrossel, na ordem: capa, miolo, final."""
    out = [{"kind": "capa", **p["capa"]}]
    passo = 1
    cortes = ["50% 15%", "50% 85%", "20% 50%", "80% 50%", "50% 50%"]
    for i, s in enumerate(p["slides"]):
        # Mesma imagem em todos os slides: cada um mostra um pedaço diferente dela.
        s = {"kind": "miolo", "pos": cortes[i % len(cortes)], **s}
        if s.get("passos"):
            s["inicio"] = passo  # a numeração dos passos continua de um slide para o outro
            passo += len(s["passos"])
        out.append(s)
    out.append({"kind": "final", "titulo": p["final"]})
    return out


def legenda(p: dict) -> str:
    lg = p["legenda"]
    partes = [lg["gancho"], *lg["corpo"], lg["chamada"], AVISO_LINK]
    return "\n\n".join(x.strip() for x in partes if x.strip()) + "\n\n" + " ".join(lg["hashtags"])


# ---------------------------------------------------------------------------
# Conferência
# ---------------------------------------------------------------------------
def conferir(p: dict, arquivo: str | None = None) -> list[str]:
    """Erros que impedem a pauta de sair. Lista vazia = pode ir para a fila."""
    e: list[str] = []

    def exige(cond, msg):
        if not cond:
            e.append(msg)

    def tam(campo, texto, lim):
        if texto and len(texto) > lim:
            e.append(f"{campo} tem {len(texto)} caracteres (máximo {lim})")

    for k in ("slug", "tipo", "assunto", "gta6", "criado", "imagem", "fonte", "capa", "slides", "final", "legenda", "alt", "status"):
        exige(k in p, f"falta o campo {k}")
    if e:
        return e
    if arquivo:
        exige(Path(arquivo).stem == p["slug"], f"o slug não bate com o nome do arquivo ({Path(arquivo).name})")
    exige(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+){1,9}", p["slug"]), "slug em minúsculas, sem acento, palavras com hífen")
    exige(p["tipo"] in TIPOS, f"tipo deve ser um de {sorted(TIPOS)}")
    exige(isinstance(p["gta6"], bool), "gta6 é true ou false")
    exige(p["status"] in STATUS, f"status deve ser um de {sorted(STATUS)}")
    try:
        exige(datetime.fromisoformat(p["criado"]).tzinfo is not None, "criado precisa do fuso (ex.: 2026-10-08T07:40:00-03:00)")
    except ValueError:
        e.append("criado não é uma data ISO")
    tam("assunto", p["assunto"], LIM["assunto"])
    tam("fonte", p["fonte"], LIM["fonte"])
    exige(p["fonte"].lower().startswith("fonte"), 'fonte começa com "Fonte:" ou "Fontes:"')

    img = p["imagem"]
    exige(img.get("url") or img.get("path"), "imagem precisa de url ou path")
    exige(img.get("credito"), "imagem sem crédito")
    if img.get("path"):
        exige((ROOT / img["path"]).exists(), f"imagem {img['path']} não existe no repositório")

    capa = p["capa"]
    exige(capa.get("titulo"), "capa sem título")
    tam("capa.titulo", capa.get("titulo"), LIM["capa.titulo"])
    tam("capa.apoio", capa.get("apoio"), LIM["capa.apoio"])
    if capa.get("destaque"):
        exige(capa["destaque"].lower() in capa.get("titulo", "").lower(), "capa.destaque precisa ser um trecho do título")
    # Campos opcionais que liberam estilos de carrossel (scripts/social/estilos.py)
    for k, lim in EXTRAS.items():
        if isinstance(capa.get(k), str):
            tam(f"capa.{k}", capa[k], lim)
    if "data" in capa:
        try:
            date.fromisoformat(capa["data"])
        except (TypeError, ValueError):
            e.append("capa.data no formato AAAA-MM-DD")
    if "lados" in capa:
        lados = capa["lados"]
        exige(isinstance(lados, list) and len(lados) == 2 and all(isinstance(x, str) and 0 < len(x) <= 14 for x in lados),
              "capa.lados são 2 nomes de até 14 caracteres")
    if "ficha" in capa:
        f = capa["ficha"]
        exige(isinstance(f, list) and 2 <= len(f) <= 4 and all(isinstance(x, list) and len(x) == 2 and len(x[0]) <= 12 and len(x[1]) <= 30 for x in f),
              "capa.ficha tem de 2 a 4 pares [rótulo até 12, valor até 30]")
    if "itens_capa" in capa:
        f = capa["itens_capa"]
        exige(isinstance(f, list) and 2 <= len(f) <= 4 and all(isinstance(x, str) and len(x) <= 16 for x in f),
              "capa.itens_capa tem de 2 a 4 nomes de até 16 caracteres")

    exige(isinstance(p["slides"], list) and 2 <= len(p["slides"]) <= 5, "de 2 a 5 slides no miolo")
    for i, s in enumerate(p["slides"] if isinstance(p["slides"], list) else [], 2):
        pre = f"slide {i}"
        exige(s.get("rotulo") and s.get("titulo"), f"{pre}: precisa de rotulo e titulo")
        tam(f"{pre}.rotulo", s.get("rotulo"), LIM["rotulo"])
        tam(f"{pre}.titulo", s.get("titulo"), LIM["titulo"])
        if s.get("destaque"):
            exige(s["destaque"].lower() in s.get("titulo", "").lower(), f"{pre}: destaque precisa ser um trecho do título")
        corpo = [k for k in ("texto", "itens", "passos") if s.get(k)]
        exige(len(corpo) == 1, f"{pre}: use um só entre texto, itens e passos")
        tam(f"{pre}.texto", " ".join(s.get("texto") or []), LIM["texto"])
        for it in s.get("itens") or []:
            exige(it.get("selo") in SELOS, f"{pre}: selo deve ser um de {sorted(SELOS)}")
            tam(f"{pre}.item", it.get("texto"), LIM["item"])
        exige(len(s.get("itens") or []) <= 5 and len(s.get("passos") or []) <= 5, f"{pre}: no máximo 5 itens ou passos")
        for t in s.get("passos") or []:
            tam(f"{pre}.passo", t, LIM["item"])
    tam("final", p["final"], LIM["final"])

    lg = p["legenda"]
    for k in ("gancho", "corpo", "chamada", "hashtags"):
        exige(k in lg, f"legenda sem {k}")
    if not e:
        tam("legenda.gancho", lg["gancho"], LIM["gancho"])
        texto = legenda(p).rsplit("\n\n", 1)[0]
        exige(LIM["legenda_min"] <= len(texto) <= LIM["legenda_max"],
              f"legenda (sem hashtags) tem {len(texto)} caracteres; vai de {LIM['legenda_min']} a {LIM['legenda_max']}")
        exige(not LINK.search(texto), "legenda não leva link nem domínio (o link fica na bio)")
        tags = lg["hashtags"]
        exige(3 <= len(tags) <= 5, "de 3 a 5 hashtags")
        exige(tags and tags[0] == MARCA, f"a primeira hashtag é {MARCA}")
        for t in tags:
            exige(re.fullmatch(r"#[a-z0-9_]+", t), f"hashtag {t!r}: minúsculas, sem acento nem espaço")
            exige(t not in GENERICAS, f"hashtag {t} é genérica demais")

    n = len(p["slides"]) + 2 if isinstance(p["slides"], list) else 0
    exige(isinstance(p["alt"], list) and len(p["alt"]) == n, f"alt precisa de {n} textos, um por slide")
    for i, a in enumerate(p["alt"] if isinstance(p["alt"], list) else [], 1):
        exige(a.startswith(f"Slide {i}: "), f'alt {i} começa com "Slide {i}: "')
        tam(f"alt {i}", a, LIM["alt"])

    arte = [capa.get("titulo", ""), capa.get("apoio", ""), p["final"]]
    for s in p["slides"] if isinstance(p["slides"], list) else []:
        arte += [s.get("titulo", ""), *(s.get("texto") or []), *(s.get("passos") or []),
                 *[it.get("texto", "") for it in s.get("itens") or []]]
    tudo = " ".join(arte)
    exige(not EMOJI.search(tudo), "sem emoji na arte")
    exige(tudo.count("!") <= 1, "no máximo um ponto de exclamação no carrossel")
    return e
