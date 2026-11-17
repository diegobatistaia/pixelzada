"""Mapa de cenas dos vídeos oficiais (para escolher trechos que casam com a fala) e imagens
oficiais de jogos antigos pela loja Steam (capturas da própria Rockstar).

    python -m scripts.longo.cenas

Grava em previas/longo/_cenas/: folhas com miniatura + tempo de cada corte de cena, cenas.json
e steam.json (URLs das capturas e trailers oficiais dos jogos antigos)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RAIZ = Path(__file__).resolve().parents[2]
OUT = RAIZ / "previas/longo/_cenas"
OFI = RAIZ / "trabalho/oficial"
DL = "https://media-rockstargames-com.akamaized.net/VI/downloads/videos"
VIDEOS = {"extended": f"{DL}/GTAVI_An_Extended_Look/GTAVI_An_Extended_Look.mp4",
          "trailer1": f"{DL}/GTAVI_Trailer_1/GTAVI_Trailer_1.mp4",
          "trailer2": f"{DL}/GTAVI_Trailer_2/GTAVI_Trailer_2.mp4",
          "launch": f"{DL}/GTAVI_Launch_Trailer/GTAVI_Launch_Trailer.mp4"}
STEAM = {"vicecity2002": 12110, "vicecity_de": 1546990, "gta5": 271590, "sanandreas": 12120, "gta3": 12100}
UA = {"User-Agent": "Mozilla/5.0"}


def baixar(url: str, dest: Path):
    if not dest.exists():
        subprocess.run(["curl", "-sfL", "--retry", "3", "--max-time", "900", "-o", str(dest), url], check=True)


def cortes(video: Path) -> list[float]:
    r = subprocess.run(["ffmpeg", "-i", str(video), "-vf", "scale=320:-2,select='gt(scene,0.32)',showinfo", "-an",
                        "-f", "null", "-"], capture_output=True, text=True)
    ts = [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    out, ult = [0.0], 0.0
    for t in ts:
        if t - ult >= 1.0:
            out.append(round(t, 2))
            ult = t
    return out


def folha(nome: str, video: Path, ts: list[float]):
    f = ImageFont.truetype(str(RAIZ / "scripts/social/gerador/fonts/f2.ttf"), 22)
    tiles = []
    for t in ts:
        meio = t + 0.6
        tmp = Path(f"/tmp/c_{nome}_{t}.jpg")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{meio:.2f}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=320:-2", str(tmp)])
        if tmp.exists():
            tiles.append((t, Image.open(tmp).convert("RGB")))
    por = 48
    for k in range(0, len(tiles), por):
        grupo = tiles[k:k + por]
        h = grupo[0][1].height + 26
        s = Image.new("RGB", (8 * 320, ((len(grupo) + 7) // 8) * h), "black")
        d = ImageDraw.Draw(s)
        for i, (t, im) in enumerate(grupo):
            x, y = (i % 8) * 320, (i // 8) * h
            s.paste(im, (x, y))
            d.text((x + 4, y + im.height), f"{nome} {t:.1f}s", font=f, fill=(255, 230, 0))
        s.save(OUT / f"{nome}-{k // por + 1:02d}.jpg", quality=72)


def steam():
    res = {}
    for nome, app in STEAM.items():
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(
                f"https://store.steampowered.com/api/appdetails?appids={app}&l=portuguese", headers=UA), timeout=40).read())
            dd = d[str(app)]["data"]
            shots = [s["path_full"].split("?")[0] for s in dd.get("screenshots", [])]
            filmes = [{"nome": m.get("name"), "mp4": (m.get("mp4") or {}).get("max"), "hls": m.get("hls_h264")}
                      for m in dd.get("movies", [])]
            res[nome] = {"app": app, "titulo": dd.get("name"), "telas": shots, "filmes": filmes}
            mini = OUT / "steam"
            mini.mkdir(exist_ok=True)
            for i, u in enumerate(shots[:24]):
                tmp = Path(f"/tmp/s_{nome}_{i}.jpg")
                subprocess.run(["curl", "-sfL", "--max-time", "60", "-o", str(tmp), u])
                if tmp.exists():
                    im = Image.open(tmp).convert("RGB")
                    im.thumbnail((360, 220))
                    im.save(mini / f"{nome}_{i:02d}.jpg", quality=75)
            print(nome, len(shots), "telas", len(filmes), "filmes")
        except Exception as e:  # noqa: BLE001
            print("steam falhou", nome, e)
    (OUT / "steam.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))


GTA5_FILMES = {"gta5fp": 29, "gta5historia": 30, "gta5teaser": 31}  # trailers do modo história (Steam)


def gta5():
    """Telas e trailers do GTA 5 (modo história) da loja Steam, com folhas de cenas."""
    d = json.loads((OUT / "steam.json").read_text())["gta5"]
    mini = OUT / "steam"
    for i, u in enumerate(d["telas"]):
        alvo = mini / f"gta5_{i:02d}.jpg"
        if alvo.exists():
            continue
        tmp = Path(f"/tmp/g5_{i}.jpg")
        subprocess.run(["curl", "-sfL", "--max-time", "60", "-o", str(tmp), u])
        if tmp.exists():
            im = Image.open(tmp).convert("RGB")
            im.thumbnail((360, 220))
            im.save(alvo, quality=75)
    todos = json.loads((OUT / "cenas.json").read_text()) if (OUT / "cenas.json").exists() else {}
    for nome, i in GTA5_FILMES.items():
        dest = OFI / f"{nome}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", d["filmes"][i]["hls"], "-c", "copy", str(dest)])
        if not dest.exists():
            print("não baixou", nome)
            continue
        ts = cortes(dest)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                    "default=nw=1:nk=1", str(dest)], capture_output=True, text=True).stdout or 0)
        todos[nome] = {"arquivo": dest.name, "dur": dur, "cortes": ts}
        print(nome, f"{dur:.0f}s", len(ts), "cenas", flush=True)
        folha(nome, dest, ts)
    (OUT / "cenas.json").write_text(json.dumps(todos, indent=1))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    OFI.mkdir(parents=True, exist_ok=True)
    if "gta5" in sys.argv:
        gta5()
        return 0
    steam()
    todos = {}
    for nome, url in VIDEOS.items():
        dest = OFI / url.rsplit("/", 1)[1]
        try:
            baixar(url, dest)
        except Exception as e:  # noqa: BLE001
            print("não baixou", nome, e)
            continue
        ts = cortes(dest)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                    "default=nw=1:nk=1", str(dest)], capture_output=True, text=True).stdout or 0)
        todos[nome] = {"arquivo": dest.name, "dur": dur, "cortes": ts}
        print(nome, f"{dur:.0f}s", len(ts), "cenas", flush=True)
        folha(nome, dest, ts)
    (OUT / "cenas.json").write_text(json.dumps(todos, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
