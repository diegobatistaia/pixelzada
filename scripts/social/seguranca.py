"""Barreira contra nudez nos Reels (Diego, 16/11).

Em 15/11 o Instagram marcou o Reel "Defendendo o Eren de uma onda de titãs" (Attack on
Titan 3) como "Nudez ou atividade sexual": os titãs são corpos humanos nus, sem órgãos,
mas o filtro automático da Meta não diferencia. Violação assim tira a conta da
monetização. Daqui para a frente nenhum vídeo desse tipo entra na fila:

1. Texto (sem internet): legenda do concorrente, título e legenda do Reel não podem ter
   palavras de risco (titãs, biquíni, sem camisa, sensual, twerk...). Usado na lista da
   pesquisa (pesquisa.py), na montagem e de novo na hora de publicar (reels.py).
2. Imagem: 8 quadros do vídeo vão para o modelo de visão do GitHub Models (o mesmo
   GITHUB_TOKEN que escreve os títulos), que diz se há corpo nu ou quase nu, roupa de
   banho ou íntima em destaque, torso nu em close, dança ou pose sexual. Risco médio
   ou alto = o vídeo não entra (montagem.py) ou sai da fila (varrer), com registro em
   social/reels/barrados.json.

    python -m scripts.social.seguranca texto "legenda..."      palavras de risco
    python -m scripts.social.seguranca conferir video.mp4 ...   checagem visual
    python -m scripts.social.seguranca varrer                   confere os agendados ainda não conferidos
    python -m scripts.social.seguranca varrer --slugs a,b       confere estes (mesmo publicados), só relatório
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from .pauta import ROOT, TZ

# Palavras de risco (comparadas sem acento e em minúsculas, como palavra inteira). Jogos/franquias cujo conteúdo costuma ser
# barrado pelo filtro de nudez da Meta entram aqui também.
PALAVRAS_RISCO = [
    # nudez e corpo
    "nude", "nudes", "nudez", "nudity", "naked", "pelado", "pelados", "peladas", "sem roupa", "sem camisa", "shirtless", "topless",
    "seminu", "semi nu", "semi-nu", "seios", "boobs", "bunda", "booty", "thicc", "rabuda",
    "gostosa", "corpao", "abdomen", "tanquinho",
    # roupa de banho / íntima
    "biquini", "bikini", "sunga", "lingerie", "calcinha", "cueca", "fio dental", "swimsuit", "underwear",
    # sexual / sugestivo
    "sexy", "sensual", "sexo", "sexual", "sex", "nsfw", "+18", "18+", "onlyfans", "only fans",
    "twerk", "rebolando", "rebolada", "stripper", "strip club", "striptease", "pole dance", "lap dance",
    "hentai", "ecchi", "waifu", "thirst trap", "hot girl", "fanservice", "fan service",
    # jogos/temas que o filtro costuma barrar
    "attack on titan", "shingeki", "aot", "tita", "titas", "titan", "titans",
    "dead or alive", "doa xtreme", "senran kagura", "nikke", "stellar blade",
]
# Exceções: nomes que contêm uma palavra de risco mas não são risco.
EXCECOES = ["titanfall", "titan quest", "titanic"]
_EXCECOES_RE = [re.compile(r"(?<![a-z0-9])" + re.escape(e)) for e in EXCECOES]


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


# "*" no fim = começo de palavra ("pelad*" pega pelado, pelada).
_RISCO_RE = [(p.rstrip("*"), re.compile(r"(?<![a-z0-9])" + re.escape(_sem_acento(p.rstrip("*")))
                                        + ("" if p.endswith("*") else r"(?![a-z0-9])")))
             for p in PALAVRAS_RISCO]


def risco_texto(*textos: str) -> list[str]:
    """Palavras de risco encontradas (lista vazia = ok)."""
    t = _sem_acento(" ".join(x or "" for x in textos))
    for e in _EXCECOES_RE:
        t = e.sub(" ", t)
    return [p for p, rx in _RISCO_RE if rx.search(t)]


# ---------------------------------------------------------------------------
# Imagem
# ---------------------------------------------------------------------------
PROMPT_VISUAL = """Você é o moderador de um perfil de games no Instagram que NÃO pode receber
violação de "Nudez ou atividade sexual". O filtro automático da Meta é rígido: ele marca até
personagens de jogo ou monstros humanoides nus sem órgãos (ex.: titãs de Attack on Titan),
corpos de pele exposta em close, biquíni, roupa íntima e dança sensual, mesmo em jogo ou desenho.

A imagem é uma folha com 8 quadros do mesmo vídeo. Responda SÓ um JSON:
{"risco": "alto" | "medio" | "baixo", "motivo": "frase curta em português"}

alto: qualquer corpo humano ou humanoide nu ou quase nu (real, jogo, desenho ou monstro),
nádegas/seios/virilha em destaque, ato ou pose sexual, dança sensual (twerk, pole dance),
roupa íntima.
medio: biquíni, sunga ou maiô em destaque, torso nu ocupando boa parte do quadro, close em
corpo/decote, praia ou piscina com corpos em destaque, beijo intenso.
baixo: nada disso (violência de jogo, armas, carros, rostos, pessoas vestidas, multidão
vestida, pessoa sem camisa pequena e distante no fundo)."""

MODELO = os.environ.get("MODELO_VISAO", "openai/gpt-4.1-mini")


def folha_quadros(video: Path, destino: Path, n: int = 8) -> Path | None:
    """Folha 4x2 com n quadros espalhados pelo vídeo (640 px de largura, leve: o GitHub
    Models respondeu "OK" sem JSON para a folha de 1024 px em 16/11)."""
    ff = shutil.which("ffmpeg")
    fp = shutil.which("ffprobe")
    if not ff or not fp:
        return None
    try:
        dur = float(subprocess.check_output([fp, "-v", "error", "-show_entries", "format=duration",
                                             "-of", "csv=p=0", str(video)], text=True).strip() or 0)
    except (subprocess.CalledProcessError, ValueError):
        return None
    if dur <= 0:
        return None
    fps = n / dur
    r = subprocess.run([ff, "-v", "error", "-y", "-i", str(video), "-vf",
                        f"fps={fps:.5f},scale=160:-2,tile=4x2", "-frames:v", "1", "-q:v", "6", str(destino)],
                       capture_output=True)
    return destino if r.returncode == 0 and destino.exists() else None


def conferir_visual(video: Path) -> dict:
    """{"risco": alto|medio|baixo|desconhecido, "motivo": ...}"""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return {"risco": "desconhecido", "motivo": "sem GITHUB_TOKEN (GitHub Models)"}
    with tempfile.TemporaryDirectory() as tmp:
        folha = folha_quadros(video, Path(tmp) / "folha.jpg")
        if not folha:
            return {"risco": "desconhecido", "motivo": "não deu para tirar quadros do vídeo"}
        img = base64.b64encode(folha.read_bytes()).decode()
    corpo = {
        "model": MODELO, "temperature": 0,
        "messages": [
            {"role": "system", "content": PROMPT_VISUAL},
            {"role": "user", "content": [
                {"type": "text", "text": "Classifique o risco desta folha de quadros."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}", "detail": os.environ.get("DETALHE_VISAO", "low")}},
            ]},
        ],
    }
    req = urllib.request.Request("https://models.github.ai/inference/chat/completions",
                                 data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                          "Accept": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            bruto = r.read().decode("utf-8", "replace")
        try:
            txt = json.loads(bruto)["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            return {"risco": "desconhecido", "motivo": f"resposta inesperada ({len(bruto)} bytes): {bruto[:200]!r}"}
        dado = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        risco = _sem_acento(str(dado.get("risco", ""))).strip()
        if risco not in ("alto", "medio", "baixo"):
            return {"risco": "desconhecido", "motivo": f"resposta fora do padrão: {txt[:120]!r}"}
        return {"risco": risco, "motivo": str(dado.get("motivo", ""))[:200]}
    except urllib.error.HTTPError as e:
        return {"risco": "desconhecido", "motivo": f"GitHub Models HTTP {e.code}: "
                                                   f"{e.read().decode('utf-8', 'replace')[:150]}"}
    except Exception as e:  # rede, JSON etc.
        return {"risco": "desconhecido", "motivo": f"GitHub Models indisponível ({str(e)[:150]})"}


def barrar(risco: str) -> bool:
    return risco in ("alto", "medio")


def checagem(video: Path, *textos: str) -> dict:
    """Texto + imagem. Devolve o registro gravado na fila em item["checagem"]."""
    palavras = risco_texto(*textos)
    if palavras:
        return {"risco": "alto", "motivo": "palavras de risco: " + ", ".join(palavras), "por": "texto",
                "em": datetime.now(TZ).isoformat(timespec="seconds")}
    v = conferir_visual(video)
    return {**v, "por": "imagem", "em": datetime.now(TZ).isoformat(timespec="seconds")}


# ---------------------------------------------------------------------------
# Varredura da fila
# ---------------------------------------------------------------------------
BARRADOS = ROOT / "social" / "reels" / "barrados.json"


def registrar_barrado(registro: dict) -> None:
    """Histórico do que foi barrado (o vídeo não volta: o link fica marcado como usado)."""
    lista = json.loads(BARRADOS.read_text(encoding="utf-8")) if BARRADOS.exists() else []
    lista.append(registro)
    BARRADOS.write_text(json.dumps(lista, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tirar_da_fila(fila: list[dict], item: dict, motivo: dict) -> None:
    """Tira o Reel da fila (o horário fica livre para o piso automático) e apaga o vídeo."""
    from . import reels as R
    fila.remove(item)
    for ext in ("mp4", "jpg"):
        (R.PASTA / "videos" / f"{item['slug']}.{ext}").unlink(missing_ok=True)
    registrar_barrado({"slug": item["slug"], "data": item["data"], "horario": item["horario"],
                       "link": (item.get("origem") or {}).get("link"), "legenda": item.get("legenda", ""),
                       **motivo})


def varrer(slugs: list[str] | None = None, so_imagem: bool = False) -> int:
    from . import reels as R
    fila = R.carregar()
    videos = R.PASTA / "videos"
    if slugs:  # só relatório
        for s in slugs:
            item = next((i for i in fila if i["slug"] == s), {"slug": s, "legenda": ""})
            c = ({**conferir_visual(videos / f"{s}.mp4"), "por": "imagem"} if so_imagem
                 else checagem(videos / f"{s}.mp4", item.get("legenda", "")))
            time.sleep(4)
            print(f"{s}: risco {c['risco']} ({c['por']}): {c['motivo']}")
        return 0
    agora = datetime.now(TZ)
    alvo = [i for i in fila if i["status"] == "agendado" and R.quando(i) > agora
            and (i.get("checagem") or {}).get("risco") in (None, "desconhecido")]
    print(f"{len(alvo)} Reel(s) agendado(s) sem checagem de nudez")
    tirados = 0
    for n, item in enumerate(alvo):
        if n:
            time.sleep(4)  # GitHub Models grátis: ~15 pedidos por minuto
        c = checagem(videos / f"{item['slug']}.mp4", item.get("legenda", ""))
        print(f"  {item['slug']} ({item['data']} {item['horario']}): risco {c['risco']} ({c['por']}): {c['motivo']}")
        if barrar(c["risco"]):
            tirar_da_fila(fila, item, c)
            tirados += 1
            print(f"  AVISO: {item['slug']} saiu da fila (risco de violação de nudez)")
        else:
            item["checagem"] = c
    R.salvar(fila)
    print(f"{tirados} Reel(s) tirado(s) da fila; o piso automático preenche os horários vazios")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("texto")
    t.add_argument("texto", nargs="+")
    c = sub.add_parser("conferir")
    c.add_argument("videos", nargs="+")
    v = sub.add_parser("varrer")
    v.add_argument("--slugs", default="")
    v.add_argument("--so-imagem", action="store_true", help="com --slugs: pula o texto e testa só a imagem")
    a = ap.parse_args(argv)
    if a.cmd == "texto":
        p = risco_texto(*a.texto)
        print("risco: " + ", ".join(p) if p else "ok")
        return 1 if p else 0
    if a.cmd == "conferir":
        for f in a.videos:
            print(f"{f}: {conferir_visual(Path(f))}")
        return 0
    return varrer([s for s in a.slugs.split(",") if s.strip()] or None, a.so_imagem)


if __name__ == "__main__":
    sys.exit(main())
