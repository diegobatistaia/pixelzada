"""Capas para o teste do YouTube (Testar e comparar: até 3 capas por vídeo). Diego, 17/11/2026.

Regras usadas (pesquisa de canais grandes): um foco só (rosto ou objeto grande), 2 a 4 palavras
em letra enorme com contorno, contraste alto, cores da identidade Pixelzada Vice, texto que NÃO
repete o título e abre curiosidade. 1280x720 JPG.

    python -m scripts.longo.capas_teste <pasta_saida> [quadro_gta5.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from scripts.longo.narrado import ANTON, CIANO, LOGO, NOITE, ROSA, fonte

W, H = 1280, 720
AMARELO = (255, 221, 51)
BRANCO = (255, 255, 255)


def img(prefixo: str) -> Image.Image:
    from scripts.longo.narrado import oficial
    im = Image.open(oficial(prefixo)).convert("RGB")
    print(f"  {prefixo}: {im.size[0]}x{im.size[1]}")
    return im


def cobrir(im: Image.Image, w: int, h: int, fx: float = 0.5, fy: float = 0.5) -> Image.Image:
    """Redimensiona cobrindo w x h e recorta em torno do ponto (fx, fy)."""
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x = min(max(0, int(im.width * fx - w / 2)), im.width - w)
    y = min(max(0, int(im.height * fy - h / 2)), im.height - h)
    return im.crop((x, y, x + w, y + h))


def realce(im: Image.Image) -> Image.Image:
    from PIL import ImageEnhance
    im = ImageEnhance.Color(im).enhance(1.25)
    return ImageEnhance.Contrast(im).enhance(1.12)


def degrade(im: Image.Image, lado: str = "esq", largura: int = 760, forca: int = 225) -> None:
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    for i in range(largura):
        a = int(forca * (1 - i / largura) ** 1.4)
        x = i if lado == "esq" else W - 1 - i
        d.line([(x, 0), (x, H)], fill=(*NOITE, a))
    im.alpha_composite(g)


def texto(im: Image.Image, xy, s: str, tam: int, cor=AMARELO, contorno=12, ancora="la", rot: float = 0,
          brilho=None) -> None:
    f = fonte(ANTON, tam)
    contorno = int(contorno * 1.35)
    x, y = xy
    # Diego (17/11): brilho neon borrava a leitura. Só contorno escuro grosso + sombra dura.
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    # sombra dura deslocada + contorno grosso (leitura no celular)
    d.text((x + 9, y + 11), s, font=f, fill=(0, 0, 0, 200), anchor=ancora, stroke_width=contorno,
           stroke_fill=(0, 0, 0, 200))
    d.text((x, y), s, font=f, fill=cor, anchor=ancora, stroke_width=contorno, stroke_fill=NOITE)
    if rot:
        camada = camada.rotate(rot, resample=Image.BICUBIC, center=(x, y))
    im.alpha_composite(camada)


def pilula(im: Image.Image, xy, s: str, tam: int = 46, fundo=ROSA, cor=BRANCO) -> None:
    d = ImageDraw.Draw(im)
    f = fonte(ANTON, tam)
    x, y = xy
    tl = f.getlength(s)
    d.rounded_rectangle([x, y, x + tl + 40, y + tam + 24], radius=14, fill=fundo, outline=NOITE, width=5)
    d.text((x + 20, y + 8), s, font=f, fill=cor)


def selo(im: Image.Image, xy, tam: int = 84, ancora: str = "esq", s: str = "GTA 6", fundo=ROSA) -> None:
    """Selo grande "GTA 6" em todas as capas (pedido do Diego, 17/11)."""
    f = fonte(ANTON, tam)
    tl = f.getlength(s)
    w, h = int(tl + 56), tam + 36
    x, y = xy
    if ancora == "dir":
        x -= w
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(g).rounded_rectangle([x - 6, y - 6, x + w + 6, y + h + 6], radius=22, fill=(*fundo, 255))
    im.alpha_composite(g.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([x + 6, y + 10, x + w + 6, y + h + 10], radius=20, fill=(0, 0, 0))
    d.rounded_rectangle([x, y, x + w, y + h], radius=20, fill=fundo, outline=BRANCO, width=7)
    d.text((x + 28, y + 10), s, font=f, fill=BRANCO, stroke_width=4, stroke_fill=NOITE)


def logo(im: Image.Image, canto: str = "dir") -> None:
    l = Image.open(LOGO).convert("RGBA")
    l = l.resize((int(l.width * 40 / l.height), 40), Image.LANCZOS)
    fundo = Image.new("RGBA", (l.width + 28, 58), (*NOITE, 200))
    x = W - fundo.width - 24 if canto == "dir" else 24
    im.alpha_composite(fundo, (x, H - 82))
    im.alpha_composite(l, (x + 14, H - 73))


def borda(im: Image.Image, cor=ROSA, larg: int = 10) -> None:
    ImageDraw.Draw(im).rectangle([0, 0, W - 1, H - 1], outline=cor, width=larg)


def seta(im: Image.Image, de, para, cor=AMARELO, larg: int = 18) -> None:
    import math
    d = ImageDraw.Draw(im)
    d.line([de, para], fill=NOITE, width=larg + 12)
    d.line([de, para], fill=cor, width=larg)
    ang = math.atan2(para[1] - de[1], para[0] - de[0])
    pts = [para]
    for da in (2.6, -2.6):
        pts.append((para[0] + 60 * math.cos(ang + da), para[1] + 60 * math.sin(ang + da)))
    d.polygon(pts, fill=cor, outline=NOITE)


def mapa_florida(alt: int = 640) -> Image.Image:
    """Mapa da Flórida no estilo do vídeo (motion.mapa_anim), quadro final com todas as regiões."""
    from scripts.longo import motion as M
    import subprocess
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    M.mapa_anim(tmp / "m.mp4", 1.0, "todas", anterior=None, entrada=False)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.05", "-i", str(tmp / "m.mp4"),
                    "-frames:v", "1", str(tmp / "m.png")], check=True)
    return Image.open(tmp / "m.png").convert("RGB")


# ---------------------------------------------------------------------------
# REGRA (Diego, 17/11): TODA capa tem Jason e Lucia (os protagonistas) + selo "GTA 6" grande,
# para quem rola o feed saber na hora que é GTA 6. Rosto nunca cortado nem coberto por texto.
JL_TRAILER = "GTAVI_Launch_Trailer_poster"   # Jason ~0.35, Lucia ~0.62 (pôr do sol, carro vermelho)
JL_TELHADO = "Jason_Lucia_Rooftop_landscape"  # Jason ~0.55, Lucia ~0.72, Vice City ao fundo
JL_POSTO = "GTAVI_An_Extended_Look_poster"   # Lucia ~0.38, Jason ~0.55 andando
JL_CARRO = "Jason_and_Lucia_17"              # Lucia ~0.4, Jason ~0.65 saindo do carro
JL_ARMAS = "Jason_Lucia_Lock_And_Load_landscape"  # Jason ~0.2, Lucia ~0.43
JL_ASSALTO = "Jason_and_Lucia_15"            # Jason ~0.55 de máscara, Lucia ~0.65


def fundo(prefixo: str, fx: float = .5, fy: float = .5, zoom: float = 1.0) -> Image.Image:
    im = img(prefixo)
    s = max(W / im.width, H / im.height) * zoom
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    return realce(cobrir(im, W, H, fx, fy)).convert("RGBA")


def leonida(pasta: Path) -> None:
    # A: painel do mapa da Flórida (com o texto) à esquerda + Jason e Lucia à direita
    im = Image.new("RGBA", (W, H), NOITE)
    m = mapa_florida()
    mp = m.crop((560, 0, 1720, 1000)).resize((696, 600), Image.LANCZOS).convert("RGBA")
    im.alpha_composite(mp, (-30, 110))
    jl = img(JL_TRAILER)
    sc = max(680 / jl.width, H / jl.height) * 1.25
    jl = jl.resize((round(jl.width * sc), round(jl.height * sc)), Image.LANCZOS)
    dirr = realce(cobrir(jl, 700, H, .50, .45)).convert("RGBA")
    mask = Image.new("L", (700, H), 0)
    ImageDraw.Draw(mask).polygon([(70, 0), (700, 0), (700, H), (0, H)], fill=255)
    im.paste(dirr, (580, 0), mask)
    ImageDraw.Draw(im).line([(650, 0), (580, H)], fill=ROSA, width=12)
    texto(im, (48, 50), "O MAPA", 116, BRANCO)
    texto(im, (48, 180), "É A", 116, AMARELO)
    texto(im, (48, 310), "FLÓRIDA", 116, ROSA)
    selo(im, (40, 580), 70)
    borda(im)
    logo(im, "dir")
    im.convert("RGB").save(pasta / "leonida-capa-A.jpg", quality=92)

    # B: Jason e Lucia no telhado com Vice City atrás: "ISSO É MIAMI!"
    im = fundo(JL_TELHADO, .62, .45, 1.1)
    degrade(im, "esq", 760, 235)
    texto(im, (36, 50), "ISSO É", 140, BRANCO)
    texto(im, (36, 200), "MIAMI!", 200, AMARELO)
    selo(im, (40, 560), 66, s="GTA 6 = VIDA REAL")
    borda(im, CIANO)
    logo(im, "dir")
    im.convert("RGB").save(pasta / "leonida-capa-B.jpg", quality=92)

    # C: Jason e Lucia andando + "6 REGIÕES"
    im = fundo(JL_POSTO, .40, .45, 1.15)
    degrade(im, "dir", 640, 235)
    texto(im, (W - 36, 30), "6", 320, AMARELO, 16, "ra")
    texto(im, (W - 36, 365), "REGIÕES", 130, BRANCO, 12, "ra")
    selo(im, (W - 40, 575), 70, "dir")
    borda(im)
    logo(im, "esq")
    im.convert("RGB").save(pasta / "leonida-capa-C.jpg", quality=92)


def h48(pasta: Path) -> None:
    # A: Jason e Lucia no telhado + "48H"
    im = fundo(JL_TELHADO, .62, .45, 1.1)
    degrade(im, "esq", 700, 240)
    selo(im, (36, 26), 62)
    texto(im, (36, 120), "48H", 260, AMARELO, 16)
    texto(im, (36, 420), "FAÇA ISSO", 100, BRANCO, 12)
    texto(im, (36, 545), "HOJE", 104, ROSA, 12)
    borda(im)
    logo(im, "dir")
    im.convert("RGB").save(pasta / "48h-capa-A.jpg", quality=92)

    # B: Jason e Lucia armados + barra de download
    im = fundo(JL_ARMAS, .30, .45, 1.1)
    degrade(im, "dir", 700, 240)
    texto(im, (W - 36, 40), "BAIXE", 160, BRANCO, 12, "ra")
    texto(im, (W - 36, 215), "AGORA", 160, AMARELO, 12, "ra")
    d = ImageDraw.Draw(im)
    x0 = W - 620
    d.rounded_rectangle([x0, 455, W - 44, 525], radius=18, fill=NOITE, outline=BRANCO, width=5)
    d.rounded_rectangle([x0 + 12, 467, x0 + 420, 513], radius=12, fill=CIANO)
    d.text((x0 + 440, 463), "73%", font=fonte(ANTON, 52), fill=BRANCO)
    selo(im, (W - 40, 572), 66, "dir", s="GTA 6 PRÉ-DOWNLOAD")
    borda(im, CIANO)
    logo(im, "esq")
    im.convert("RGB").save(pasta / "48h-capa-B.jpg", quality=92)

    # C: Jason e Lucia saindo do carro + "CUIDADO: SPOILER!" embaixo (rostos livres em cima)
    im = fundo(JL_CARRO, .5, .35, 1.0)
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dg = ImageDraw.Draw(g)
    for i in range(300):
        dg.line([(0, H - i), (W, H - i)], fill=(*NOITE, int(235 * (1 - i / 300) ** 1.2)))
    im.alpha_composite(g)
    texto(im, (W // 2, H - 95), "CUIDADO: SPOILER!", 150, ROSA, 12, "mm")
    pilula(im, (36, 30), "QUARTA, 8H", 60, AMARELO, NOITE)
    selo(im, (W - 36, 26), 70, "dir")
    borda(im)
    im.convert("RGB").save(pasta / "48h-capa-C.jpg", quality=92)


def g5g6(pasta: Path, quadro_gta5: Path) -> None:
    # arte oficial do GTA 5 (Steam): Michael e Trevor de frente (Diego: personagem tem que ser conhecido)
    g5 = Image.open(quadro_gta5).convert("RGB")
    if g5.size == (1920, 620):
        g5 = g5.crop((1080, 0, 1700, 620))

    def dividido(prefixo: str, nome: str, cima: str, fx: float, zoom: float) -> None:
        im = Image.new("RGBA", (W, H), NOITE)
        from PIL import ImageEnhance
        esq = realce(cobrir(g5, 660, H, .5, .45)).convert("RGBA")
        im.alpha_composite(esq, (0, 0))
        dj = img(prefixo)
        sc = max(660 / dj.width, H / dj.height) * zoom
        dj = dj.resize((round(dj.width * sc), round(dj.height * sc)), Image.LANCZOS)
        dirr = realce(cobrir(dj, 680, H, fx, .45)).convert("RGBA")  # Jason e Lucia inteiros no painel
        mask = Image.new("L", (680, H), 0)
        ImageDraw.Draw(mask).polygon([(60, 0), (680, 0), (680, H), (0, H)], fill=255)
        im.paste(dirr, (600, 0), mask)
        d = ImageDraw.Draw(im)
        d.line([(660, 0), (600, H)], fill=BRANCO, width=14)
        selo(im, (28, 26), 84, s="GTA 5", fundo=(70, 120, 70))
        selo(im, (W - 28, 26), 84, "dir")
        texto(im, (W // 2 - 20, H // 2 - 40), "VS", 190, AMARELO, 14, "mm")
        texto(im, (W // 2, H - 95), cima, 112, BRANCO, 12, "mm")
        borda(im, CIANO)
        im.convert("RGB").save(pasta / nome, quality=92)

    dividido(JL_TRAILER, "gta5-vs-gta6-capa-A.jpg", "10 DIFERENÇAS", .45, 1.25)
    dividido(JL_TELHADO, "gta5-vs-gta6-capa-B.jpg", "MUDOU TUDO", .66, 1.0)

    # C: Jason e Lucia + "3 → 2"
    im = fundo(JL_POSTO, .45, .45, 1.15)
    degrade(im, "esq", 640, 240)
    texto(im, (36, 40), "3", 190, AMARELO)
    seta(im, (150, 150), (300, 150), BRANCO, 22)
    texto(im, (330, 40), "2", 190, AMARELO)
    texto(im, (36, 260), "ADEUS", 120, BRANCO)
    texto(im, (36, 390), "TREVOR?", 120, ROSA)
    selo(im, (40, 572), 66, s="GTA 5 vs GTA 6")
    borda(im)
    logo(im, "dir")
    im.convert("RGB").save(pasta / "gta5-vs-gta6-capa-C.jpg", quality=92)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    leonida(out)
    h48(out)
    if len(sys.argv) > 2:
        g5g6(out, Path(sys.argv[2]))
