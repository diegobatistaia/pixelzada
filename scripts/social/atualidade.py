"""Barreira de data vencida nos Reels (Diego, 21/11).

Em 21/11 saiu o vídeo longo "GTA 6 sai em MENOS de 48 horas" com o jogo já lançado (19/11).
Texto de contagem regressiva ou de "ainda vai sair" não pode ir ao ar depois do lançamento.
Esta checagem olha a legenda (e o título) e recusa frase de data/futuro já vencida.

    python -m scripts.social.atualidade varrer     # pausa os agendados com texto vencido
    python -m scripts.social.atualidade testar "texto"

Só o texto é checado (a legenda). Texto escrito dentro do vídeo precisa ser conferido na
revisão do Reel (vídeos antigos da própria Pixelzada, de antes de 19/11, não entram sozinhos).
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import date

LANCAMENTO = date(2026, 11, 19)  # GTA 6 já saiu: a partir daqui, tudo é "já saiu"

_N = r"(?:\d+|um|uma|dois|duas|tres|quatro|cinco|seis|sete|dez|vinte|trinta)"
_UN = r"(?:minutos?|horas?|dias?|semanas?|meses|mes)"

_PADROES = [
    ("contagem regressiva", r"contagem regressiva|countdown"),
    ("falta/faltam", rf"\bfalt(?:a|am|ando)\b(?: apenas| so| somente| menos de| mais de| pouco(?:s)?)?\s*(?:{_N}\s*)?{_UN}"),
    ("falta pouco", r"\bfalt(?:a|am)\s+pouco"),
    ("sai/chega em N tempo", rf"\b(?:sai|saira|saindo|chega|chegara|chegando|lanca|lancara|lancando|vem|volta)\s+em\s+(?:menos de |apenas |so |somente |mais de )?{_N}\s*{_UN}"),
    ("N tempo para o lançamento", rf"{_N}\s*{_UN}\s*(?:para|pro|pra|ate|antes)\s*(?:o\s*)?(?:lancamento|gta\s*6|gta\s*vi|chegar|sair)"),
    ("até o lançamento", r"\bate\s+(?:o\s+)?(?:lancamento|gta\s*6\s+(?:sair|chegar|lancar))"),
    ("antes do lançamento/de jogar", r"\bantes\s+(?:de|do|da)\s+(?:jogar|lancamento|gta\s*6\s+(?:sair|chegar|lancar)|sair|chegar)"),
    ("quando o GTA 6 sair", r"\bquando\s+(?:o\s+)?gta\s*6\s+(?:sair|chegar|lancar|for lancado)"),
    ("vai sair/chegar", r"\b(?:gta\s*6\s+)?vai\s+(?:sair|chegar|lancar|ser\s+lancado)\b"),
    ("ainda não saiu", r"\bainda\s+nao\s+(?:saiu|foi\s+lancado|lancou|chegou|da\s+pra\s+jogar|pode\s+jogar|posso\s+jogar)"),
    ("amanhã sai/chega", r"\bamanha\s+(?:sai|chega|lanca|e\s+o\s+dia)"),
    ("pré-load/pré-download", r"\bpre-?\s*(?:load|download|carreg\w+)\b"),
    ("lançamento em breve", r"\bem\s+breve\b.{0,30}\b(?:gta|lancamento)|\b(?:gta\s*6|lancamento)\b.{0,30}\bem\s+breve\b"),
]
_RX = [(nome, re.compile(p)) for nome, p in _PADROES]


def _sem_acento(t: str) -> str:
    t = unicodedata.normalize("NFD", t or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def defasado(*textos: str, hoje: date | None = None) -> list[str]:
    """Frases de data/futuro já vencidas (lista vazia = ok). Antes do lançamento não barra nada."""
    from .pauta import TZ
    from datetime import datetime
    dia = hoje or datetime.now(TZ).date()
    if dia < LANCAMENTO:
        return []
    t = _sem_acento(" ".join(x or "" for x in textos))
    return [nome for nome, rx in _RX if rx.search(t)]


def varrer(*, aplicar: bool = True) -> int:
    """Pausa os Reels agendados cujo texto está vencido. Devolve quantos achou."""
    from . import reels as R
    fila = R.carregar()
    achados = []
    for item in fila:
        if item.get("status") != "agendado":
            continue
        motivos = defasado(item.get("legenda", ""), (item.get("origem") or {}).get("titulo", ""))
        if motivos:
            achados.append((item, motivos))
    for item, motivos in achados:
        print(f"VENCIDO {item['data']} {item['horario']} {item['slug']}: {', '.join(motivos)}")
        if aplicar:
            item["status"] = "pausado"
            item["erro"] = "texto com data vencida: " + ", ".join(motivos)
    if achados and aplicar:
        R.salvar(fila)
    print(f"{len(achados)} agendado(s) com texto vencido")
    return len(achados)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="atualidade")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("varrer")
    t = sub.add_parser("testar")
    t.add_argument("texto", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "testar":
        print(defasado(*a.texto) or "ok")
        return 0
    varrer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
