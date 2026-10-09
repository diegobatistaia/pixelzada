"""Rodízio dos 21 estilos de carrossel (templates/social/estilos/).

Regra do Diego (09/10/2026): cada carrossel sai num estilo, sem repetir estilo
em dias seguidos, e todos os estilos têm de aparecer. Por isso a escolha é:

1. fora os estilos que já saíram hoje ou ontem;
2. fora os que pedem um campo que a pauta não tem (Agenda sem data etc.);
3. entre os que sobram, o que está há mais tempo sem sair vai primeiro
   (nunca usado vem antes de todos);
4. empate: o que combina mais com a pauta.

Story e Reel continuam no modelo de sempre (templates/social/arte.html.j2).
"""
from __future__ import annotations

from datetime import datetime, timedelta

# nome: (campo que o estilo exige na capa, ou None)
ESTILOS = {
    "plantao": None, "numerao": "numero", "revista": None, "dividido": None, "missao": None,
    "mosaico": None, "aspas": "citacao", "fliperama": None, "versus": "lados", "ficha": None,
    "figurinha": None, "carregando": None, "conquista": None, "inventario": None, "mapa": None,
    "celular": None, "agenda": "data", "poster": None, "chefao": None, "quadrinho": None,
    "reprodutor": None,
}


def serve(nome: str, p: dict) -> bool:
    """O estilo funciona com esta pauta?"""
    capa = p.get("capa") or {}
    exige = ESTILOS[nome]
    if exige == "lados":
        return bool(capa.get("lados")) or " x " in capa.get("titulo", "").replace(" vs ", " x ")
    return not exige or bool(capa.get(exige))


def afinidade(nome: str, p: dict) -> int:
    """Quanto o estilo combina com a pauta. Só desempata."""
    capa, slides = p.get("capa") or {}, p.get("slides") or []
    tem = lambda k: any(s.get(k) for s in slides)  # noqa: E731
    pontos = {
        "numerao": 3 if capa.get("numero") else 0,
        "aspas": 3, "versus": 3 if capa.get("lados") else 1, "agenda": 3,
        "ficha": (3 if capa.get("ficha") else 0) + tem("itens"),
        "inventario": (3 if capa.get("itens_capa") else 0) + tem("itens"),
        "mapa": (3 if capa.get("local") else 0) + (p.get("tipo") == "guia"),
        "poster": 2 if capa.get("palavra") else 0,
        "chefao": 3 if capa.get("chefe") else 0,
        "quadrinho": 3 if capa.get("fala") else 0,
        "plantao": 2 if p.get("tipo") == "checagem" else 0,
        "mosaico": 2 if p.get("tipo") == "guia" else 0,
        "carregando": (2 if p.get("tipo") == "guia" else 0) + tem("passos"),
        "missao": 2 if p.get("gta6") else 0,
        "celular": 1 if p.get("gta6") else 0,
        "reprodutor": 2 if p.get("tipo") == "noticia" and p.get("gta6") else 1,
        "fliperama": tem("itens"),
        "revista": 1 if p.get("tipo") == "noticia" else 0,
    }
    return int(pontos.get(nome, 0))


def historico(pautas: list[dict]) -> dict[str, str]:
    """Último dia (AAAA-MM-DD) em que cada estilo saiu."""
    ultimo: dict[str, str] = {}
    for q in pautas:
        pub = q.get("publicado") or {}
        e, dia = pub.get("estilo"), pub.get("data")
        if e in ESTILOS and dia and dia > ultimo.get(e, ""):
            ultimo[e] = dia
    return ultimo


def ordem(p: dict, pautas: list[dict], t: datetime) -> list[str]:
    """Estilos para tentar, do melhor para o pior. O primeiro que desenhar sem
    erro é o usado; se nenhum couber, o gerador volta para o modelo de sempre."""
    ultimo = historico(pautas)
    hoje = t.date().isoformat()
    ontem = (t.date() - timedelta(days=1)).isoformat()
    lista = list(ESTILOS)
    servem = [e for e in lista if serve(e, p)]
    livres = [e for e in servem if ultimo.get(e, "") < ontem]
    if not livres:  # não deve acontecer com 20 estilos e 6 posts por dia
        livres = [e for e in servem if ultimo.get(e, "") < hoje] or servem
    return sorted(livres, key=lambda e: (ultimo.get(e, ""), -afinidade(e, p), lista.index(e)))
