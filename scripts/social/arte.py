"""Desenha os posts da Pixelzada: carrossel (1080x1350), Story e Reel (1080x1920).

A moldura vem de templates/social/ (marca.css e arte.html.j2, copiados da
identidade visual). Cada slide é uma página HTML fotografada pelo Chromium; o
Reel junta os slides num vídeo com o ffmpeg.

    python -m scripts.social.arte <slug>        desenha tudo em social/saida/<slug>/
"""
from __future__ import annotations

import io
import math
import re
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape

from . import pauta as P

TEMPLATES = P.ROOT / "templates" / "social"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class ArteError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Imagem do jogo
# ---------------------------------------------------------------------------
def obter_imagem(p: dict, pasta: Path) -> Path:
    """Baixa (ou copia) a imagem da pauta para a pasta de saída, em JPEG."""
    from PIL import Image

    img = p["imagem"]
    if img.get("path"):
        dados = (P.ROOT / img["path"]).read_bytes()
    else:
        import requests
        try:
            r = requests.get(img["url"], headers={"User-Agent": UA}, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            raise ArteError(f"não consegui baixar a imagem ({e})") from None
        dados = r.content
    try:
        im = Image.open(io.BytesIO(dados)).convert("RGB")
    except Exception:
        raise ArteError("o arquivo da imagem não é uma imagem válida") from None
    if im.width < 800:
        raise ArteError(f"imagem pequena demais ({im.width}x{im.height}); precisa de 800px de largura")
    destino = pasta / "foto.jpg"
    im.save(destino, "JPEG", quality=92)
    return destino


# ---------------------------------------------------------------------------
# HTML -> PNG
# ---------------------------------------------------------------------------
def _realce(texto: str, trecho: str | None, classe: str = "hl") -> Markup:
    texto = str(escape(texto))
    if trecho:
        t = str(escape(trecho))
        i = texto.lower().find(t.lower())
        if i >= 0:
            texto = f'{texto[:i]}<span class="{classe}">{texto[i:i + len(t)]}</span>{texto[i + len(t):]}'
    return Markup(texto)


def _negrito(texto: str) -> Markup:
    return Markup(re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", str(escape(texto))))


def _numero(texto: str) -> str:
    """Estilo Numerão sem campo "numero": o primeiro número do título."""
    m = re.search(r"\d+(?:[.,]\d+)?%?", texto or "")
    return m.group(0) if m else "!"


def _data(texto: str) -> dict:
    """Estilo Agenda: dia, mês, ano, dia da semana e a grade do mês (começa no domingo)."""
    import calendar
    from datetime import date
    try:
        d = date.fromisoformat(texto)
    except (TypeError, ValueError):
        d = date.today()
    semana = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"][d.weekday()]
    return {"dia": d.day, "mes": d.month, "ano": d.year, "semana": semana,
            "inicio": (date(d.year, d.month, 1).weekday() + 1) % 7,
            "total": calendar.monthrange(d.year, d.month)[1]}


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
    env.filters["realce"] = _realce
    env.filters["negrito"] = _negrito
    env.filters["regex_numero"] = _numero
    env.filters["data_iso"] = _data
    return env


class Desenhista:
    """Um Chromium aberto para desenhar vários slides seguidos."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch()
        except Exception:
            # Sessões na nuvem do Claude trazem o Chromium em /opt/pw-browsers.
            self._browser = self._pw.chromium.launch(executable_path=_chromium_local())
        self._page = self._browser.new_page(viewport={"width": 1080, "height": 1920})
        self._env = _env()
        return self

    def __exit__(self, *exc):
        self._browser.close()
        self._pw.stop()

    def desenhar(self, destino: Path, estilo: str | None = None, **ctx) -> list[str]:
        """Grava o PNG e devolve os problemas de encaixe medidos na página.
        estilo: um dos templates/social/estilos/ (só capa, miolo e final)."""
        html = destino.with_suffix(".html")
        tpl = self._env.get_template(f"estilos/{estilo}.html.j2" if estilo else "arte.html.j2")
        html.write_text(tpl.render(base=P.ROOT.as_uri(), **ctx), encoding="utf-8")
        self._page.goto(html.as_uri())
        self._page.evaluate("document.fonts.ready")
        self._page.wait_for_function("window.__medida !== undefined")
        medida = self._page.evaluate("window.__medida")
        self._page.locator("main.arte").screenshot(path=str(destino))
        html.unlink()
        return medida["erros"]


def _chromium_local() -> str:
    for c in sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome")):
        return str(c)
    raise ArteError("Chromium não encontrado")


def _contexto(p: dict, foto: Path | None) -> dict:
    cor, rotulo, _ = P.TIPOS[p["tipo"]]
    pos = p["imagem"].get("pos", "50% 40%")
    return {"p": p, "cor": cor, "rotulo_tipo": rotulo, "fonte": p["fonte"], "selos": P.SELOS,
            "credito": p["imagem"]["credito"], "img": foto.as_uri() if foto else None, "pos": pos}


def _jpeg(png: Path) -> Path:
    from PIL import Image
    jpg = png.with_suffix(".jpg")
    Image.open(png).convert("RGB").save(jpg, "JPEG", quality=92, optimize=True)  # a API só aceita JPEG
    return jpg


def desenhar_post(p: dict, pasta: Path | None = None, estilos: list[str] | None = None) -> dict:
    """Carrossel e Story. O carrossel tenta os estilos na ordem dada e fica com o
    primeiro em que o texto cabe; sem estilo (ou se nenhum couber), usa o modelo
    de sempre. Devolve os arquivos e o estilo usado ("estilo": None = modelo de
    sempre); ArteError se nem o modelo de sempre couber."""
    pasta = pasta or P.SAIDA / p["slug"]
    pasta.mkdir(parents=True, exist_ok=True)
    foto = obter_imagem(p, pasta)
    ctx = _contexto(p, foto)
    lista = P.slides(p)
    tentativas = [*(estilos or []), None]
    with Desenhista() as d:
        for estilo in tentativas:
            erros, slides = [], []
            for n, s in enumerate(lista, 1):
                png = pasta / f"{n:02d}.png"
                for e in d.desenhar(png, estilo, s=s, n=n, total=len(lista), **ctx):
                    erros.append(f"slide {n}: {e}")
                slides.append(png)
            if not erros:
                break
            print(f"estilo {estilo or 'padrão'} não coube: {'; '.join(erros)}")
        story = pasta / "story.png"
        for e in d.desenhar(story, s={"kind": "story", **p["capa"]}, n=0, total=0, **ctx):
            erros.append(f"story: {e}")
    if erros:
        raise ArteError("; ".join(erros))
    return {"slides": [_jpeg(s) for s in slides], "story": _jpeg(story), "pngs": slides, "estilo": estilo}


# ---------------------------------------------------------------------------
# Reel
# ---------------------------------------------------------------------------
def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise ArteError("ffmpeg não encontrado") from None


def _tempo_de_leitura(s: dict) -> float:
    texto = " ".join([s.get("titulo", ""), s.get("apoio", "") or "", *(s.get("texto") or []),
                      *(s.get("passos") or []), *[i.get("texto", "") for i in s.get("itens") or []]])
    return round(min(9.0, max(4.0, 2.5 + len(texto) / 28)), 1)


def trilha(destino: Path, segundos: float, taxa: int = 22050) -> None:
    """Trilha 8-bit gerada aqui mesmo (sem direito autoral de terceiros).

    Arpejo em onda de pulso sobre baixo triangular, I-V-vi-IV a 112 bpm, baixinho.
    """
    notas = {"C": 261.63, "G": 196.00, "A": 220.00, "F": 174.61}
    acordes = [("C", [0, 4, 7, 12]), ("G", [0, 4, 7, 12]), ("A", [0, 3, 7, 12]), ("F", [0, 4, 7, 12])]
    batida = 60 / 112 / 2  # colcheia
    total = int(segundos * taxa)
    amostras = bytearray()
    filtro = 0.0
    for i in range(total):
        t = i / taxa
        passo = int(t / batida)
        raiz, intervalos = acordes[(passo // 8) % 4]
        f = notas[raiz] * 2 ** (intervalos[passo % 4] / 12) * 2
        fase = (t * f) % 1
        pulso = 1.0 if fase < 0.25 else -1.0
        env = math.exp(-((t % batida) / batida) * 3)
        fb = notas[raiz] / 2
        tri = 4 * abs((t * fb) % 1 - 0.5) - 1
        v = 0.10 * pulso * env + 0.16 * tri
        filtro += 0.25 * (v - filtro)  # passa-baixa simples: tira o chiado do pulso
        fade = min(1.0, t / 0.5, (segundos - t) / 1.5)
        amostras += struct.pack("<h", int(max(-1, min(1, filtro * fade)) * 32767 * 0.8))
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(bytes(amostras))


def desenhar_reel(p: dict, pngs: list[Path], pasta: Path | None = None) -> dict:
    """Capa do Reel + os slides do carrossel na moldura vertical, com trilha."""
    from PIL import Image

    pasta = pasta or P.SAIDA / p["slug"]
    foto = pasta / "foto.jpg"
    ctx = _contexto(p, foto if foto.exists() else None)
    capa, moldura = pasta / "reel-capa.png", pasta / "reel-moldura.png"
    with Desenhista() as d:
        erros = d.desenhar(capa, s={"kind": "reel-capa", **p["capa"]}, n=0, total=0, **ctx)
        d.desenhar(moldura, s={"kind": "reel-moldura"}, n=0, total=0, **ctx)
    if erros:
        raise ArteError("capa do Reel: " + "; ".join(erros))
    quadros, tempos = [capa], [3.0]
    fundo = Image.open(moldura).convert("RGB")
    for n, (png, s) in enumerate(zip(pngs, P.slides(p)), 1):
        q = fundo.copy()
        q.paste(Image.open(png).convert("RGB"), (0, 285))
        caminho = pasta / f"reel-{n:02d}.png"
        q.save(caminho)
        quadros.append(caminho)
        tempos.append(_tempo_de_leitura(s) if s["kind"] != "final" else 3.5)

    xf = 0.4  # transição entre quadros
    duracao = sum(tempos) - xf * (len(tempos) - 1)
    audio = pasta / "trilha.wav"
    trilha(audio, duracao)
    cmd = [_ffmpeg(), "-y", "-loglevel", "error"]
    for q, t in zip(quadros, tempos):
        cmd += ["-loop", "1", "-t", str(t), "-framerate", "30", "-i", str(q)]
    cmd += ["-i", str(audio)]
    filtros, ant, offset = [], "0:v", 0.0
    for i in range(1, len(quadros)):
        offset += tempos[i - 1] - xf
        saida = f"v{i}"
        filtros.append(f"[{ant}][{i}:v]xfade=transition=fade:duration={xf}:offset={offset:.2f}[{saida}]")
        ant = saida
    filtros.append(f"[{ant}]format=yuv420p,scale=1080:1920[vout]")
    video = pasta / "reel.mp4"
    cmd += ["-filter_complex", ";".join(filtros), "-map", "[vout]", "-map", f"{len(quadros)}:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", "30", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(video)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise ArteError(f"ffmpeg falhou: {r.stderr[-400:]}")
    return {"video": video, "capa": _jpeg(capa), "segundos": round(duracao, 1)}


def folha(pngs: list[Path], destino: Path, colunas: int = 4) -> Path:
    """Folha de contato com os slides, para conferir o carrossel de uma vez."""
    from PIL import Image
    w, h = 270, 338
    linhas = math.ceil(len(pngs) / colunas)
    out = Image.new("RGB", (colunas * w + (colunas + 1) * 12, linhas * h + (linhas + 1) * 12), "#444444")
    for i, png in enumerate(pngs):
        im = Image.open(png).convert("RGB").resize((w, h))
        out.paste(im, (12 + (i % colunas) * (w + 12), 12 + (i // colunas) * (h + 12)))
    out.save(destino)
    return destino


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--reel", action="store_true", help="também gera o Reel")
    ap.add_argument("--estilo", help="um dos estilos de templates/social/estilos/ (padrão: o modelo de sempre)")
    args = ap.parse_args(argv)
    p = P.carregar(args.slug)
    erros = P.conferir(p, str(P.caminho(args.slug)))
    if erros:
        print("\n".join(f"ERRO: {e}" for e in erros))
        return 1
    try:
        out = desenhar_post(p, estilos=[args.estilo] if args.estilo else None)
        print(f"folha: {folha(out['pngs'], P.SAIDA / args.slug / 'folha.png')}")
        if args.reel:
            r = desenhar_reel(p, out["pngs"])
            print(f"reel: {r['video']} ({r['segundos']}s)")
    except ArteError as e:
        print(f"ERRO: {e}")
        return 1
    print(f"ok: {len(out['slides'])} slides e story em {P.SAIDA / args.slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
