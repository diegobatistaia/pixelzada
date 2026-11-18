"""Avalia um canal da Twitch como fonte de imagens para os vídeos longos (Diego, 18/11/2026).

    python -m scripts.longo.twitch_fonte <login> <pasta_saida>

Grava relatorio.json (canal, live, vídeos, clipes) e folha.jpg com quadros dos clipes mais vistos.
Usa TWITCH_CLIENT_ID_PIXELZADA / TWITCH_CLIENT_SECRET_PIXELZADA (nunca imprime).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def tok() -> str:
    d = urllib.parse.urlencode({"client_id": os.environ["TWITCH_CLIENT_ID_PIXELZADA"],
                                "client_secret": os.environ["TWITCH_CLIENT_SECRET_PIXELZADA"],
                                "grant_type": "client_credentials"}).encode()
    return json.loads(urllib.request.urlopen("https://id.twitch.tv/oauth2/token", d, timeout=30).read())["access_token"]


def helix(t: str, rota: str, **q) -> list:
    url = f"https://api.twitch.tv/helix/{rota}?{urllib.parse.urlencode(q)}"
    r = urllib.request.Request(url, headers={"Client-Id": os.environ["TWITCH_CLIENT_ID_PIXELZADA"],
                                             "Authorization": f"Bearer {t}"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read()).get("data", [])


def main(login: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    t = tok()
    u = helix(t, "users", login=login)
    if not u:
        raise SystemExit("canal não encontrado")
    u = u[0]
    rel = {"canal": u, "canal_info": helix(t, "channels", broadcaster_id=u["id"]),
           "live": helix(t, "streams", user_id=u["id"]),
           "videos": helix(t, "videos", user_id=u["id"], first=20),
           "clipes": helix(t, "clips", broadcaster_id=u["id"], first=40,
                           started_at="2026-11-01T00:00:00Z")}
    (out / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1))
    print(f"canal {u['display_name']}: {u['description'][:200]!r}")
    print(f"live agora: {bool(rel['live'])} {rel['live'][0]['title'] if rel['live'] else ''}")
    for v in rel["videos"][:20]:
        print(f"video {v['type']} {v['created_at'][:16]} {v['duration']} views={v['view_count']} {v['title'][:80]}")
    for c in rel["clipes"][:40]:
        print(f"clipe {c['created_at'][:16]} {c['duration']}s views={c['view_count']} {c['title'][:70]} {c['url']}")
    # quadros: 6 clipes mais vistos + último vídeo (3 pontos)
    quadros = []
    alvos = [(c["url"], c["duration"]) for c in sorted(rel["clipes"], key=lambda c: -c["view_count"])[:6]]
    if rel["videos"]:
        v = rel["videos"][0]
        alvos.append((v["url"], 0))
    for i, (url, dur) in enumerate(alvos):
        try:
            lnk = subprocess.run(["yt-dlp", "-g", "-f", "best[height<=720]/best", url], capture_output=True,
                                 text=True, timeout=120).stdout.strip().splitlines()[0]
        except Exception as e:  # noqa: BLE001
            print(f"sem link {url}: {e}")
            continue
        pontos = [dur * f for f in (.2, .5, .8)] if dur else [600, 3600, 7200]
        for j, s in enumerate(pontos):
            q = out / f"q{i}-{j}.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(s), "-i", lnk, "-frames:v", "1",
                            "-vf", "scale=480:-2", str(q)], timeout=120)
            if q.exists():
                quadros.append(q)
    if quadros:
        from PIL import Image
        c = 3
        g = Image.new("RGB", (480 * c, 270 * ((len(quadros) + c - 1) // c)))
        for k, q in enumerate(quadros):
            g.paste(Image.open(q).convert("RGB").resize((480, 270)), ((k % c) * 480, (k // c) * 270))
        g.save(out / "folha.jpg", quality=85)
        for q in quadros:
            q.unlink()


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
