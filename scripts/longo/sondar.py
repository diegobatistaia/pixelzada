"""Sonda de material para o vídeo longo (roda no GitHub Actions).

1. baixa o Reel de referência do Diego (API da Meta / yt-dlp), transcreve (faster-whisper)
   e tira uma folha de quadros;
2. testa as fontes oficiais da Rockstar: trailers (canal oficial) e imagens do site do GTA VI.

Grava tudo em previas/longo/_sonda/. Não publica nada.

    python -m scripts.longo.sondar <link do reel>
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "previas/longo/_sonda"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}


def run(*a, timeout=600):
    r = subprocess.run([str(x) for x in a], capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)[-800:]


def baixar_reel(url: str) -> Path | None:
    sys.path.insert(0, str(RAIZ))
    from scripts.social import pesquisa as P
    cfg = P.carregar_config(P.CONFIG_PADRAO)
    try:
        token, ig_id = P.conta(cfg)
    except Exception as e:  # noqa: BLE001
        print("sem chave da Meta:", e)
        token, ig_id = "", ""
    achado = P.dados_do_link(cfg, url, token, ig_id)
    if not achado:
        return None
    c, cache = achado
    (SAIDA / "reel.json").write_text(json.dumps(c, ensure_ascii=False, indent=1))
    nome = P.baixar_um(cfg, c, SAIDA / "tmp", token, ig_id, cache)
    if not nome:
        return None
    final = SAIDA / "reel.mp4"
    Path(nome).rename(final)
    return final


def folha(video: Path, nome: str, passo: float = 2.0) -> None:
    run("ffmpeg", "-y", "-v", "error", "-i", video, "-vf",
        f"fps=1/{passo},scale=270:-2,tile=6x6:padding=4", "-frames:v", "4", SAIDA / f"{nome}-%d.jpg")


def transcrever(video: Path) -> None:
    from faster_whisper import WhisperModel
    m = WhisperModel("small", compute_type="int8")
    segs, info = m.transcribe(str(video), language="pt", word_timestamps=False)
    linhas = [f"[{s.start:6.1f}-{s.end:6.1f}] {s.text.strip()}" for s in segs]
    (SAIDA / "reel-transcricao.txt").write_text("\n".join(linhas))
    print("\n".join(linhas))


def sondar_rockstar() -> None:
    rel = {}
    for nome, url in {"trailer1": "https://www.youtube.com/watch?v=QdBZY2fkU-0",
                      "trailer2": "https://www.youtube.com/watch?v=VQRLujxTm3c"}.items():
        dest = SAIDA / "tmp" / f"{nome}.mp4"
        code, out = run("yt-dlp", "--no-playlist", "-f", "bv*[height<=720][ext=mp4]/b[height<=720]",
                        "-o", dest, url, timeout=400)
        ok = dest.exists()
        rel[nome] = {"ok": ok, "log": out[-300:]}
        if ok:
            folha(dest, nome, 4)
    # site oficial
    for nome, url in {"site": "https://www.rockstargames.com/VI",
                      "site_pt": "https://www.rockstargames.com/br/VI",
                      "news": "https://www.rockstargames.com/newswire?tag_id=702"}.items():
        try:
            html = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode("utf8", "ignore")
            imgs = sorted(set(re.findall(r"https://media-rockstargames-com\.akamaized\.net/[^\"' )]+?\.(?:jpg|jpeg|png|webp)", html)))
            imgs += sorted(set(re.findall(r"https://[a-z0-9.-]*rockstargames\.com/[^\"' )]+?\.(?:jpg|jpeg|png|webp)", html)))
            rel[nome] = {"ok": True, "tam": len(html), "imagens": imgs[:300]}
            (SAIDA / f"{nome}.html").write_text(html[:3_000_000])
        except Exception as e:  # noqa: BLE001
            rel[nome] = {"ok": False, "erro": str(e)[:300]}
    (SAIDA / "rockstar.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1))
    print(json.dumps({k: {kk: (vv if kk != "imagens" else len(vv)) for kk, vv in v.items()} for k, v in rel.items()}, indent=1))


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    (SAIDA / "tmp").mkdir(exist_ok=True)
    url = sys.argv[1]
    v = None
    try:
        v = baixar_reel(url)
    except Exception as e:  # noqa: BLE001
        print("reel falhou:", e)
    if v:
        run("ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", v)
        folha(v, "reel", 1.5)
        try:
            transcrever(v)
        except Exception as e:  # noqa: BLE001
            print("transcrição falhou:", e)
    else:
        print("REEL NÃO BAIXOU")
    sondar_rockstar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
