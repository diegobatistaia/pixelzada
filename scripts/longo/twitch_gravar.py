"""Grava trechos curtos de uma live da Twitch SÓ DE JOGO (sem câmera) para os vídeos longos.

    python -m scripts.longo.twitch_gravar <login> <pasta> [minutos=20] [a_cada=40] [dur=8]

A cada `a_cada` segundos grava `dur` s em 720p SEM ÁUDIO (o som vai fora: narração + trilha).
Grava folha.jpg (um quadro de cada trecho, numerado) e indice.json para escolher as cenas.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def link(login: str) -> str:
    r = subprocess.run(["yt-dlp", "-g", "-f", "best[height<=1080]/best", f"https://www.twitch.tv/{login}"],
                       capture_output=True, text=True, timeout=120)
    return r.stdout.strip().splitlines()[0]


def main(login: str, pasta: Path, minutos: float = 20, a_cada: int = 40, dur: int = 8) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    indice = json.loads((pasta / "indice.json").read_text()) if (pasta / "indice.json").exists() else []
    n0 = len(indice)
    fim = time.time() + minutos * 60
    lnk, k = link(login), n0
    while time.time() < fim:
        t0 = time.time()
        arq = pasta / f"t{k:03d}.mp4"
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", lnk, "-t", str(dur), "-an",
                            "-vf", "scale=-2:720,fps=30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                            str(arq)], timeout=120)
        if r.returncode != 0 or not arq.exists() or arq.stat().st_size < 50_000:
            arq.unlink(missing_ok=True)
            try:
                lnk = link(login)  # link expira ou intervalo comercial
            except Exception:  # noqa: BLE001
                break
        else:
            indice.append({"arquivo": arq.name, "gravado": datetime.now(timezone.utc).isoformat()[:19]})
            k += 1
        time.sleep(max(0, a_cada - (time.time() - t0)))
    (pasta / "indice.json").write_text(json.dumps(indice, indent=1))
    # folha com o quadro do meio de cada trecho novo
    from PIL import Image, ImageDraw
    novos = indice[n0:]
    if not novos:
        print("nada gravado")
        return
    c = 5
    g = Image.new("RGB", (384 * c, 236 * ((len(novos) + c - 1) // c)))
    d = ImageDraw.Draw(g)
    for i, it in enumerate(novos):
        q = pasta / "q.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(dur / 2), "-i", str(pasta / it["arquivo"]),
                        "-frames:v", "1", "-vf", "scale=384:216", str(q)])
        g.paste(Image.open(q), ((i % c) * 384, (i // c) * 236))
        d.text(((i % c) * 384 + 4, (i // c) * 236 + 218), it["arquivo"], fill="white")
        q.unlink()
    g.save(pasta / f"folha-{n0:03d}.jpg", quality=85)
    print(f"{len(novos)} trechos gravados")


if __name__ == "__main__":
    a = sys.argv
    main(a[1], Path(a[2]), *(float(x) if i == 0 else int(x) for i, x in enumerate(a[3:6])))
