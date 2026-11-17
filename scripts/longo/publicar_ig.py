"""Publica um vídeo longo (horizontal) no Instagram, como teste do Diego (17/11/2026).

Pela API todo vídeo do Instagram sai como Reel (até 15 min). O arquivo já tem que estar em
pixelzada.com.br/ig/<pasta>/video.mp4 e capa.jpg (o workflow longo-instagram.yml envia).
Grava o resultado em previas/longo/instagram-<pasta>.json.

    python -m scripts.longo.publicar_ig <pasta> <arquivo da legenda>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.social import instagram as IG
from scripts.social.seguranca import risco_texto

RAIZ = Path(__file__).resolve().parents[2]


def main() -> int:
    pasta, arq = sys.argv[1], Path(sys.argv[2])
    legenda = arq.read_text(encoding="utf-8").strip()
    saida = RAIZ / f"previas/longo/instagram-{pasta}.json"
    res = {"pasta": pasta, "em": IG.agora().isoformat(timespec="seconds")}
    if saida.exists() and json.loads(saida.read_text()).get("ok"):
        print("já publicado:", saida.read_text())
        return 0
    try:
        if risco_texto(legenda):
            raise IG.ApiError(f"legenda com palavra de risco: {risco_texto(legenda)}")
        token, ig = IG.conta()
        video, capa = IG.url_publica(pasta, "video.mp4"), IG.url_publica(pasta, "capa.jpg")
        IG.conferir_urls([video, capa])
        c = IG.call("POST", f"{ig}/media", token, media_type="REELS", video_url=video, cover_url=capa,
                    caption=legenda, share_to_feed="true")
        IG.esperar(c["id"], token, tentativas=90, pausa=10)
        try:
            pub = IG.call("POST", f"{ig}/media_publish", token, creation_id=c["id"])
        except IG.ApiError:
            achado = IG._ja_publicado(legenda, ig, token)
            if not achado:
                raise
            pub = {"id": achado["id"]}
        res.update(ok=True, media_id=pub["id"])
        try:
            res["permalink"] = IG.call("GET", pub["id"], token, fields="permalink").get("permalink")
        except IG.ApiError as e:
            print("sem link:", e)
    except IG.ApiError as e:
        res.update(ok=False, erro=str(e))
    saida.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
