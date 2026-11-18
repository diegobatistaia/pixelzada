"""Saúde das chaves da Meta e da fila de Reels (pedido do Diego, 12/11).

Em 12/11 as duas chaves (INSTAGRAM_TOKEN_PIXELZADA e META_TOKEN_PIXELZADA) foram
derrubadas pela Meta (erro 190) e nenhum Reel saiu. Este script faz, de hora em
hora, uma chamada leve com cada chave e confere a reserva da fila, para o aviso
chegar ao Diego antes de um horário passar em branco.

    python -m scripts.social.saude                 confere e imprime o resumo
    python -m scripts.social.saude --saida DIR     grava também DIR/saude.json

Roda no GitHub Actions (.github/workflows/saude.yml), o único lugar com as chaves
e com saída para graph.instagram.com / graph.facebook.com. O resultado vai para o
ramo saude-dados; a tarefa agendada do Claude lê de lá e avisa o Diego no chat.

Problemas (campo "problemas", cada um com "id" fixo para não repetir aviso):
  chave_instagram   a chave de publicação não funciona (Reels param)
  chave_meta        a chave da pesquisa de concorrentes não funciona
  validade_*        a chave vence em menos de AVISO_DIAS dias
  acesso_meta       o acesso aos dados da chave da Meta vence em menos de AVISO_DIAS dias
  reserva           a fila de Reels tem menos de RESERVA_MIN dias de vídeos
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import instagram as IG, painel as PN, pesquisa as PQ, reels as R

AVISO_DIAS = 10      # avisar quando faltar menos que isso para a chave vencer
RESERVA_MIN = 2.0    # dias de Reels na fila (Diego, 12/11)


def _erro(e: Exception) -> dict:
    """Código e subcódigo da Meta a partir do texto do erro (sem a chave)."""
    texto = str(e)
    cod = re.search(r'"code"\s*:\s*(\d+)', texto)
    sub = re.search(r'"error_subcode"\s*:\s*(\d+)', texto)
    return {"codigo": int(cod.group(1)) if cod else None,
            "subcodigo": int(sub.group(1)) if sub else None,
            "mensagem": texto[:300]}


def _dias(ts: int | None, agora: datetime) -> float | None:
    if not ts:
        return None
    return round((datetime.fromtimestamp(ts, timezone.utc) - agora).total_seconds() / 86400, 1)


def chave_instagram(agora: datetime) -> dict:
    token = os.environ.get(IG.SECRET, "").strip()
    r = {"segredo": IG.SECRET, "uso": "publicar os Reels", "ok": False}
    if not token:
        return {**r, "erro": {"codigo": None, "mensagem": "segredo vazio ou não cadastrado"}}
    r["tipo"] = "login do Instagram" if IG.chave_do_instagram(token) else "login do Facebook"
    try:
        IG.conta()
        r["ok"] = True
    except IG.ApiError as e:
        return {**r, "erro": _erro(e)}
    if IG.chave_do_instagram(token):
        # A renovação estica para 60 dias e diz quanto falta; erro aqui não derruba a chave.
        try:
            ren = IG.call("GET", "https://graph.instagram.com/refresh_access_token", token,
                          grant_type="ig_refresh_token")
            r["vence_em_dias"] = round(int(ren.get("expires_in", 0)) / 86400, 1)
        except IG.ApiError as e:
            r["renovacao"] = _erro(e)["mensagem"][:200]
    else:
        r["vence_em_dias"] = None  # token do Facebook: a validade vem do debug_token, se houver
    return r


def chave_meta(agora: datetime) -> dict:
    cfg = PQ.carregar_config(PQ.ROOT / "social/pesquisa/config.yaml")
    token = os.environ.get(cfg["segredo"], "").strip()
    r = {"segredo": cfg["segredo"], "uso": "pesquisa de vídeos dos concorrentes", "ok": False}
    if not token:
        return {**r, "erro": {"codigo": None, "mensagem": "segredo vazio ou não cadastrado"}}
    try:
        info = PQ.call(cfg["api"], "debug_token", token, input_token=token).get("data") or {}
    except PQ.ApiError as e:
        return {**r, "erro": _erro(e)}
    r["tipo"] = info.get("type")
    if not info.get("is_valid", False):
        err = info.get("error") or {}
        return {**r, "erro": {"codigo": err.get("code"), "subcodigo": err.get("subcode"),
                              "mensagem": (err.get("message") or "chave inválida")[:300]}}
    r["vence_em_dias"] = _dias(info.get("expires_at"), agora)          # None = nunca vence
    r["acesso_vence_em_dias"] = _dias(info.get("data_access_expires_at"), agora)
    faltam = {"instagram_basic", "instagram_manage_insights", "pages_show_list"} - set(info.get("scopes") or [])
    if faltam:
        r["permissoes_faltando"] = sorted(faltam)
    try:
        PQ.conta(cfg)
        r["ok"] = True
    except PQ.ApiError as e:
        r["erro"] = _erro(e)
    return r


def problemas(chaves: dict, fila: dict) -> list[dict]:
    p = []
    for nome, c in chaves.items():
        if not c["ok"]:
            e = c.get("erro") or {}
            p.append({"id": f"chave_{nome}", "nivel": "vermelho",
                      "texto": f"A chave {c['segredo']} ({c['uso']}) parou de funcionar: " + (
                          f"erro {e['codigo']}{'/' + str(e['subcodigo']) if e.get('subcodigo') else ''}."
                          if e.get("codigo") else f"{e.get('mensagem', 'erro desconhecido')}.")})
            continue
        v = c.get("vence_em_dias")
        if v is not None and v < AVISO_DIAS:
            p.append({"id": f"validade_{nome}", "nivel": "amarelo",
                      "texto": f"A chave {c['segredo']} vence em {v:.0f} dia(s)."})
        a = c.get("acesso_vence_em_dias")
        if a is not None and a < AVISO_DIAS:
            p.append({"id": f"acesso_{nome}", "nivel": "amarelo",
                      "texto": f"O acesso aos dados da chave {c['segredo']} vence em {a:.0f} dia(s)."})
    dias = fila.get("dias_de_reserva") or 0
    if dias < RESERVA_MIN:
        p.append({"id": "reserva", "nivel": "vermelho" if dias < 1 else "amarelo",
                  "texto": f"A fila de Reels tem só {str(dias).replace('.', ',')} dia(s) de reserva "
                           f"({fila.get('agendados', 0)} vídeos; meta {fila.get('meta_por_dia')}/dia)."})
    return p


def montar(agora: datetime | None = None) -> dict:
    agora_brt = agora or IG.agora()
    utc = agora_brt.astimezone(timezone.utc)
    fila_toda = R.carregar()
    chaves = {"instagram": chave_instagram(utc), "meta": chave_meta(utc)}
    fila = PN.reserva_reels(fila_toda, agora_brt)
    fila.pop("por_dia", None)
    hoje = PN.reels_hoje(fila_toda, agora_brt)
    return {
        "atualizado": agora_brt.isoformat(timespec="minutes"),
        "chaves": chaves,
        "fila_reels": fila,
        "reels_hoje": {k: hoje[k] for k in ("meta", "publicados", "deviam_ter_saido", "atrasados")},
        "problemas": problemas(chaves, fila),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", type=Path)
    a = ap.parse_args(argv)
    estado = montar()
    for nome, c in estado["chaves"].items():
        extra = f", vence em {c['vence_em_dias']} dias" if c.get("vence_em_dias") is not None else ""
        print(f"chave {nome}: {'OK' if c['ok'] else 'FALHOU'} ({c.get('tipo') or '?'}{extra})")
        if not c["ok"]:
            print(f"  {(c.get('erro') or {}).get('mensagem', '')[:200]}")
    f = estado["fila_reels"]
    print(f"fila: {f['agendados']} Reels agendados, {f['dias_de_reserva']} dia(s) de reserva")
    for p in estado["problemas"]:
        # Anotação no resumo do GitHub, sem derrubar o workflow (o aviso vai pelo chat).
        print(f"::warning title=Saúde::{p['texto']}")
    if a.saida:
        a.saida.mkdir(parents=True, exist_ok=True)
        (a.saida / "saude.json").write_text(json.dumps(estado, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
