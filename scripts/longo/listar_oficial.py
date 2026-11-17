"""Lista TUDO o que o site oficial do GTA VI (e páginas de jogos antigos da Rockstar) oferece:
imagens, vídeos mp4, ids de YouTube. Grava índice + miniaturas das imagens em previas/longo/_lista/."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
OUT = RAIZ / "previas/longo/_lista"
BASE = "https://www.rockstargames.com"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
PAGS = ["/VI", "/VI/media", "/VI/media/videos", "/VI/media/screenshots", "/VI/media/artwork-wallpapers",
        "/VI/only-in-leonida", "/VI/launch-gallery", "/games/vicecity", "/games/vicecitystories", "/games/grandtheftautov",
        "/gta-v", "/games/gta-trilogy", "/gta-trilogy", "/games/info/gta-trilogy", "/games/vicecity/screens"]
MID = re.compile(r'(?:https://[a-z0-9.-]+)?/[A-Za-z0-9_./~%-]*?\.(?:jpg|jpeg|png|webp|mp4|m3u8)')


def get(u):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read().decode("utf8", "ignore")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    vistos, fila, itens, yt = set(), list(PAGS), {}, {}
    while fila and len(vistos) < 70:
        p = fila.pop(0)
        if p in vistos:
            continue
        vistos.add(p)
        try:
            h = get(BASE + p)
        except Exception as e:  # noqa: BLE001
            print("falhou", p, e)
            continue
        (OUT / ("pag" + re.sub(r"[^a-z0-9]+", "-", p.lower()) + ".html")).write_text(h[:4_000_000])
        for sub in set(re.findall(r'\\?"(/VI/(?:only-in-leonida|media|people|places)[a-z0-9/_-]*)\\?"', h)):
            if sub not in vistos:
                fila.append(sub)
        for m in MID.findall(h):
            u = m if m.startswith("http") else BASE + m
            if re.search(r"(_av1\.|zh_|ja_|ko_|fr_fr|Mobile|mobile|shard\d|favicon|wm-)", u):
                continue
            itens.setdefault(u, p)
        for v in re.findall(r'(?:youtube\.com/(?:embed/|watch\?v=)|youtu\.be/|"youtubeId"\s*:\s*"|videoId\\?"\s*:\s*\\?")([A-Za-z0-9_-]{11})', h):
            yt.setdefault(v, p)
        print(p, len(h), len(itens), flush=True)
    (OUT / "indice.json").write_text(json.dumps({"itens": itens, "youtube": yt, "paginas": sorted(vistos)}, indent=1))
    mini = OUT / "mini"
    mini.mkdir(exist_ok=True)
    lst = [u for u in itens if re.search(r"\.(jpg|jpeg|png|webp)$", u) and not re.search(r"ULTIMATE|VINTAGE|GTAVI_FOB|logo|poster_logo|intro", u)]
    Path("/tmp/l.txt").write_text("\n".join(lst))
    subprocess.run("xargs -P 8 -I{} sh -c 'curl -sfL --max-time 60 -o /tmp/img_$(basename {}) {} && "
                   f"ffmpeg -y -loglevel error -i /tmp/img_$(basename {{}}) -vf scale=360:-2 {mini}/$(basename {{}}).jpg' < /tmp/l.txt",
                   shell=True)
    print(len(lst), "imagens")
    return 0


if __name__ == "__main__":
    sys.exit(main())
