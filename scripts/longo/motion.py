"""Motion graphics da identidade "Pixelzada Vice" (16/11/2026, pedido do Diego):

- intro_logo: entrada animada do logo Pixelzada (vinheta reaproveitável em todos os vídeos);
- mapa_anim: mapa de Leonida animado SEM zoom: contorno desenhando, pinos surgindo um a um,
  rota tracejada da região anterior até a atual, anel pulsando e etiqueta deslizando.

Os quadros são desenhados no Pillow e mandados crus para o ffmpeg.
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H, FPS = 1920, 1080, 30


def _ffmpeg(saida: Path, n: int):
    return subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-frames:v", str(n), "-c:v", "libx264",
                             "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", str(saida)],
                            stdin=subprocess.PIPE)


def ease_out(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def ease_back(t: float) -> float:
    t = min(1.0, max(0.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# ---------------------------------------------------------------------------
def intro_logo(saida: Path, dur: float = 3.2, apoio: str = "") -> None:
    from scripts.longo import narrado as N
    n = max(1, int(round(dur * FPS)))
    fundo = N.fundo_vice().convert("RGB")
    escuro = Image.new("RGB", (W, H), N.NOITE)
    logo = Image.open(N.LOGO).convert("RGBA")
    base_w = 1100
    logo = logo.resize((base_w, int(logo.height * base_w / logo.width)), Image.LANCZOS)
    brilho = logo.copy()
    r, g, b, a = brilho.split()
    rosa = Image.new("RGBA", logo.size, N.ROSA + (0,))
    rosa.putalpha(a)
    brilho = rosa.filter(ImageFilter.GaussianBlur(28))
    # canais separados para o efeito de "glitch" RGB na entrada
    ciano = Image.new("RGBA", logo.size, N.CIANO + (0,))
    ciano.putalpha(a.point(lambda v: v * 0.8))
    mag = Image.new("RGBA", logo.size, N.ROSA + (0,))
    mag.putalpha(a.point(lambda v: v * 0.8))
    fa = N.fonte(N.ARCHIVO, 46)
    proc = _ffmpeg(saida, n)
    for i in range(n):
        t = i / FPS
        # fundo: escuro -> pôr do sol (0 a 0,6 s); no fim volta a escurecer (corte para o vídeo)
        k = ease_out(t / 0.6)
        quadro = Image.blend(escuro, fundo, k * 0.85)
        if t > dur - 0.35:
            quadro = Image.blend(quadro, escuro, (t - (dur - 0.35)) / 0.35)
        quadro = quadro.convert("RGBA")
        # faixas de varredura (scanlines) passando
        d = ImageDraw.Draw(quadro, "RGBA")
        off = int(t * 240) % 8
        for y in range(off, H, 8):
            d.line([(0, y), (W, y)], fill=(0, 0, 0, 28))
        # logo: entra com escala "back" (0,25 s a 0,95 s)
        e = ease_back((t - 0.25) / 0.7)
        if t >= 0.25:
            esc = 0.55 + 0.45 * e
            lw, lh = max(2, int(logo.width * esc)), max(2, int(logo.height * esc))
            cx, cy = W // 2, int(H * 0.44)
            pos = (cx - lw // 2, cy - lh // 2)
            glitch = max(0.0, 1 - (t - 0.25) / 0.6)
            if glitch > 0:
                dx = int(26 * glitch * math.sin(t * 70))
                quadro.alpha_composite(ciano.resize((lw, lh)), (pos[0] - dx, pos[1]))
                quadro.alpha_composite(mag.resize((lw, lh)), (pos[0] + dx, pos[1] + 3))
            pulso = 0.55 + 0.45 * math.sin(max(0, t - 0.9) * 5)
            bl = brilho.resize((lw, lh))
            bl.putalpha(bl.getchannel("A").point(lambda v, p=pulso: int(v * p)))
            quadro.alpha_composite(bl, pos)
            quadro.alpha_composite(logo.resize((lw, lh), Image.LANCZOS), pos)
            # flash branco no impacto
            if 0.55 < t < 0.75:
                fl = Image.new("RGBA", (W, H), (255, 255, 255, int(120 * (1 - (t - 0.55) / 0.2))))
                quadro.alpha_composite(fl)
        # linha neon que corre por baixo + texto de apoio digitando
        if t > 0.9:
            p = ease_out((t - 0.9) / 0.5)
            y = int(H * 0.44) + 150
            d = ImageDraw.Draw(quadro, "RGBA")
            meio = W // 2
            d.line([(meio - 420 * p, y), (meio + 420 * p, y)], fill=N.CIANO + (255,), width=5)
            if apoio:
                nchar = int(len(apoio) * min(1, (t - 1.1) / 0.8)) if t > 1.1 else 0
                txt = apoio[:nchar]
                d.text(((W - fa.getlength(apoio)) / 2, y + 26), txt, font=fa, fill=(255, 255, 255, 235))
        proc.stdin.write(quadro.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()


# ---------------------------------------------------------------------------
_BASE: dict = {}


def _base_mapa():
    """Mapa sem rótulos (fundo, contorno com brilho, ilhas) e as posições das regiões."""
    if _BASE:
        return _BASE
    from scripts.longo import narrado as N
    im = N.degrade(W, H, [(12, 4, 28), (34, 10, 66), (20, 6, 42)])
    d = ImageDraw.Draw(im, "RGBA")
    for x in range(0, W, 60):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 10))
    for y in range(0, H, 60):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 10))
    im = im.convert("RGBA")
    caixa = (560, 40, 136)
    polis = [[N.projetar(lo, la, caixa) for lo, la in p] for p in N.contorno_florida()]
    polis = [p for p in polis if len(p) >= 3]
    preench = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd = ImageDraw.Draw(preench)
    for p in polis:
        pd.polygon(p, fill=(74, 20, 140, 255))
    contorno = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(contorno)
    for p in polis:
        cd.line(p + [p[0]], fill=(255, 61, 139, 255), width=10)
    brilho = contorno.filter(ImageFilter.GaussianBlur(14))
    fino = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fd = ImageDraw.Draw(fino)
    for p in polis:
        fd.line(p + [p[0]], fill=(255, 61, 139, 255), width=4)
    for i in range(14):
        lo, la = -80.35 - i * 0.11, 25.15 - (i ** 1.25) * 0.032
        x, y = N.projetar(lo, la, caixa)
        fd.ellipse([x - 5, y - 3, x + 5, y + 3], fill=(255, 61, 139, 230))
    fp = N.fonte(N.PIXEL, 20)
    for txt, lo, la in [("GOLFO DO MÉXICO", -86.6, 27.4), ("OCEANO ATLÂNTICO", -79.9, 29.6)]:
        x, y = N.projetar(lo, la, caixa)
        fd.text((x, y), txt, font=fp, fill=(255, 255, 255, 70))
    fd.text((60, 40), "FLÓRIDA REAL · REGIÕES DE LEONIDA EM POSIÇÃO APROXIMADA", font=N.fonte(N.PIXEL, 18),
            fill=(255, 255, 255, 110))
    pos = {k: N.projetar(lo, la, caixa) for k, (_, lo, la, _) in N.REGIOES.items()}
    # máscara de "desenho" do contorno: revela da esquerda para a direita e de cima para baixo
    _BASE.update(fundo=im, preench=preench, brilho=brilho, fino=fino, pos=pos)
    return _BASE


def _rotulo(d, N, chave, x, y, ativo, alpha, desliza=0.0):
    nome, _, _, real = N.REGIOES[chave]
    fl = N.fonte(N.ANTON, 36 if ativo else 30)
    tl = fl.getlength(nome)
    if chave == "grassrivers":
        lx, ly = x - 30 - tl - 24, y
    elif chave == "gellhorn":
        lx, ly = x - tl / 2 - 12, y + 36
    elif chave == "keys":
        lx, ly = x - tl - 50, y - 40
    else:
        lx, ly = x + 28, y
    lx += desliza
    a = int(255 * alpha)
    fundo = (255, 61, 139, a) if ativo else (18, 6, 36, int(a * .85))
    d.rounded_rectangle([lx, ly - 25, lx + tl + 24, ly + 25], radius=8, fill=fundo,
                        outline=None if ativo else (46, 230, 214, a), width=2)
    d.text((lx + 12, ly - 24), nome, font=fl, fill=(255, 255, 255, a))
    if ativo:
        d.text((lx + 12, ly + 32), f"VIDA REAL: {real.upper()}", font=N.fonte(N.PIXEL, 20), fill=(46, 230, 214, a))


def mapa_anim(saida: Path, dur: float, destaque: str | None, anterior: str | None = None,
              entrada: bool = False) -> None:
    """entrada=True: contorno se desenha e os pinos surgem um a um (primeira vez que o mapa aparece)."""
    from scripts.longo import narrado as N
    B = _base_mapa()
    n = max(1, int(round(dur * FPS)))
    ordem = list(N.REGIOES)
    proc = _ffmpeg(saida, n)
    for i in range(n):
        t = i / FPS
        q = B["fundo"].copy()
        if entrada:
            rev = ease_out(t / 1.2)
            mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(mask).rectangle([0, 0, int(W * rev), H], fill=255)
            for camada in ("preench", "brilho", "fino"):
                c = B[camada].copy()
                c.putalpha(Image.composite(c.getchannel("A"), Image.new("L", (W, H), 0), mask))
                q.alpha_composite(c)
        else:
            for camada in ("preench", "brilho", "fino"):
                q.alpha_composite(B[camada])
        d = ImageDraw.Draw(q, "RGBA")
        # rota tracejada da região anterior até a atual
        if anterior and destaque and anterior != destaque:
            (x0, y0), (x1, y1) = B["pos"][anterior], B["pos"][destaque]
            p = ease_out(t / 0.9)
            passos = 40
            for k in range(int(passos * p)):
                if k % 2:
                    continue
                a0, a1 = k / passos, (k + 1) / passos
                curva = lambda s: (x0 + (x1 - x0) * s, y0 + (y1 - y0) * s - math.sin(math.pi * s) * 60)  # noqa: E731
                d.line([curva(a0), curva(a1)], fill=(255, 214, 120, 230), width=5)
        for j, chave in enumerate(ordem):
            x, y = B["pos"][chave]
            ativo = chave == destaque
            atraso = (0.9 + j * 0.25) if entrada else 0.0
            if ativo and anterior:
                atraso = 0.6
            vis = ease_out((t - atraso) / 0.35)
            if vis <= 0:
                continue
            if ativo:
                fase = (t * 1.6) % 1
                for r0 in (0, 0.5):
                    f = (fase + r0) % 1
                    rr = 14 + 70 * f
                    d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=(255, 61, 139, int(220 * (1 - f))), width=4)
                d.ellipse([x - 13, y - 13, x + 13, y + 13], fill=(255, 255, 255, int(255 * vis)))
                _rotulo(d, N, chave, x, y, True, vis, desliza=-40 * (1 - vis))
            else:
                apagado = 0.45 if destaque else 1.0
                rr = 9 * ease_back((t - atraso) / 0.35)
                d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(46, 230, 214, int(210 * apagado * vis)))
                _rotulo(d, N, chave, x, y, False, vis * apagado)
        proc.stdin.write(q.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()
