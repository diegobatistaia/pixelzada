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


def baixar(ind: dict, so: list[str] | None = None) -> list[dict]:
    """Baixa em paralelo com curl (tempo máximo por arquivo). so = prefixos de nome que interessam."""
    TRAB.mkdir(parents=True, exist_ok=True)
    alvos = [(u, p) for u, p in ind["midia"].items()
             if not so or any(u.rsplit("/", 1)[1].startswith(x) for x in so)]
    lista = TRAB / "_urls.txt"
    lista.write_text("".join(f"{u}\n" for u, _ in alvos if not (TRAB / u.rsplit("/", 1)[1]).exists()))
    print(f"baixando {len(alvos)} arquivos", flush=True)
    subprocess.run(f"xargs -P 8 -I{{}} sh -c 'curl -sfL --retry 3 --connect-timeout 20 --max-time 600 "
                   f"-A \"{UA['User-Agent']}\" -o \"{TRAB}/$(basename {{}})\" {{}} || echo FALHOU {{}}' < {lista}",
                   shell=True)
    itens = []
    for url, pag in alvos:
        dest = TRAB / url.rsplit("/", 1)[1]
        if dest.exists() and dest.stat().st_size > 1000:
            itens.append({"nome": dest.name, "url": url, "pagina": pag, "bytes": dest.stat().st_size})
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
    so = None
    if "--episodio" in sys.argv:
        ep = json.loads(Path(sys.argv[sys.argv.index("--episodio") + 1]).read_text(encoding="utf-8"))
        so = sorted({p["v"][2:] for c in ep["cenas"] for p in c["planos"] if p["v"].startswith("o:")}
                    | {ep["capa"]["imagem"], "GTAVI_Launch_Trailer", "GTAVI_Pre-Load_Now"})
    itens = baixar(ind, so)
    if "--episodio" in sys.argv:  # vídeos longos citados como v:<nome>:<segundo>
        from scripts.longo.cenas import VIDEOS
        for nome in {p["v"].split(":")[1] for c in ep["cenas"] for p in c["planos"] if p["v"].startswith("v:")}:
            url = VIDEOS.get(nome)
            dest = TRAB / url.rsplit("/", 1)[1] if url else None
            if not dest:
                continue
            for tent in range(5):  # download às vezes vem cortado (sem "moov"): confere e tenta de novo
                if dest.exists() and subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                                     "-of", "csv=p=0", str(dest)], capture_output=True).returncode == 0:
                    break
                dest.unlink(missing_ok=True)
                print("baixando", nome, f"(tentativa {tent + 1})", flush=True)
                subprocess.run(["curl", "-sfL", "--retry", "5", "--retry-all-errors", "--max-time", "900",
                                "-A", UA["User-Agent"], "-o", str(dest), url])
            else:
                raise SystemExit(f"vídeo {nome} não baixou inteiro")
    print(f"{len(itens)} arquivos oficiais baixados")
    if "--folhas" in sys.argv:
        folhas(itens)
    return 0


if __name__ == "__main__":
    sys.exit(main())
