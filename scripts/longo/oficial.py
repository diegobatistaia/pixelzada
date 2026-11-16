"""Banco de material OFICIAL da Rockstar para os vídeos longos (roda no GitHub Actions).

Lê as páginas oficiais do GTA VI (site, galeria de lançamento, mídia, Only in Leonida e
subpáginas), junta as imagens e vídeos e baixa para trabalho/oficial/. Com --folhas grava
miniaturas e um índice em previas/longo/_oficial/ para escolher o que entra no vídeo.

    python -m scripts.longo.oficial [--folhas]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BASE = "https://www.rockstargames.com"
TRAB = RAIZ / "trabalho/oficial"
PREV = RAIZ / "previas/longo/_oficial"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
PAGINAS = ["/VI", "/VI/launch-gallery", "/VI/media", "/VI/only-in-leonida", "/VI/music"]
PULA = re.compile(r"(_av1\.|zh_|ja_|ko_|fr_fr|_Mobile|Mobile\.|mobile|shard\d|wm-|favicon|logo_|poster_logo|GTA_PLUS|FOB_|collectors)", re.I)
MIDIA = re.compile(r'(?:https://[a-z0-9.-]+)?/VI/_next/static/media/[A-Za-z0-9_.~-]+\.(?:jpg|jpeg|png|webp|mp4)'
                   r'|https://[a-z0-9.-]*(?:akamaized|rockstargames)[a-z0-9./-]*/[A-Za-z0-9_./~%-]+\.(?:jpg|jpeg|png|webp|mp4)')


def get(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()


def coletar() -> dict:
    vistos, fila, midia = set(), list(PAGINAS), {}
    while fila and len(vistos) < 40:
        p = fila.pop(0)
        if p in vistos:
            continue
        vistos.add(p)
        try:
            html = get(BASE + p).decode("utf8", "ignore")
        except Exception as e:  # noqa: BLE001
            print("falhou", p, e)
            continue
        for sub in set(re.findall(r'\\?"(/VI/(?:only-in-leonida|launch-gallery|media|people|places)[a-z0-9/_-]*)\\?"', html)):
            if sub not in vistos and sub not in fila:
                fila.append(sub)
        for m in MIDIA.findall(html):
            url = m if m.startswith("http") else BASE + m
            if PULA.search(url):
                continue
            midia.setdefault(url, p)
        print(f"{p}: {len(html)} bytes; total {len(midia)} arquivos")
    return {"paginas": sorted(vistos), "midia": midia}


def baixar(ind: dict) -> list[dict]:
    TRAB.mkdir(parents=True, exist_ok=True)
    itens, total = [], 0
    for url, pag in ind["midia"].items():
        if total > 900_000_000:
            print("limite de 900 MB atingido")
            break
        nome = url.rsplit("/", 1)[1]
        dest = TRAB / nome
        if not dest.exists():
            try:
                dest.write_bytes(get(url))
            except Exception as e:  # noqa: BLE001
                print("não baixou", nome, e)
                continue
        total += dest.stat().st_size
        print(f"  {nome} {dest.stat().st_size // 1000} KB", flush=True)
        itens.append({"nome": nome, "url": url, "pagina": pag, "bytes": dest.stat().st_size})
    return itens


def folhas(itens: list[dict]) -> None:
    PREV.mkdir(parents=True, exist_ok=True)
    for it in itens:
        src = TRAB / it["nome"]
        mini = PREV / (it["nome"].rsplit(".", 1)[0] + ".jpg")
        if it["nome"].endswith(".mp4"):
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                "default=nw=1:nk=1", str(src)], capture_output=True, text=True)
            it["dur"] = float(r.stdout.strip() or 0)
            passo = max(1.0, it["dur"] / 12)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf",
                            f"fps=1/{passo:.2f},scale=320:-2,tile=4x3:padding=3", "-frames:v", "1", str(mini)])
        else:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", "scale=480:-2", str(mini)])
    (PREV / "indice.json").write_text(json.dumps(itens, ensure_ascii=False, indent=1))


def main() -> int:
    ind = coletar()
    itens = baixar(ind)
    print(f"{len(itens)} arquivos oficiais baixados")
    if "--folhas" in sys.argv:
        folhas(itens)
    return 0


if __name__ == "__main__":
    sys.exit(main())
