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

from scripts.longo.narrado import ANTON, CIANO, LOGO, NOITE, OFICIAL, ROSA, fonte

W, H = 1280, 720
AMARELO = (255, 221, 51)
BRANCO = (255, 255, 255)


def img(prefixo: str) -> Image.Image:
    arq = sorted(p for p in OFICIAL.iterdir() if p.name.startswith(prefixo))[0]
    return Image.open(arq).convert("RGB")


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


def texto(im: Image.Image, xy, s: str, tam: int, cor=AMARELO, contorno=12, ancora="la", rot: float = 0) -> None:
    f = fonte(ANTON, tam)
    camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    x, y = xy
    # sombra dura deslocada + contorno grosso (leitura no celular)
    d.text((x + 8, y + 10), s, font=f, fill=(0, 0, 0, 170), anchor=ancora, stroke_width=contorno,
           stroke_fill=(0, 0, 0, 170))
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
def leonida(pasta: Path) -> None:
    # A: mapa + cidade real do jogo, "É A FLÓRIDA"
    m = mapa_florida()
    im = Image.new("RGBA", (W, H), NOITE)
    cid = realce(cobrir(img("Vice_City_27"), W, H, .5, .5)).convert("RGBA")
    im.alpha_composite(cid)
    degrade(im, "dir", 900, 240)
    mp = m.crop((400, 0, 1740, 1000)).resize((965, 720), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", mp.size, 0)
    ImageDraw.Draw(mask).rectangle([60, 0, mp.width, mp.height], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(40))
    im.paste(mp, (W - mp.width, 0), mask)
    texto(im, (40, 60), "O MAPA", 130, BRANCO)
    texto(im, (40, 200), "É A", 130, AMARELO)
    texto(im, (40, 340), "FLÓRIDA", 130, ROSA)
    pilula(im, (44, 560), "6 REGIÕES", 52, CIANO, NOITE)
    borda(im)
    logo(im, "dir")
    im.convert("RGB").save(pasta / "leonida-capa-A.jpg", quality=92)

    # B: vista aérea de Vice City com seta: "ISSO É MIAMI"
    im = realce(cobrir(img("Vice_City_15"), W, H, .5, .55)).convert("RGBA")
    degrade(im, "esq", 700, 200)
    texto(im, (40, 70), "ISSO É", 140, BRANCO)
    texto(im, (40, 220), "MIAMI!", 210, AMARELO)
    seta(im, (720, 560), (1000, 430))
    pilula(im, (44, 560), "GTA 6 = VIDA REAL", 50, ROSA)
    borda(im, CIANO)
    logo(im, "dir")
    im.convert("RGB").save(pasta / "leonida-capa-B.jpg", quality=92)

    # C: rosto da Lucia + "6 REGIÕES"
    im = realce(cobrir(img("Grassrivers_07"), W, H, .4, .45)).convert("RGBA")
    degrade(im, "dir", 640, 230)
    texto(im, (W - 40, 90), "6", 330, AMARELO, 16, "ra")
    texto(im, (W - 40, 430), "REGIÕES", 130, BRANCO, 12, "ra")
    pilula(im, (W - 420, 590), "LEONIDA", 48, ROSA)
    borda(im)
    logo(im, "esq")
    im.convert("RGB").save(pasta / "leonida-capa-C.jpg", quality=92)


def h48(pasta: Path) -> None:
    # A: Lucia encarando + "48H" gigante
    im = realce(cobrir(img("Lucia_Caminos_13"), W, H, .35, .45)).convert("RGBA")
    degrade(im, "dir", 700, 235)
    texto(im, (W - 40, 40), "48H", 300, AMARELO, 16, "ra")
    texto(im, (W - 40, 380), "FAÇA ISSO", 110, BRANCO, 12, "ra")
    texto(im, (W - 40, 510), "HOJE", 110, ROSA, 12, "ra")
    borda(im)
    logo(im, "esq")
    im.convert("RGB").save(pasta / "48h-capa-A.jpg", quality=92)

    # B: arte oficial + barra de download
    im = realce(cobrir(img("GTAVI_Pre_Load"), W, H, .6, .4)).convert("RGBA")
    degrade(im, "esq", 760, 235)
    texto(im, (40, 60), "BAIXE", 170, BRANCO)
    texto(im, (40, 240), "AGORA", 170, AMARELO)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([44, 470, 620, 540], radius=18, fill=NOITE, outline=BRANCO, width=5)
    d.rounded_rectangle([56, 482, 470, 528], radius=12, fill=CIANO)
    d.text((490, 478), "73%", font=fonte(ANTON, 52), fill=BRANCO)
    pilula(im, (44, 580), "PRÉ-DOWNLOAD", 46, ROSA)
    borda(im, CIANO)
    logo(im, "dir")
    im.convert("RGB").save(pasta / "48h-capa-B.jpg", quality=92)

    # C: personagem assustado + "SPOILER" (Nova Zelândia joga antes)
    im = realce(cobrir(img("Vice_City_16"), W, H, .55, .4)).convert("RGBA")
    degrade(im, "esq", 700, 225)
    texto(im, (40, 70), "CUIDADO", 150, BRANCO)
    texto(im, (40, 240), "SPOILER!", 170, ROSA)
    pilula(im, (44, 470), "QUARTA, 8H", 64, AMARELO, NOITE)
    borda(im)
    logo(im, "dir")
    im.convert("RGB").save(pasta / "48h-capa-C.jpg", quality=92)


def g5g6(pasta: Path, quadro_gta5: Path) -> None:
    g5 = Image.open(quadro_gta5).convert("RGB")
    g5 = g5.crop((560, 100, 1480, 960))  # Michael no GTA 5, sem legenda e etiquetas

    def dividido(dir_img: Image.Image, nome: str, cima: str, baixo: str, corb=AMARELO) -> None:
        im = Image.new("RGBA", (W, H), NOITE)
        esq = realce(cobrir(g5, 660, H, .5, .45)).convert("RGBA")
        from PIL import ImageEnhance
        esq = ImageEnhance.Color(esq.convert("RGB")).enhance(0.55).convert("RGBA")  # GTA 5 "velho"
        im.alpha_composite(esq, (0, 0))
        dirr = realce(cobrir(dir_img, 660, H, .5, .45)).convert("RGBA")
        mask = Image.new("L", (660, H), 0)
        ImageDraw.Draw(mask).polygon([(60, 0), (660, 0), (660, H), (0, H)], fill=255)
        im.paste(dirr, (620, 0), mask)
        d = ImageDraw.Draw(im)
        d.line([(680, 0), (620, H)], fill=BRANCO, width=14)
        pilula(im, (30, 30), "GTA 5", 54, (90, 90, 110))
        pilula(im, (W - 250, 30), "GTA 6", 54, ROSA)
        texto(im, (W // 2, H // 2 - 30), "VS", 170, AMARELO, 14, "mm")
        texto(im, (W // 2, H - 150), cima, 96, BRANCO, 12, "mm")
        if baixo:
            texto(im, (W // 2, H - 60), baixo, 70, corb, 10, "mm")
        borda(im, CIANO)
        im.convert("RGB").save(pasta / nome, quality=92)

    dividido(img("Jason_Duval_17"), "gta5-vs-gta6-capa-A.jpg", "10 DIFERENÇAS", "")
    dividido(img("Lucia_Caminos_13"), "gta5-vs-gta6-capa-B.jpg", "MUDOU TUDO", "")

    # C: casal de GTA 6 + "3 → 2"
    im = realce(cobrir(img("Jason_and_Lucia_17"), W, H, .5, .45)).convert("RGBA")
    degrade(im, "esq", 640, 235)
    texto(im, (40, 60), "3", 190, AMARELO)
    seta(im, (150, 170), (300, 170), BRANCO, 22)
    texto(im, (330, 60), "2", 190, AMARELO)
    texto(im, (40, 280), "ADEUS", 120, BRANCO)
    texto(im, (40, 410), "TREVOR?", 120, ROSA)
    pilula(im, (44, 590), "GTA 5 vs GTA 6", 46, CIANO, NOITE)
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
