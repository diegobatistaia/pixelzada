"""Vídeo "Despedida de Los Santos": trajeto em motion no mapa de satélite do GTA V (1080x1920).

    python3 scripts/mapa/render.py <mapa_master.jpg> <pasta_voz> <saida.mp4> [--ate SEG] [--quadro SEG --png x.png]

O mapa é o de satélite do próprio jogo (ladrilhos z6 costurados, recorte 7400x10800 = miniatura x6).
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import rota as R  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
RAIZ = Path(__file__).resolve().parents[2]
FONTES = RAIZ / "scripts/social/gerador/fonts"
ANTON, ARCHIVO, PIXEL = str(FONTES / "f1.ttf"), str(FONTES / "f2.ttf"), str(FONTES / "f5.ttf")
LOGO = Path("/mnt/project-files/identidade/logo/pixelzada-logo-transparente.png")
if not LOGO.exists():
    LOGO = RAIZ / "scripts/mapa/logo.png"

W, H, FPS = 1080, 1920, 30
K = 1.18  # miniatura -> tela
NOITE, CARVAO, LIMA, CIANO, ROSA, BRANCO, CINZA = (11, 10, 16), (23, 21, 31), (198, 255, 26), (46, 230, 255), (255, 61, 139), (255, 255, 255), (167, 163, 181)
GAP, INICIO = 0.22, 0.35
PAD = 400

_F = {}


def fonte(c, t):
    if (c, t) not in _F:
        _F[(c, t)] = ImageFont.truetype(c, t)
    return _F[(c, t)]


def ease(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def ease_out(t):
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


def ease_back(t):
    t = min(1.0, max(0.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# ---------------------------------------------------------------------------
ROT = json.loads((Path(__file__).parent / "roteiro.json").read_text(encoding="utf-8"))
TXT = {s["id"].split("-", 1)[1]: s["texto"] for s in ROT["segmentos"]}
ORDEM = [s["id"] for s in ROT["segmentos"]]

TITULOS = {
    "abertura": (None, "TRAJETO DA DESPEDIDA", "Um último rolê por Los Santos"),
    "grove": ("01", "GROVE STREET", "Ponto de encontro · 14h30 no jogo"),
    "rodovia": ("02", "RODOVIA PARA O NORTE", "Liga sua rádio favorita"),
    "sandy": ("03", "SANDY SHORES", "Deserto do Trevor · Alamo Sea"),
    "paleto": ("04", "PALETO BAY", "Extremo norte · começo da volta"),
    "costa": ("05", "COSTA OESTE", "Great Ocean Highway"),
    "delperro": ("06", "PRAIA DE DEL PERRO", "De volta a Los Santos"),
    "aeroporto": ("07", "AEROPORTO DE LOS SANTOS", "Chegada perto das 19h30 no jogo"),
    "conta": ("07", "AEROPORTO DE LOS SANTOS", "Chegada perto das 19h30 no jogo"),
    "jatinho": ("08", "DECOLE DE JATINHO", "Rumo ao leste · próximo destino: Vice City"),
    "vice": ("08", "DECOLE DE JATINHO", "Rumo ao leste · próximo destino: Vice City"),
    "resumo": (None, "UMA VOLTA PARA GUARDAR", "Despedida de Los Santos · GTA V"),
    "final": (None, "SALVE ESTE PERCURSO", "Despedida de Los Santos · GTA V"),
}
# janela de zoom do recorte (ponto na miniatura) e rótulo
RECORTES = {
    "grove": (R.CTRL[0], "Grove Street"), "rodovia": (R.CTRL[7], "Rodovia norte"),
    "sandy": (R.CTRL[12], "Sandy Shores"), "paleto": (R.CTRL[22], "Paleto Bay"),
    "costa": (R.CTRL[29], "Costa oeste"), "delperro": (R.CTRL[35], "Praia de Del Perro"),
    "aeroporto": ((360, 1585), "Aeroporto de Los Santos"),
}
ALVO = {  # fração da rota no fim de cada trecho
    "rodovia": R.frac_parada("sandy") * 0.72, "sandy": R.frac_parada("sandy"), "paleto": R.frac_parada("paleto"),
    "costa": R.frac_parada("costa"), "delperro": R.frac_parada("delperro"), "aeroporto": 1.0,
}
PINOS = [("grove", "Grove Street"), ("rodovia", "Rodovia norte"), ("sandy", "Sandy Shores"), ("paleto", "Paleto Bay"),
         ("costa", "Costa oeste"), ("delperro", "Del Perro"), ("aeroporto", "Aeroporto")]
PINO_PT = {"grove": R.CTRL[0], "rodovia": R.CTRL[7], "sandy": R.CTRL[12], "paleto": R.CTRL[22],
           "costa": R.CTRL[29], "delperro": R.CTRL[35], "aeroporto": R.CTRL[40]}
PINO_LADO = {"grove": 1, "rodovia": -1, "sandy": -1, "paleto": 1, "costa": 1, "delperro": -1, "aeroporto": 1}


def frac_ponto(p):
    best = min(range(len(R.PONTOS)), key=lambda i: math.dist(R.PONTOS[i], p))
    return R.ACUM[best] / R.TOTAL


PINO_F = {k: frac_ponto(p) for k, p in PINO_PT.items()}


# ---------------------------------------------------------------------------
def duracao_wav(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def linha_do_tempo(pasta: Path):
    t, seg = INICIO, {}
    for sid in ORDEM:
        d = duracao_wav(pasta / f"{sid}.wav")
        nome = sid.split("-", 1)[1]
        extra = {"vice": 0.9, "conta": 0.6, "final": 1.6}.get(nome, 0.0)
        seg[nome] = (t, t + d, sid)
        t += d + GAP + extra
    return seg, t + 0.3


def legendas(seg):
    """blocos de 2-4 palavras, tempo proporcional às letras dentro de cada trecho."""
    out = []
    for nome, (a, b, _) in seg.items():
        palavras = TXT[nome].split()
        blocos, atual = [], []
        for p in palavras:
            atual.append(p)
            if len(atual) >= 4 or (len(atual) >= 2 and p[-1] in ".,:!?") or sum(len(x) for x in atual) > 20:
                blocos.append(atual)
                atual = []
        if atual:
            if blocos and len(atual) == 1:
                blocos[-1] += atual
            else:
                blocos.append(atual)
        pesos = [sum(len(x) for x in bl) + 2 for bl in blocos]
        tot = sum(pesos)
        t = a
        for bl, pe in zip(blocos, pesos):
            d = (b - a) * pe / tot
            out.append((t, t + d, bl))
            t += d
    return out


# ---------------------------------------------------------------------------
class Cena:
    def __init__(self, master: Path, pasta_voz: Path):
        self.seg, self.total = linha_do_tempo(pasta_voz)
        self.leg = legendas(self.seg)
        mst = Image.open(master).convert("RGB")
        self.master = mst
        esc = K / 6
        self.mapa = mst.resize((int(mst.width * esc), int(mst.height * esc)), Image.LANCZOS)
        self.mapa = self._tratar(self.mapa)
        cor = self.mapa.getpixel((5, 5))
        grande = Image.new("RGB", (self.mapa.width + 2 * PAD, self.mapa.height + 2 * PAD), cor)
        grande.paste(self.mapa, (PAD, PAD))
        self.mapa = grande
        self.logo = Image.open(LOGO).convert("RGBA")
        lw = 300
        self.logo = self.logo.resize((lw, int(self.logo.height * lw / self.logo.width)), Image.LANCZOS)
        self.carros = [self._carro(c) for c in (LIMA, BRANCO, ROSA)]
        self.recortes = {k: self._recorte(*v) for k, v in RECORTES.items()}
        self.sombra = self._sombras()
        self.cam = self._camera()

    # --- preparação ---------------------------------------------------------
    @staticmethod
    def _tratar(m):
        a = np.asarray(m).astype(np.float32)
        a = (a - 128) * 1.06 + 128  # um pouco mais de contraste
        a *= 0.9
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    def _sombras(self):
        g = np.zeros((H, 1), np.float32)
        y = np.arange(H)
        g[:, 0] = np.clip((330 - y) / 330, 0, 1) ** 1.4 * 0.85 + np.clip((y - 1380) / 540, 0, 1) ** 1.3 * 0.88
        alfa = (g * 255).astype(np.uint8)
        im = Image.new("RGBA", (W, H), NOITE + (0,))
        im.putalpha(Image.fromarray(np.repeat(alfa, W, axis=1)))
        return im

    @staticmethod
    def _carro(cor):
        s = 4
        im = Image.new("RGBA", (52 * s, 28 * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([2 * s, 2 * s, 50 * s, 26 * s], radius=8 * s, fill=(0, 0, 0, 120))
        d.rounded_rectangle([3 * s, 3 * s, 48 * s, 24 * s], radius=7 * s, fill=cor + (255,), outline=NOITE + (255,), width=2 * s)
        d.rounded_rectangle([28 * s, 6 * s, 37 * s, 21 * s], radius=3 * s, fill=(20, 22, 30, 255))  # para-brisa
        d.rounded_rectangle([10 * s, 7 * s, 16 * s, 20 * s], radius=2 * s, fill=(20, 22, 30, 230))  # vidro de trás
        d.rectangle([44 * s, 5 * s, 47 * s, 9 * s], fill=(255, 250, 200, 255))
        d.rectangle([44 * s, 18 * s, 47 * s, 22 * s], fill=(255, 250, 200, 255))
        return im.resize((52, 28), Image.LANCZOS)

    def _recorte(self, p, rotulo):
        cx, cy = p[0] * 6, p[1] * 6
        w, h = 780, 540
        c = self.master.crop((int(cx - w / 2), int(cy - h / 2), int(cx + w / 2), int(cy + h / 2))).resize((430, 298), Image.LANCZOS)
        card = Image.new("RGBA", (442, 352), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rectangle([0, 0, 441, 351], fill=CARVAO + (255,))
        card.paste(c, (6, 6))
        d.rectangle([0, 0, 441, 351], outline=LIMA + (255,), width=4)
        # mira no centro
        mx, my = 6 + 215, 6 + 149
        d.ellipse([mx - 16, my - 16, mx + 16, my + 16], outline=LIMA + (255,), width=4)
        d.ellipse([mx - 4, my - 4, mx + 4, my + 4], fill=LIMA + (255,))
        f = fonte(ANTON, 30)
        d.text((18, 312), rotulo.upper(), font=f, fill=BRANCO, anchor="lm")
        d.text((424, 312), "ZOOM", font=fonte(PIXEL, 18), fill=LIMA, anchor="rm")
        return card

    def progresso(self, t):
        f = 0.0
        prev = 0.0
        for nome in ["rodovia", "sandy", "paleto", "costa", "delperro", "aeroporto"]:
            a, b, _ = self.seg[nome]
            if t < a:
                return prev
            if t <= b:
                return prev + (ALVO[nome] - prev) * ease((t - a) / (b - a))
            prev = ALVO[nome]
            f = prev
        return f

    def _camera(self):
        """centro da câmera (px no mapa escalado) por quadro, seguindo o comboio com atraso suave."""
        n = int(self.total * FPS) + 2
        ilha = np.array([630 * K, 905 * K])
        pos = np.zeros((n, 3))
        cam = None
        PADV = np.array([PAD, PAD])
        r0 = self.seg["resumo"][0]
        for i in range(n):
            t = i / FPS
            p, _ = R.ponto(self.progresso(t))
            alvo = np.array([p[0] * K, p[1] * K - 40])
            alvo = ilha + (alvo - ilha) * 0.55  # a ilha sempre quase inteira na tela
            if t > self.seg["jatinho"][0]:
                alvo = ilha + (np.array([R.CTRL[40][0] * K + 160, R.CTRL[40][1] * K]) - ilha) * 0.55
            z = 1.0
            if t > r0 - 0.4:
                alvo = np.array([630 * K, 905 * K + 95])
                z = 0.74
            alvo = alvo + PADV
            alvo = np.array([alvo[0], alvo[1], z])
            cam = alvo if cam is None else cam + (alvo - cam) * 0.06
            pos[i] = cam
        return pos

    # --- desenho por quadro --------------------------------------------------
    def base(self, i):
        cx, cy, z = self.cam[min(i, len(self.cam) - 1)]
        cw, ch = W / z, H / z
        x0 = cx - cw / 2
        y0 = cy - ch / 2 + 60 / z
        x0 = max(0, min(self.mapa.width - cw, x0))
        y0 = max(0, min(self.mapa.height - ch, y0))
        if abs(z - 1) < 0.002:
            x0, y0 = round(x0), round(y0)
            return self.mapa.crop((x0, y0, x0 + W, y0 + H)).convert("RGBA"), (x0, y0, 1.0)
        im = self.mapa.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
        return im.convert("RGBA"), (x0, y0, z)

    def quadro(self, t):
        i = int(round(t * FPS))
        im, (ox, oy, zz) = self.base(i)
        tela = lambda p: ((p[0] * K + PAD - ox) * zz, (p[1] * K + PAD - oy) * zz)  # noqa: E731
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        seg = self.seg
        atual = self.trecho(t)

        # rota completa (fantasma) desenhando na abertura
        a0, b0, _ = seg["abertura"]
        rev = ease_out((t - a0 - 0.2) / 2.6)
        if rev > 0:
            n = max(2, int(len(R.PONTOS) * rev))
            pts = [tela(p) for p in R.PONTOS[:n]]
            d.line(pts, fill=(255, 255, 255, 70), width=16, joint="curve")
            d.line(pts, fill=CIANO + (150,), width=5, joint="curve")
        # rota percorrida
        f = self.progresso(t)
        if t > seg["resumo"][0]:
            f = 1.0
        if f > 0.002:
            alvo = f * R.TOTAL
            pts = [tela(p) for p, ac in zip(R.PONTOS, R.ACUM) if ac <= alvo]
            pts.append(tela(R.ponto(f)[0]))
            if len(pts) >= 2:
                d.line(pts, fill=LIMA + (55,), width=30, joint="curve")
                d.line(pts, fill=LIMA + (110,), width=18, joint="curve")
                d.line(pts, fill=LIMA + (255,), width=9, joint="curve")
        im.alpha_composite(ov)
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)

        # pinos e etiquetas
        for nome, rot in PINOS:
            alcancado = f >= PINO_F[nome] - 0.004 or t > seg["resumo"][0]
            if nome == "grove":
                alcancado = t > seg["grove"][0] - 0.3 or f > 0
            if not alcancado:
                continue
            x, y = tela(PINO_PT[nome])
            d.ellipse([x - 15, y - 15, x + 15, y + 15], fill=NOITE + (255,), outline=CIANO + (255,), width=5)
            d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=CIANO + (255,))
            mostra = t > seg["resumo"][0] or nome == atual or (nome == "aeroporto" and atual in ("conta", "jatinho"))
            if mostra:
                self.etiqueta(d, x, y, rot, PINO_LADO[nome], 34 if t < seg["resumo"][0] else 28)

        # comboio
        if t < seg["jatinho"][0] + 0.6:
            for k, car in enumerate(self.carros):
                fk = f - k * (16 / R.TOTAL)
                if fk < -0.001 and f > 0:
                    continue
                fk = max(0.0, fk)
                if f <= 0:  # parados em Grove, em fila
                    p = (R.CTRL[0][0] - k * 13, R.CTRL[0][1] + k * 13)
                    ang = math.atan2(-1, 1)
                else:
                    p, ang = R.ponto(fk)
                x, y = tela(p)
                rc = car.rotate(-math.degrees(ang), resample=Image.BICUBIC, expand=True)
                ov.alpha_composite(rc, (int(x - rc.width / 2), int(y - rc.height / 2)))

        # jatinho
        a, b, _ = seg["jatinho"]
        if a - 0.2 < t < seg["vice"][0] + 0.5:
            u = ease((t - a - 0.3) / max(0.5, b - a + 0.6))
            x0, y0 = tela(R.CTRL[40])
            x1, y1 = W + 160, y0 - 520
            x, y = x0 + (x1 - x0) * u, y0 + (y1 - y0) * u
            for s in range(14):  # rastro
                v = max(0, u - s * 0.025)
                d.ellipse([x0 + (x1 - x0) * v - 5, y0 + (y1 - y0) * v - 5, x0 + (x1 - x0) * v + 5, y0 + (y1 - y0) * v + 5],
                          fill=BRANCO + (int(160 * (1 - s / 14)),))
            self.aviao(ov, x, y, math.atan2(y1 - y0, x1 - x0), 1 + 0.5 * u)

        im.alpha_composite(ov)
        im.alpha_composite(self.sombra)
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)

        self.cabecalho(ov, d)
        self.titulo(ov, d, t, atual)
        self.recorte_ativo(ov, t, atual)
        if atual == "conta" or (seg["conta"][0] - 0.3 < t < seg["jatinho"][0] + 0.2):
            self.painel_conta(ov, t)
        if t > seg["resumo"][0]:
            self.numeros(ov, t)
        self.legenda(ov, d, t)
        self.rodape(d)
        im.alpha_composite(ov)

        # cartão Vice City
        a, b, _ = seg["vice"]
        if a - 0.35 < t < b + 1.1:
            u = ease_out((t - a + 0.35) / 0.5) * (1 - ease((t - b - 0.6) / 0.5))
            vc = self.vice(t - a)
            m = Image.new("L", (W, H), 0)
            ImageDraw.Draw(m).rectangle([0, 0, W, int(H * u)], fill=255)
            im.paste(vc, (0, 0), m)
            ov2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            self.cabecalho(ov2, ImageDraw.Draw(ov2))
            self.legenda(ov2, ImageDraw.Draw(ov2), t)
            im.alpha_composite(ov2)
        return im.convert("RGB")

    def trecho(self, t):
        atual = "abertura"
        for nome, (a, b, _) in self.seg.items():
            if t >= a - 0.15:
                atual = nome
        return atual

    # --- peças -----------------------------------------------------------------
    def etiqueta(self, d, x, y, txt, lado, tam):
        f = fonte(ANTON, tam)
        w = d.textlength(txt, font=f) + 26
        h = tam + 18
        if lado > 0:
            bx = x + 24
        else:
            bx = x - 24 - w
        by = y - h / 2 - 2
        d.rectangle([bx, by, bx + w, by + h], fill=NOITE + (235,), outline=BRANCO + (255,), width=2)
        d.text((bx + 13, by + h / 2), txt, font=f, fill=BRANCO, anchor="lm")

    def aviao(self, ov, x, y, ang, esc):
        s = 6
        im = Image.new("RGBA", (60 * s, 60 * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c = 30 * s
        corpo = [(c + 26 * s, c), (c + 20 * s, c - 3 * s), (c - 22 * s, c - 3 * s), (c - 26 * s, c), (c - 22 * s, c + 3 * s), (c + 20 * s, c + 3 * s)]
        asa = [(c + 4 * s, c), (c - 6 * s, c - 22 * s), (c - 11 * s, c - 22 * s), (c - 6 * s, c), (c - 11 * s, c + 22 * s), (c - 6 * s, c + 22 * s)]
        cauda = [(c - 18 * s, c), (c - 24 * s, c - 9 * s), (c - 27 * s, c - 9 * s), (c - 24 * s, c), (c - 27 * s, c + 9 * s), (c - 24 * s, c + 9 * s)]
        for poly in (asa, cauda, corpo):
            d.polygon(poly, fill=BRANCO + (255,), outline=NOITE + (255,))
        tam = int(64 * esc)
        im = im.resize((tam, tam), Image.LANCZOS).rotate(-math.degrees(ang), resample=Image.BICUBIC, expand=True)
        ov.alpha_composite(im, (int(x - im.width / 2), int(y - im.height / 2)))

    def cabecalho(self, ov, d):
        d.rectangle([36, 44, W - 36, 132], fill=NOITE + (225,), outline=(42, 39, 51, 255), width=2)
        ov.alpha_composite(self.logo, (56, 88 - self.logo.height // 2))
        f = fonte(ARCHIVO, 22)
        d.text((56 + self.logo.width + 22, 74), "A ÚLTIMA VOLTA", font=f, fill=BRANCO, anchor="lm")
        d.text((56 + self.logo.width + 22, 102), "GTA V · LOS SANTOS", font=f, fill=CINZA, anchor="lm")
        txt = "18 NOV · À NOITE"
        fp = fonte(ANTON, 30)
        w = d.textlength(txt, font=fp) + 36
        d.rectangle([W - 56 - w, 66, W - 56, 110], fill=LIMA + (255,))
        d.text((W - 56 - w / 2, 88), txt, font=fp, fill=NOITE, anchor="mm")

    def titulo(self, ov, d, t, atual):
        num, tit, sub = TITULOS[atual]
        a = self.seg[atual][0]
        u = ease_out((t - a + 0.15) / 0.45)
        dx = int((1 - u) * -60)
        alfa = int(255 * u)
        x, y = 40 + dx, 166
        if t > self.seg["resumo"][0] - 0.15:  # no resumo o título vai para o centro
            f = fonte(ANTON, 64)
            w = d.textlength(tit, font=f) + 50
            d.rectangle([W / 2 - w / 2, 160, W / 2 + w / 2, 244], fill=NOITE + (int(230 * u),))
            d.text((W / 2, 202), tit, font=f, fill=(LIMA if atual == "final" else BRANCO) + (alfa,), anchor="mm")
            return
        if num:
            d.rectangle([x, y, x + 70, y + 70], fill=LIMA + (alfa,))
            d.text((x + 35, y + 36), num, font=fonte(ANTON, 46), fill=NOITE + (alfa,), anchor="mm")
            x += 86
        f = fonte(ANTON, 56 if len(tit) < 20 else 46)
        w = d.textlength(tit, font=f)
        d.rectangle([x - 6, y, x + w + 18, y + 70], fill=NOITE + (int(200 * u),))
        d.text((x + 6, y + 36), tit, font=f, fill=BRANCO + (alfa,), anchor="lm")
        d.text((40 + dx, y + 100), sub, font=fonte(ARCHIVO, 28), fill=(225, 225, 235, alfa), anchor="lm",
               stroke_width=3, stroke_fill=NOITE + (alfa,))

    def recorte_ativo(self, ov, t, atual):
        if atual not in self.recortes:
            if atual in ("conta",):
                return
            return
        a, b, _ = self.seg[atual]
        u = ease_back((t - a - 0.25) / 0.5)
        sai = ease((t - b - 0.05) / 0.25) if atual != "aeroporto" else 0
        esc = max(0.01, u * (1 - sai))
        card = self.recortes[atual]
        if esc < 0.98 or esc > 1.02:
            card = card.resize((max(1, int(card.width * esc)), max(1, int(card.height * esc))), Image.BILINEAR)
        cx, cy = W - 40 - 221, 330 + 176
        ov.alpha_composite(card, (int(cx - card.width / 2), int(cy - card.height / 2)))

    def painel_conta(self, ov, t):
        a, b, _ = self.seg["conta"]
        u = ease_out((t - a + 0.2) / 0.45) * (1 - ease((t - b - 0.2) / 0.35))
        if u <= 0.01:
            return
        p = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(p)
        y0 = 560 + int((1 - u) * 80)
        d.rectangle([110, y0, W - 110, y0 + 80], fill=LIMA + (255,))
        d.text((W / 2, y0 + 41), "A CONTA DO HORÁRIO", font=fonte(ANTON, 52), fill=NOITE, anchor="mm")
        d.text((W / 2, y0 + 112), "RELÓGIO DO JOGO × TEMPO REAL", font=fonte(ARCHIVO, 26), fill=BRANCO, anchor="mm",
               stroke_width=3, stroke_fill=NOITE)
        b1 = y0 + 150
        d.rectangle([140, b1, W - 140, b1 + 190], fill=NOITE + (238,), outline=(60, 56, 72, 255), width=2)
        d.text((W / 2, b1 + 62), "1 HORA NO JOGO", font=fonte(ANTON, 58), fill=BRANCO, anchor="mm")
        d.text((W / 2, b1 + 140), "= 2 MINUTOS REAIS", font=fonte(ANTON, 52), fill=LIMA, anchor="mm")
        b2 = b1 + 220
        d.rectangle([140, b2, W - 140, b2 + 250], fill=NOITE + (238,), outline=(60, 56, 72, 255), width=2)
        d.text((W / 2 - 150, b2 + 66), "14H30", font=fonte(ANTON, 72), fill=BRANCO, anchor="mm")
        d.line([(W / 2 - 50, b2 + 66), (W / 2 + 50, b2 + 66)], fill=CIANO, width=6)
        d.polygon([(W / 2 + 58, b2 + 66), (W / 2 + 36, b2 + 52), (W / 2 + 36, b2 + 80)], fill=CIANO)
        d.text((W / 2 + 150, b2 + 66), "19H30", font=fonte(ANTON, 72), fill=BRANCO, anchor="mm")
        d.text((W / 2, b2 + 140), "5 HORAS NO JOGO", font=fonte(ARCHIVO, 32), fill=CINZA, anchor="mm")
        d.text((W / 2, b2 + 200), "~10 MINUTOS REAIS", font=fonte(ANTON, 52), fill=LIMA, anchor="mm")
        if u < 1:
            al = p.getchannel("A").point(lambda v: int(v * u))
            p.putalpha(al)
        ov.alpha_composite(p)

    def numeros(self, ov, t):
        a = self.seg["resumo"][0]
        d = ImageDraw.Draw(ov)
        for k, (big, small) in enumerate([("~25 KM", "PERCURSO ESTIMADO"), ("10-14 MIN", "VARIA COM O CARRO")]):
            u = ease_back((t - a - 0.6 - k * 0.25) / 0.5)
            if u <= 0:
                continue
            x0 = 70 + k * 480
            y0 = 1640 + int((1 - u) * 60)
            d.rectangle([x0, y0, x0 + 460, y0 + 128], fill=NOITE + (240,), outline=LIMA + (255,), width=3)
            d.text((x0 + 230, y0 + 50), big, font=fonte(ANTON, 54), fill=LIMA, anchor="mm")
            d.text((x0 + 230, y0 + 102), small, font=fonte(ARCHIVO, 22), fill=CINZA, anchor="mm")

    def legenda(self, ov, d, t):
        fin = self.seg["final"]
        if t > fin[0] - 0.1:  # chamada final fixa
            u = ease_out((t - fin[0] + 0.1) / 0.5)
            txt1 = "Essa é a página para seguir"
            txt2 = "e acompanhar o GTA 6"
            f = fonte(ANTON, 58)
            y = 1440 + int((1 - u) * 40)
            for k, tx in enumerate((txt1, txt2)):
                d.text((W / 2, y + k * 76), tx.upper(), font=f, fill=(BRANCO if k == 0 else LIMA) + (int(255 * u),),
                       anchor="mm", stroke_width=6, stroke_fill=NOITE)
            return
        for a, b, bl in self.leg:
            if a <= t < b:
                break
        else:
            return
        y = 1500 if t < self.seg["resumo"][0] else 1520
        f = fonte(ANTON, 64)
        palavras = [p.upper() for p in bl]
        dest = max(range(len(palavras)), key=lambda k: len(palavras[k].strip(".,:!?")))
        larg = [d.textlength(p, font=f) for p in palavras]
        esp = 18
        total = sum(larg) + esp * (len(palavras) - 1)
        linhas = [list(range(len(palavras)))]
        if total > W - 120:
            meio = len(palavras) // 2
            linhas = [list(range(meio)), list(range(meio, len(palavras)))]
        u = ease_out((t - a) / 0.12)
        for li, idx in enumerate(linhas):
            tw = sum(larg[k] for k in idx) + esp * (len(idx) - 1)
            x = W / 2 - tw / 2
            yy = y + li * 80 - (len(linhas) - 1) * 40 + int((1 - u) * 14)
            for k in idx:
                cor = LIMA if k == dest else BRANCO
                d.text((x, yy), palavras[k], font=f, fill=cor + (int(255 * u),), anchor="lm", stroke_width=7, stroke_fill=NOITE)
                x += larg[k] + esp

    def rodape(self, d):
        d.line([(40, 1862), (W - 40, 1862)], fill=(255, 255, 255, 60), width=2)
        f = fonte(ARCHIVO, 24)
        d.text((40, 1890), "@pixelzada.br", font=f, fill=BRANCO, anchor="lm")
        d.text((W - 40, 1890), "MAPA DO JOGO · GTA V", font=f, fill=CINZA, anchor="rm")

    _vice_fundo = None

    def vice(self, tt):
        if self._vice_fundo is None:
            self._vice_fundo = fundo_vice()
        im = self._vice_fundo.copy()
        d = ImageDraw.Draw(im)
        u = ease_back((tt - 0.1) / 0.6)
        y = 760 + int((1 - min(u, 1.2)) * 80)
        d.text((W / 2, y - 120), "PRÓXIMO DESTINO", font=fonte(ARCHIVO, 44), fill=BRANCO, anchor="mm")
        fv = fonte(ANTON, 230)
        brilho = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(brilho).text((W / 2, y + 60), "VICE CITY", font=fv, fill=ROSA + (255,), anchor="mm")
        brilho = brilho.filter(ImageFilter.GaussianBlur(26))
        im.alpha_composite(brilho)
        im.alpha_composite(brilho)
        d = ImageDraw.Draw(im)
        d.text((W / 2, y + 60), "VICE CITY", font=fv, fill=BRANCO, anchor="mm", stroke_width=4, stroke_fill=ROSA)
        d.rectangle([W / 2 - 230, y + 230, W / 2 + 230, y + 290], fill=LIMA)
        d.text((W / 2, y + 261), "GTA 6 · 19 DE NOVEMBRO", font=fonte(ANTON, 40), fill=NOITE, anchor="mm")
        return im.convert("RGB")


def degrade(w, h, cores):
    y = np.linspace(0, 1, h)[:, None]
    n = len(cores) - 1
    pos = y * n
    i = np.clip(pos.astype(int), 0, n - 1)
    a = pos - i
    c = np.array(cores, np.float32)
    col = c[i[:, 0]] * (1 - a) + c[i[:, 0] + 1] * a
    return Image.fromarray(np.repeat(col[:, None, :], w, axis=1).astype(np.uint8))


def palmeira(d, x, base, alt, cor, inclina=0.15):
    topo = (x + int(alt * inclina), base - alt)
    pts = [(x + int(alt * inclina * (t / 20) ** 1.6), base - int(alt * t / 20)) for t in range(21)]
    for i in range(20):
        d.line([pts[i], pts[i + 1]], fill=cor, width=max(3, int(alt * 0.035 * (1 - i / 30))))
    for ang in range(0, 360, 36):
        r = alt * 0.42
        a = math.radians(ang)
        ex, ey = topo[0] + r * math.cos(a), topo[1] + r * 0.55 * math.sin(a) + r * 0.25
        mx, my = topo[0] + r * 0.5 * math.cos(a), topo[1] - r * 0.18 + r * 0.25 * math.sin(a)
        for k in range(8):
            t0, t1 = k / 8, (k + 1) / 8
            p0 = ((1 - t0) ** 2 * topo[0] + 2 * (1 - t0) * t0 * mx + t0 ** 2 * ex, (1 - t0) ** 2 * topo[1] + 2 * (1 - t0) * t0 * my + t0 ** 2 * ey)
            p1 = ((1 - t1) ** 2 * topo[0] + 2 * (1 - t1) * t1 * mx + t1 ** 2 * ex, (1 - t1) ** 2 * topo[1] + 2 * (1 - t1) * t1 * my + t1 ** 2 * ey)
            d.line([p0, p1], fill=cor, width=max(2, int(alt * 0.03 * (1 - t0))))


def fundo_vice():
    im = degrade(W, H, [(20, 6, 42), (74, 20, 140), (196, 44, 140), (255, 120, 90), (255, 176, 96)]).convert("RGBA")
    sol = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sol)
    cx, cy, r = W // 2, int(H * 0.70), 330
    sd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 214, 120, 255))
    for i in range(7):
        y = cy + int(r * (0.1 + i * 0.13))
        sd.rectangle([cx - r, y, cx + r, y + 5 + i * 4], fill=(0, 0, 0, 0))
    im.alpha_composite(sol)
    mar = degrade(W, int(H * 0.2), [(60, 16, 100), (20, 6, 42)]).convert("RGBA")
    im.paste(mar, (0, int(H * 0.8)))
    d = ImageDraw.Draw(im)
    for i in range(16):
        y = int(H * 0.8) + int((i ** 1.5) * 2.4)
        d.line([(0, y), (W, y)], fill=(255, 61, 139, 255), width=2)
    cor = (16, 4, 30, 255)
    palmeira(d, 90, int(H * 0.82), 760, cor, 0.18)
    palmeira(d, 230, int(H * 0.83), 520, cor, 0.25)
    palmeira(d, W - 110, int(H * 0.82), 700, cor, -0.2)
    palmeira(d, W - 260, int(H * 0.84), 470, cor, -0.12)
    return im


# ---------------------------------------------------------------------------
def audio(pasta: Path, seg, total, saida: Path):
    taxa = 24000
    pista = np.zeros(int((total + 0.5) * taxa), np.float32)
    for nome, (a, b, sid) in seg.items():
        with wave.open(str(pasta / f"{sid}.wav")) as w:
            taxa_w = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        if taxa_w != taxa:
            x = np.interp(np.arange(0, len(x), taxa_w / taxa), np.arange(len(x)), x).astype(np.float32)
        i = int(a * taxa)
        pista[i:i + len(x)] += x[: len(pista) - i]
    pico = np.abs(pista).max() or 1
    pista = pista / pico * 0.89
    voz = saida.with_suffix(".voz.wav")
    with wave.open(str(voz), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(taxa)
        w.writeframes((pista * 32767).astype(np.int16).tobytes())
    mus = saida.with_suffix(".musica.wav")
    trilha(total + 0.5, mus)
    return voz, mus


def trilha(dur, saida: Path, bpm=100):
    """trilha synthwave simples gerada aqui (sem direitos de terceiros)."""
    sr = 44100
    n = int(dur * sr)
    t = np.arange(n) / sr
    out = np.zeros(n, np.float32)
    beat = 60 / bpm
    acordes = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # Am F C G
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)  # noqa: E731
    compasso = beat * 4
    for c in range(int(dur / compasso) + 1):
        a0 = c * compasso
        i0, i1 = int(a0 * sr), min(n, int((a0 + compasso) * sr))
        if i0 >= n:
            break
        tt = t[i0:i1] - a0
        env = np.minimum(1, tt / 0.4) * np.minimum(1, (compasso - tt) / 0.3)
        for m in acordes[c % 4]:
            for det in (-0.12, 0.12):
                f = hz(m) * (1 + det / 100)
                out[i0:i1] += 0.05 * env * (2 * ((tt * f) % 1) - 1)
        # baixo em colcheias
        fb = hz(acordes[c % 4][0] - 24)
        for k in range(8):
            j0 = int((a0 + k * beat / 2) * sr)
            j1 = min(n, j0 + int(beat / 2 * sr * 0.9))
            if j0 >= n:
                break
            tb = t[j0:j1] - t[j0]
            out[j0:j1] += 0.16 * np.exp(-tb * 5) * np.sign(np.sin(2 * np.pi * fb * tb))
    # passa-baixa simples no pad/baixo
    k = 18
    out = np.convolve(out, np.ones(k) / k, mode="same").astype(np.float32)
    for b in range(int(dur / beat) + 1):  # bumbo e chimbal
        j0 = int(b * beat * sr)
        if j0 >= n:
            break
        tk = np.arange(min(int(0.25 * sr), n - j0)) / sr
        out[j0:j0 + len(tk)] += 0.5 * np.sin(2 * np.pi * (50 + 90 * np.exp(-tk * 30)) * tk) * np.exp(-tk * 9)
        h0 = int((b * beat + beat / 2) * sr)
        if h0 < n:
            th = np.arange(min(int(0.05 * sr), n - h0)) / sr
            out[h0:h0 + len(th)] += 0.05 * np.random.default_rng(b).standard_normal(len(th)) * np.exp(-th * 80)
    fade = np.minimum(1, np.minimum(t / 1.0, (dur - t) / 2.0))
    out *= fade
    out /= np.abs(out).max() or 1
    with wave.open(str(saida), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((out * 0.8 * 32767).astype(np.int16).tobytes())


def main():
    master, pasta, saida = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    cena = Cena(master, pasta)
    if "--quadro" in sys.argv:
        for s in sys.argv[sys.argv.index("--quadro") + 1].split(","):
            cena.quadro(float(s)).save(saida.parent / f"quadro-{float(s):05.1f}.jpg", quality=88)
        print(json.dumps({k: [round(v[0], 2), round(v[1], 2)] for k, v in cena.seg.items()}))
        return
    total = cena.total
    if "--ate" in sys.argv:
        total = float(sys.argv[sys.argv.index("--ate") + 1])
    voz, mus = audio(pasta, cena.seg, cena.total, saida)
    video = saida.with_suffix(".mudo.mp4")
    n = int(total * FPS)
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                          "-pix_fmt", "yuv420p", str(video)], stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(cena.quadro(i / FPS).tobytes())
        if i % 150 == 0:
            print(f"quadro {i}/{n}", flush=True)
    p.stdin.close(); p.wait()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(voz), "-i", str(mus),
                    "-filter_complex",
                    "[1:a]aresample=48000,volume=1.0,asplit=2[v][sc];[2:a]aresample=48000,volume=0.22[m];"
                    "[m][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[md];"
                    "[v][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.2f}",
                    "-movflags", "+faststart", str(saida)], check=True)
    for f in (video, voz, mus):
        f.unlink(missing_ok=True)
    print("ok", saida, round(total, 1), "s")


if __name__ == "__main__":
    main()
