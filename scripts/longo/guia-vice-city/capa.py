"""Capas do Guia Vice City (1280x720): Leo grande à direita (recortado), arte oficial de Jason e Lucia
ao fundo, 1-2 palavras gigantes em amarelo com contorno preto grosso e sombra (sem neon).

    python -m scripts.longo.guia-vice-city.capa  (rodado pelo workflow capa-gvc.yml)
Saída: previas/longo/guia-vice-city/<slug>-capa-<X>.jpg
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

RAIZ = Path(__file__).resolve().parents[3]
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
from scripts.longo import narrado as N  # noqa: E402

ANTON = str(RAIZ / "scripts/social/gerador/fonts/f1.ttf")
AMARELO = (255, 214, 0)
SAIDA = RAIZ / "previas/longo/guia-vice-city"


def leo_recortado() -> Image.Image:
    from rembg import remove
    cache = AQUI / "leo-recorte.png"
    if cache.exists():
        return Image.open(cache).convert("RGBA")
    im = remove(Image.open(AQUI / "leo.png").convert("RGB"))
    im = im.crop(im.getbbox())
    im.save(cache)
    return im


def fundo(prefixo: str) -> Image.Image:
    im = Image.open(N.oficial(prefixo)).convert("RGB")
    esc = max(1280 / im.width, 720 / im.height)
    im = im.resize((int(im.width * esc) + 1, int(im.height * esc) + 1), Image.LANCZOS)
    x = (im.width - 1280) // 2
    im = im.crop((x, 0, x + 1280, 720))
    im = ImageEnhance.Brightness(im).enhance(0.8)
    return ImageEnhance.Color(im).enhance(1.25)


def texto(im: Image.Image, linha: str, tam: int, y: int, cor=AMARELO, x=None, borda=14) -> None:
    f = ImageFont.truetype(ANTON, tam)
    while f.getlength(linha) > 1220 and tam > 60:
        tam -= 6
        f = ImageFont.truetype(ANTON, tam)
    w = f.getlength(linha)
    x = int((1280 - w) / 2) if x is None else x
    sombra = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).text((x + 12, y + 14), linha, font=f, fill=(0, 0, 0, 200), stroke_width=borda, stroke_fill=(0, 0, 0, 200))
    im.alpha_composite(sombra.filter(ImageFilter.GaussianBlur(8)))
    ImageDraw.Draw(im).text((x, y), linha, font=f, fill=cor, stroke_width=borda, stroke_fill=(0, 0, 0))


def selo(im: Image.Image) -> None:
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(ANTON, 64)
    d.rounded_rectangle([30, 26, 30 + f.getlength("GTA 6") + 44, 26 + 92], radius=16, fill=(255, 61, 139), outline=(0, 0, 0), width=6)
    d.text((52, 30), "GTA 6", font=f, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))


def capa(fundo_pref: str, palavra: str, saida: Path, leo_alt: int = 700, leo_x: int = 640) -> None:
    im = fundo(fundo_pref).convert("RGBA")
    # escurece a base para o texto
    g = Image.new("RGBA", im.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(g)
    for y in range(360, 720):
        gd.line([(0, y), (1280, y)], fill=(10, 4, 24, int(200 * ((y - 360) / 360) ** 1.4)))
    im.alpha_composite(g)
    leo = leo_recortado()
    leo = leo.resize((int(leo.width * leo_alt / leo.height), leo_alt), Image.LANCZOS)
    # contorno branco em volta do Leo (destaca do fundo)
    a = leo.split()[3].filter(ImageFilter.MaxFilter(15))
    contorno = Image.new("RGBA", leo.size, (255, 255, 255, 255))
    contorno.putalpha(a)
    y = 720 - leo.height + 40
    im.alpha_composite(contorno, (leo_x, y))
    im.alpha_composite(leo, (leo_x, y))
    selo(im)
    texto(im, palavra, 190, 470)
    im.convert("RGB").save(saida, quality=92)
    print("capa:", saida)


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((AQUI / "capas.json").read_text(encoding="utf-8"))
    for c in cfg:
        capa(c["fundo"], c["palavra"], SAIDA / c["arquivo"], c.get("leo_alt", 700), c.get("leo_x", 640))
    return 0


if __name__ == "__main__":
    sys.exit(main())
