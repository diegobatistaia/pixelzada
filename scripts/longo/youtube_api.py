"""Envio de vídeo longo ao YouTube pela API oficial (YouTube Data API v3).

Lê scripts/longo/publicar/<slug>.json:
  {"titulo", "descricao", "tags": [...], "publicar_em": "2026-11-18T12:00:00-03:00" (opcional),
   "capa": "previas/longo/capas/<arquivo>.jpg", "categoria": "20"}
e o vídeo final em previas/longo/narrado/<slug>/final-1080p.mp4.parteNN (confere o sha256).

    python -m scripts.longo.youtube_api <slug> [--teste]

--teste: sobe PRIVADO e sem agendamento (para conferir). Segredos: YOUTUBE_CLIENT_ID,
YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN. Nunca imprime os segredos.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def token() -> str:
    dados = urllib.parse.urlencode({
        "client_id": os.environ["YOUTUBE_CLIENT_ID"],
        "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
        "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    r = urllib.request.urlopen("https://oauth2.googleapis.com/token", dados, timeout=60)
    return json.loads(r.read())["access_token"]


def video_final(slug: str) -> Path:
    pasta = RAIZ / "previas/longo/narrado" / slug
    partes = sorted(pasta.glob("final-1080p.mp4.parte*"))
    if not partes:
        raise SystemExit(f"vídeo final não encontrado em {pasta}")
    destino = RAIZ / "trabalho" / f"{slug}.mp4"
    destino.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with destino.open("wb") as f:
        for p in partes:
            b = p.read_bytes()
            f.write(b)
            h.update(b)
    esperado = (pasta / "final-1080p.sha256").read_text().split()[0]
    if h.hexdigest() != esperado:
        raise SystemExit("sha256 do vídeo final não confere")
    return destino


def enviar(slug: str, teste: bool) -> str:
    meta = json.loads((RAIZ / "scripts/longo/publicar" / f"{slug}.json").read_text())
    arq = video_final(slug)
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    if meta.get("publicar_em") and not teste:
        status["publishAt"] = meta["publicar_em"]  # fica privado e o YouTube publica no horário
    corpo = {
        "snippet": {
            "title": meta["titulo"][:100],
            "description": meta["descricao"][:5000],
            "tags": meta.get("tags", []),
            "categoryId": meta.get("categoria", "20"),
            "defaultLanguage": "pt-BR",
            "defaultAudioLanguage": "pt-BR",
        },
        "status": status,
    }
    tk = token()
    tam = arq.stat().st_size
    ini = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=json.dumps(corpo).encode(), method="POST",
        headers={"Authorization": f"Bearer {tk}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(tam)})
    url = urllib.request.urlopen(ini, timeout=120).headers["Location"]
    with arq.open("rb") as f:
        env = urllib.request.Request(url, data=f.read(), method="PUT",
                                     headers={"Authorization": f"Bearer {tk}", "Content-Type": "video/mp4"})
        vid = json.loads(urllib.request.urlopen(env, timeout=1800).read())["id"]
    print(f"vídeo enviado: https://youtu.be/{vid} ({'teste privado' if teste else status.get('publishAt', 'privado')})")
    capa = meta.get("capa")
    if capa:
        dados = (RAIZ / capa).read_bytes()
        req = urllib.request.Request(
            f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid}",
            data=dados, method="POST", headers={"Authorization": f"Bearer {tk}", "Content-Type": "image/jpeg"})
        try:
            urllib.request.urlopen(req, timeout=120)
            print("capa enviada")
        except urllib.error.HTTPError as e:  # canal sem verificação por telefone não aceita capa
            print(f"capa NÃO enviada ({e.code}): {e.read()[:300]!r}")
    return vid


if __name__ == "__main__":
    enviar(sys.argv[1], "--teste" in sys.argv)
