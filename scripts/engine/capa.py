"""Capa própria da Pixelzada: arte em pixel art gerada, sem banco de imagens.

Cada matéria ganha uma cena (céu em degradê, sol, skyline com janelas acesas e
estrelas) nas cores da categoria. A cena é sorteada a partir do slug, então a
mesma matéria sempre gera a mesma capa. Não usa foto, trailer nem print de
terceiros: não há licença nem crédito a cumprir.
"""
from __future__ import annotations

import random

from PIL import Image, ImageDraw, ImageFont

from .config import ROOT, Config
from .util import fingerprint

IMG_DIR = ROOT / "assets" / "img"
FONT = ROOT / "assets" / "fonts" / "Silkscreen-Regular.ttf"
W, H, SCALE = 1200, 675, 8
GW, GH = W // SCALE, -(-H // SCALE)          # grade de 150 x 85 "pixels"

NOITE = (11, 10, 16)
PREDIO = (22, 17, 42)
LIMA = (198, 255, 26)

# topo do céu, meio, horizonte
PALETAS = {
    "gta-6": ((46, 31, 110), (190, 60, 125), (255, 150, 60)),
    "lancamentos": ((40, 20, 90), (255, 61, 139), (255, 170, 80)),
    "guias": ((12, 30, 80), (30, 120, 200), (46, 230, 255)),
    "consoles": ((50, 20, 60), (210, 70, 60), (255, 138, 31)),
    "industria": ((20, 18, 40), (70, 60, 120), (167, 163, 181)),
}
PADRAO = PALETAS["industria"]


def _hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _cena(slug: str, paleta) -> Image.Image:
    rng = random.Random(slug)
    horizonte = int(GH * 0.78)
    img = Image.new("RGB", (GW, GH), NOITE)
    px = img.load()
    topo, meio, base = paleta
    for y in range(GH):
        t = min(y / horizonte, 1.0)
        cor = _mix(topo, meio, t * 2) if t < 0.5 else _mix(meio, base, (t - 0.5) * 2)
        faixa = 3 if y % 6 < 3 else 0          # degradê em degraus, estilo 16 bits
        cor = _mix(cor, NOITE, 0.06 * faixa / 3)
        for x in range(GW):
            px[x, y] = cor
    d = ImageDraw.Draw(img)

    for _ in range(26):                          # estrelas só no alto do céu
        x, y = rng.randrange(GW), rng.randrange(int(GH * 0.38))
        d.point((x, y), fill=(255, 255, 255))

    raio = rng.randint(11, 16)                   # sol
    cx = rng.randint(int(GW * 0.25), int(GW * 0.75))
    cy = horizonte - rng.randint(2, 8)
    sol = _mix((255, 232, 160), base, 0.15)
    for y in range(cy - raio, cy + raio + 1):
        for x in range(cx - raio, cx + raio + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= raio ** 2 and y < horizonte:
                px[x, y] = sol

    x = 0                                        # skyline
    while x < GW:
        largura = rng.randint(6, 14)
        altura = rng.randint(14, 44)
        topo_y = horizonte - altura
        d.rectangle([x, topo_y, x + largura - 1, GH], fill=PREDIO)
        for wy in range(topo_y + 3, horizonte - 2, 4):
            for wx in range(x + 2, x + largura - 2, 3):
                if rng.random() < 0.22:
                    d.point((wx, wy), fill=LIMA if rng.random() < 0.7 else (255, 61, 139))
        x += largura + rng.randint(0, 2)
    d.rectangle([0, horizonte, GW, GH], fill=PREDIO)
    return img


def gerar(post: dict, cfg: Config) -> dict:
    """Gera a capa, grava em assets/img e devolve o dict `image` da matéria."""
    slug = post["slug"]
    categorias = {c["slug"]["pt"] if isinstance(c["slug"], dict) else c["slug"]: c
                  for c in cfg.get("editorial.categories", [])}
    cat = categorias.get(post.get("category"), {})
    label = cat.get("label", {}).get("pt", post.get("category", "")) if cat else ""
    cor = _hex(cat["color"]) if cat.get("color") else LIMA
    paleta = PALETAS.get(post.get("category"), PADRAO)

    img = _cena(slug, paleta).resize((GW * SCALE, GH * SCALE), Image.NEAREST).crop((0, 0, W, H))
    d = ImageDraw.Draw(img)
    fonte = ImageFont.truetype(str(FONT), 30)
    texto = label.upper()
    largura = d.textlength(texto, font=fonte)
    d.rectangle([0, H - 72, int(largura) + 80, H], fill=cor)
    d.text((40, H - 54), texto, font=fonte, fill=NOITE)
    marca = ImageFont.truetype(str(FONT), 22)
    d.text((W - 40 - d.textlength("PIXELZADA", font=marca), H - 50), "PIXELZADA",
           font=marca, fill=(255, 255, 255))

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    nome = f"{slug[:40]}-{fingerprint(slug)[:8]}.jpg"
    img.save(IMG_DIR / nome, "JPEG", quality=88, optimize=True, progressive=True)
    return {
        **post.get("image", {}),
        "path": f"/assets/img/{nome}",
        "alt": f"Arte em pixel art da Pixelzada, no tema {label or 'games'}, para a matéria: {post['title']}",
        "credit": "Arte: Pixelzada",
    }
