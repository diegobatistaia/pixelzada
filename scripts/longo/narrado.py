"""Vídeo longo NARRADO do YouTube (formato do piloto "Leonida é a Flórida", 16/11/2026).

Diferente da série de listas (episodio.py): é um documentário curto de 7-10 min com uma
voz só (Gemini TTS), imagens oficiais da Rockstar (site do GTA VI, trailer de lançamento),
fotos reais (Wikimedia Commons, com crédito na descrição), mapa animado e motion graphics.

Identidade "Pixelzada Vice": pôr do sol roxo/rosa/laranja, palmeiras, neon; legenda geral
pequena e discreta; frases de impacto, nomes e números grandes na identidade da Pixelzada.

    python -m scripts.longo.narrado tudo scripts/longo/narrados/<slug>.json

Saída em trabalho/narrado/<slug>/ (vídeo final, capa, descrição). Não publica nada.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = Path(__file__).resolve().parents[2]
AQUI = Path(__file__).resolve().parent
FONTES = RAIZ / "scripts/social/gerador/fonts"
ANTON = str(FONTES / "f1.ttf")
ARCHIVO = str(FONTES / "f2.ttf")
PIXEL = str(FONTES / "f4.ttf")
LOGO = AQUI / "logo.png"
OFICIAL = RAIZ / "trabalho/oficial"
W, H, FPS = 1920, 1080, 30
UA = {"User-Agent": "PixelzadaVideoBot/1.0 (contato pelo site pixelzada.com.br)"}

# paleta "Pixelzada Vice"
NOITE = (18, 6, 36)
ROXO = (74, 20, 140)
ROSA = (255, 61, 139)
LARANJA = (255, 140, 66)
CIANO = (46, 230, 214)
LIMA = (198, 255, 26)
BRANCO = (255, 255, 255)

sys.path.insert(0, str(RAIZ))
from scripts.longo import episodio as EP  # noqa: E402  (voz Gemini, sh, duracao)

sh, duracao = EP.sh, EP.duracao


def fonte(c, t):
    return ImageFont.truetype(c, int(t))


# ---------------------------------------------------------------------------
# roteiro
# ---------------------------------------------------------------------------
def frases(texto: str) -> list[str]:
    return [f for f in re.split(r"(?<=[.!?])\s+", texto.strip().replace("\n", " ")) if f]


def carregar(arq: Path) -> dict:
    ep = json.loads(arq.read_text(encoding="utf-8"))
    roteiro = (RAIZ / ep["roteiro"]).read_text(encoding="utf-8")
    textos = {}
    for blk in re.split(r"\n(?=\[)", roteiro.strip()):
        nome, txt = blk.split("]\n", 1)
        textos[nome.strip("[ ")] = txt.strip()
    for c in ep["cenas"]:
        c["texto"] = textos[c["id"]]
        c["frases"] = frases(c["texto"])
    return ep


# ---------------------------------------------------------------------------
# voz: um trecho por cena, uma voz só; tempo de cada frase pelos silêncios
# ---------------------------------------------------------------------------
def narrar(ep: dict, trab: Path) -> str:
    segs = [{"id": c["id"], "texto": c["texto"]} for c in ep["cenas"]]
    voz = EP.narrar(segs, trab)
    for c, s in zip(ep["cenas"], segs):
        c["audio"], c["dur"] = s["audio"], s["dur"]
        c["t_frases"] = tempos_frases(s["audio"], c["frases"], s["dur"])
    return voz


def tempos_frases(audio: Path, fr: list[str], dur: float) -> list[tuple[float, float]]:
    r = subprocess.run(["ffmpeg", "-i", str(audio), "-af", "silencedetect=noise=-38dB:d=0.18", "-f", "null", "-"],
                       capture_output=True, text=True)
    sil = []
    ini = None
    for l in r.stderr.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", l)
        if m:
            ini = float(m.group(1))
        m = re.search(r"silence_end: ([\d.]+)", l)
        if m and ini is not None:
            sil.append(((ini + float(m.group(1))) / 2, float(m.group(1)) - ini))
            ini = None
    util = max(0.5, dur - 0.35)
    total = sum(len(f) for f in fr) or 1
    est, acc = [], 0.0
    for f in fr[:-1]:
        acc += len(f) / total * util
        est.append(acc)
    cortes, usados = [], set()
    for e in est:  # silêncio mais próximo da estimativa (até 1,6 s de distância)
        cand = [(abs(m - e) - min(d, .6), i, m) for i, (m, d) in enumerate(sil) if i not in usados and abs(m - e) < 1.6]
        if cand:
            _, i, m = min(cand)
            usados.add(i)
            cortes.append(m)
        else:
            cortes.append(e)
    cortes = sorted(cortes)
    lim = [0.0] + cortes + [util]
    return [(lim[i], lim[i + 1]) for i in range(len(fr))]


# ---------------------------------------------------------------------------
# material
# ---------------------------------------------------------------------------
def oficial(prefixo: str) -> Path:
    achados = sorted(p for p in OFICIAL.iterdir() if p.name.startswith(prefixo))
    if not achados:
        raise RuntimeError(f"imagem oficial não encontrada: {prefixo}")
    return achados[0]


CREDITOS: list[str] = []


def commons(consulta: str, pasta: Path, n: int = 0) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    chave = re.sub(r"[^a-z0-9]+", "-", consulta.lower()).strip("-")
    dest = pasta / f"{chave}-{n}.jpg"
    meta = dest.with_suffix(".json")
    if dest.exists() and meta.exists():
        CREDITOS.append(json.loads(meta.read_text())["credito"])
        return dest
    q = {"action": "query", "format": "json", "generator": "search", "gsrnamespace": "6",
         "gsrsearch": f"{consulta} filetype:bitmap", "gsrlimit": "20", "prop": "imageinfo",
         "iiprop": "url|size|extmetadata|mime", "iiurlwidth": "2200"}
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(q)
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read())
    paginas = sorted((d.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    bons = []
    for p in paginas:
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("mime") not in ("image/jpeg", "image/png"):
            continue
        if ii.get("width", 0) < 1400 or ii.get("width", 0) < ii.get("height", 1) * 1.3:
            continue
        em = ii.get("extmetadata") or {}
        lic = (em.get("LicenseShortName") or {}).get("value", "")
        if not re.search(r"CC|Public domain|PD", lic, re.I) or re.search(r"NC|ND", lic):
            continue
        autor = re.sub(r"<[^>]+>", "", (em.get("Artist") or {}).get("value", "")).strip()[:80]
        bons.append((p["title"], ii.get("thumburl") or ii["url"], autor, lic, ii.get("descriptionurl", "")))
    if len(bons) <= n:
        raise RuntimeError(f"Commons sem foto boa para: {consulta}")
    titulo, link, autor, lic, pagina = bons[n]
    dest.write_bytes(urllib.request.urlopen(urllib.request.Request(link, headers=UA), timeout=90).read())
    credito = f"{titulo.replace('File:', '')}: {autor or 'autor no Commons'} ({lic}) {pagina}"
    meta.write_text(json.dumps({"credito": credito}, ensure_ascii=False))
    CREDITOS.append(credito)
    print(f"  foto real '{consulta}': {titulo}")
    return dest


# ---------------------------------------------------------------------------
# artes: fundo da identidade, mapa, cartões
# ---------------------------------------------------------------------------
def degrade(w: int, h: int, cores: list[tuple[int, int, int]]) -> Image.Image:
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    n = len(cores) - 1
    for y in range(h):
        f = y / (h - 1) * n
        i = min(int(f), n - 1)
        a = f - i
        c = tuple(int(cores[i][k] * (1 - a) + cores[i + 1][k] * a) for k in range(3))
        d.line([(0, y), (w, y)], fill=c)
    return im


def palmeira(d: ImageDraw.ImageDraw, x: int, base: int, alt: int, cor, inclina: float = 0.15):
    topo = (x + int(alt * inclina), base - alt)
    pts = [(x + int(alt * inclina * (t / 20) ** 1.6), base - int(alt * t / 20)) for t in range(21)]
    for i in range(20):
        larg = int(alt * 0.035 * (1 - i / 30))
        d.line([pts[i], pts[i + 1]], fill=cor, width=max(3, larg))
    for ang in range(0, 360, 36):
        r = alt * 0.42
        a = math.radians(ang)
        ex, ey = topo[0] + r * math.cos(a), topo[1] + r * 0.55 * math.sin(a) + r * 0.25
        mx, my = topo[0] + r * 0.5 * math.cos(a), topo[1] - r * 0.18 + r * 0.25 * math.sin(a)
        for k in range(8):
            t0, t1 = k / 8, (k + 1) / 8
            p0 = ((1 - t0) ** 2 * topo[0] + 2 * (1 - t0) * t0 * mx + t0 ** 2 * ex,
                  (1 - t0) ** 2 * topo[1] + 2 * (1 - t0) * t0 * my + t0 ** 2 * ey)
            p1 = ((1 - t1) ** 2 * topo[0] + 2 * (1 - t1) * t1 * mx + t1 ** 2 * ex,
                  (1 - t1) ** 2 * topo[1] + 2 * (1 - t1) * t1 * my + t1 ** 2 * ey)
            d.line([p0, p1], fill=cor, width=max(2, int(alt * 0.03 * (1 - t0))))


def fundo_vice(w: int = W, h: int = H, sol: bool = True) -> Image.Image:
    im = degrade(w, h, [(20, 6, 42), (74, 20, 140), (196, 44, 140), (255, 120, 90), (255, 176, 96)])
    d = ImageDraw.Draw(im)
    if sol:
        cx, cy, r = w // 2, int(h * 0.72), int(h * 0.26)
        sol_im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sol_im)
        sd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 214, 120, 255))
        for i in range(7):  # faixas do sol estilo synthwave
            y = cy + int(r * (0.1 + i * 0.13))
            sd.rectangle([cx - r, y, cx + r, y + 4 + i * 3], fill=(0, 0, 0, 0))
        im.paste(sol_im, (0, 0), sol_im)
    # mar
    mar = degrade(w, int(h * 0.2), [(60, 16, 100), (20, 6, 42)])
    im.paste(mar, (0, int(h * 0.8)))
    for i in range(14):
        y = int(h * 0.8) + int((i ** 1.5) * 2.2)
        d.line([(0, y), (w, y)], fill=(255, 61, 139), width=1)
    cor = (16, 4, 30)
    palmeira(d, int(w * 0.07), int(h * 0.86), int(h * 0.62), cor, 0.18)
    palmeira(d, int(w * 0.16), int(h * 0.84), int(h * 0.42), cor, -0.12)
    palmeira(d, int(w * 0.90), int(h * 0.86), int(h * 0.66), cor, -0.2)
    palmeira(d, int(w * 0.82), int(h * 0.84), int(h * 0.38), cor, 0.12)
    return im


def projetar(lon, lat, caixa):
    x0, y0, esc = caixa
    return (x0 + (lon + 87.7) * esc * math.cos(math.radians(28)), y0 + (31.1 - lat) * esc)


REGIOES = {  # posição aproximada (equivalente real) no mapa da Flórida
    "vice-city": ("VICE CITY", -80.2, 25.78, "Miami"),
    "keys": ("LEONIDA KEYS", -81.2, 24.75, "Florida Keys"),
    "grassrivers": ("GRASSRIVERS", -80.95, 25.95, "Everglades"),
    "gellhorn": ("PORT GELLHORN", -85.66, 30.16, "Panhandle"),
    "ambrosia": ("AMBROSIA", -80.93, 26.75, "Clewiston"),
    "kalaga": ("MOUNT KALAGA", -81.75, 29.25, "Ocala"),
}


def contorno_florida() -> list[list[tuple[float, float]]]:
    for arq in [RAIZ / "trabalho/florida.geojson", AQUI / "florida-simples.json"]:
        if arq.exists():
            g = json.loads(arq.read_text())
            if g.get("type") == "FeatureCollection":
                g = g["features"][0]
            geo = g.get("geometry", g)
            polis = geo["coordinates"] if geo["type"] == "MultiPolygon" else [geo["coordinates"]]
            return [[tuple(p) for p in poli[0]] for poli in polis]
    raise RuntimeError("sem contorno da Flórida")


def arte_mapa(destaque: str | None, todas: bool = True) -> Image.Image:
    im = degrade(W, H, [(12, 4, 28), (34, 10, 66), (20, 6, 42)])
    d = ImageDraw.Draw(im, "RGBA")
    for x in range(0, W, 60):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 10))
    for y in range(0, H, 60):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 10))
    caixa = (540, 55, 148)
    polis = contorno_florida()
    brilho = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(brilho)
    for poli in polis:
        pts = [projetar(lo, la, caixa) for lo, la in poli]
        if len(pts) < 3:
            continue
        d.polygon(pts, fill=(74, 20, 140, 255))
        bd.line(pts + [pts[0]], fill=(255, 61, 139, 255), width=10)
    brilho = brilho.filter(ImageFilter.GaussianBlur(14))
    im.paste(brilho, (0, 0), brilho)
    d = ImageDraw.Draw(im, "RGBA")
    for poli in polis:
        pts = [projetar(lo, la, caixa) for lo, la in poli]
        if len(pts) >= 3:
            d.line(pts + [pts[0]], fill=(255, 61, 139, 255), width=4)
    # ilhas das Keys (o contorno simples não tem)
    for i in range(14):
        lo, la = -80.35 - i * 0.11, 25.15 - (i ** 1.25) * 0.032
        x, y = projetar(lo, la, caixa)
        d.ellipse([x - 5, y - 3, x + 5, y + 3], fill=(255, 61, 139, 230))
    fp = fonte(PIXEL, 20)
    for txt, lo, la in [("GOLFO DO MÉXICO", -86.6, 27.4), ("OCEANO ATLÂNTICO", -79.9, 29.6)]:
        x, y = projetar(lo, la, caixa)
        d.text((x, y), txt, font=fp, fill=(255, 255, 255, 70))
    fl = fonte(ANTON, 34)
    fs = fonte(PIXEL, 18)
    for chave, (nome, lo, la, real) in REGIOES.items():
        x, y = projetar(lo, la, caixa)
        ativo = chave == destaque
        if not todas and not ativo:
            continue
        if ativo:
            for r, a in [(70, 40), (46, 80), (26, 160)]:
                d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 61, 139, a))
            d.ellipse([x - 12, y - 12, x + 12, y + 12], fill=(255, 255, 255, 255))
        else:
            d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=(46, 230, 214, 200 if destaque is None else 120))
        tl = fl.getlength(nome)
        lx = x - 26 - tl - 24 if chave == "grassrivers" else x + 26
        if chave == "gellhorn":
            lx, y = x - tl / 2 - 12, y + 30
        if chave == "keys":
            lx, y = x - tl - 70, y + 40
        alpha = 255 if ativo or destaque is None else 120
        fundo = (255, 61, 139, alpha) if ativo else (18, 6, 36, int(alpha * .85))
        d.rounded_rectangle([lx, y - 24, lx + tl + 24, y + 24], radius=8, fill=fundo,
                            outline=(46, 230, 214, alpha) if not ativo else None, width=2)
        d.text((lx + 12, y - 22), nome, font=fl, fill=(255, 255, 255, alpha))
        if ativo:
            d.text((lx + 12, y + 30), f"VIDA REAL: {real.upper()}", font=fs, fill=(46, 230, 214, 255))
    d.text((60, H - 60), "MAPA DA FLÓRIDA REAL · REGIÕES DE LEONIDA EM POSIÇÃO APROXIMADA", font=fonte(PIXEL, 18),
           fill=(255, 255, 255, 120))
    return im


def arte_cartao(titulo: str, apoio: str = "") -> Image.Image:
    im = fundo_vice()
    escuro = Image.new("RGBA", (W, H), (18, 6, 36, 90))
    im.paste(escuro, (0, 0), escuro)
    d = ImageDraw.Draw(im, "RGBA")
    ft = fonte(ANTON, 170)
    linhas = EP.quebrar(titulo.upper(), ft, W - 300)
    y = H * 0.30 - (len(linhas) - 1) * 90
    for l in linhas:
        tl = ft.getlength(l)
        x = (W - tl) / 2
        sombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sombra).text((x + 8, y + 10), l, font=ft, fill=(18, 6, 36, 200))
        im.paste(sombra, (0, 0), sombra)
        texto_degrade(im, (x, y), l, ft)
        y += 185
    if apoio:
        fa = fonte(ARCHIVO, 54)
        tl = fa.getlength(apoio)
        d.rounded_rectangle([(W - tl) / 2 - 24, y + 20, (W + tl) / 2 + 24, y + 100], radius=14, fill=(18, 6, 36, 220))
        d.text(((W - tl) / 2, y + 28), apoio, font=fa, fill=CIANO)
    return im


def texto_degrade(im: Image.Image, pos, texto: str, f, cores=((255, 214, 120), (255, 61, 139), (170, 60, 255))):
    x, y = int(pos[0]), int(pos[1])
    bb = f.getbbox(texto)
    w, h = bb[2] + 4, bb[3] + 8
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((0, 0), texto, font=f, fill=255)
    grad = degrade(w, h, list(cores))
    im.paste(grad, (x, y), mask)


# ---------------------------------------------------------------------------
# planos (cada um vira um clipe 1920x1080 sem áudio)
# ---------------------------------------------------------------------------
def kenburns(img: Path | Image.Image, dur: float, saida: Path, tipo: int = 0):
    if isinstance(img, Image.Image):
        tmp = saida.with_suffix(".png")
        img.convert("RGB").save(tmp)
        img = tmp
    n = max(1, int(dur * FPS))
    zs = [("min(1.0+0.10*on/{n},1.10)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
          ("max(1.10-0.10*on/{n},1.0)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
          ("1.08", "(iw-iw/zoom)*on/{n}", "ih/2-(ih/zoom/2)"),
          ("1.08", "(iw-iw/zoom)*(1-on/{n})", "ih/2-(ih/zoom/2)")][tipo % 4]
    z, x, y = (s.format(n=n) for s in zs)
    vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={W}x{H}:fps={FPS},setsar=1,format=yuv420p")
    sh("ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img, "-vf", vf, "-frames:v", n,
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", FPS, saida)


_CROP: dict[str, str] = {}


def corte_preto(video: Path) -> str:
    if str(video) not in _CROP:
        r = subprocess.run(["ffmpeg", "-ss", "20", "-i", str(video), "-t", "20", "-vf", "cropdetect=24:2:0", "-f", "null", "-"],
                           capture_output=True, text=True)
        cs = re.findall(r"crop=(\d+:\d+:\d+:\d+)", r.stderr)
        _CROP[str(video)] = max(set(cs), key=cs.count) if cs else ""
    return _CROP[str(video)]


def trecho(video: Path, ss: float, dur: float, saida: Path):
    c = corte_preto(video)
    vf = (f"crop={c}," if c else "") + (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                                        f"setsar=1,fps={FPS},format=yuv420p")
    sh("ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ss:.2f}", "-i", video, "-t", f"{dur:.3f}", "-an", "-vf", vf,
       "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", FPS, saida)


def render_plano(p: dict, dur: float, saida: Path, trab: Path, i: int) -> str:
    k, v = p["v"].split(":", 1)
    if k == "o":
        kenburns(oficial(v), dur, saida, i)
        return "GTA 6 · OFICIAL"
    if k == "t":
        trecho(oficial("GTAVI_Launch_Trailer"), float(v), dur, saida)
        return "GTA 6 · TRAILER"
    if k == "p":
        trecho(oficial("GTAVI_Pre-Load_Now"), float(v), dur, saida)
        return "GTA 6 · OFICIAL"
    if k == "r":
        n = int(p.get("n", 0))
        pal = v.split()
        for corte in range(len(pal), 1, -1):  # sem resultado: tenta com menos palavras
            try:
                kenburns(commons(" ".join(pal[:corte]), trab / "reais", n), dur, saida, i)
                return "VIDA REAL"
            except Exception as e:  # noqa: BLE001
                print(f"    Commons: {e}")
        kenburns(fundo_vice(), dur, saida, 0)
        return ""
    if k == "m":
        kenburns(arte_mapa(None if v == "todas" else v), dur, saida, 0)
        return "MAPA"
    if k == "c":
        titulo, _, apoio = v.partition("|")
        kenburns(arte_cartao(titulo, apoio), dur, saida, 0)
        return ""
    if k == "f":
        kenburns(fundo_vice(), dur, saida, 0)
        return ""
    raise RuntimeError(f"plano desconhecido: {p}")


def tempos_planos(c: dict) -> list[tuple[float, float]]:
    pl = c["planos"]
    dur = c["dur"]
    ancora = [c["t_frases"][p["f"]][0] if "f" in p else None for p in pl]
    ancora[0] = 0.0
    ult = 0.0
    for k in range(1, len(pl)):  # âncora fora de ordem ou colada na anterior vira automática
        if ancora[k] is not None:
            if ancora[k] < ult + 1.2 or ancora[k] > dur - 1.2:
                ancora[k] = None
            else:
                ult = ancora[k]
    out = [0.0] * len(pl)
    i = 0
    while i < len(pl):
        j = i + 1
        while j < len(pl) and ancora[j] is None:
            j += 1
        fim = ancora[j] if j < len(pl) else dur
        passo = (fim - ancora[i]) / (j - i)
        for k in range(i, j):
            out[k] = ancora[i] + passo * (k - i)
        i = j
    return [(out[k], out[k + 1] if k + 1 < len(pl) else dur) for k in range(len(pl))]


# ---------------------------------------------------------------------------
# legenda e motion graphics (ASS, queimado no fim)
# ---------------------------------------------------------------------------
def ass_t(s: float) -> str:
    s = max(0, s)
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"


def ass_cor(rgb, a=0) -> str:
    return f"&H{a:02X}{rgb[2]:02X}{rgb[1]:02X}{rgb[0]:02X}"


CAB = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Legenda,Archivo SemiBold,40,&H00FFFFFF,&H00FFFFFF,&H00240612,&H96000000,0,0,0,0,100,100,0.5,0,1,2.2,1.5,2,200,200,62,1
Style: Grande,Anton,150,&H00FFFFFF,&H00FFFFFF,&H00240612,&H00000000,0,0,0,0,100,100,1,0,1,4,6,1,110,110,250,1
Style: Apoio,Archivo SemiBold,44,{ciano},&H00FFFFFF,&H00240612,&HC8240612,0,0,0,0,100,100,0.5,0,3,10,0,1,118,110,190,1
Style: Etiqueta,Silkscreen,24,&H00FFFFFF,&H00FFFFFF,{rosa},&H00000000,0,0,0,0,100,100,1,0,3,7,0,7,52,52,48,1
Style: EtiquetaReal,Silkscreen,24,&H00240612,&H00FFFFFF,{ciano},&H00000000,0,0,0,0,100,100,1,0,3,7,0,7,52,52,48,1
Style: Capitulo,Silkscreen,24,&H00FFFFFF,&H00FFFFFF,&H00240612,&H00000000,0,0,0,0,100,100,1,0,3,7,0,9,52,190,48,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def pedacos(frase: str, ini: float, fim: float, max_c: int = 46) -> list[tuple[float, float, str]]:
    pal = frase.split()
    linhas, atual = [], ""
    for p in pal:
        if len(atual) + len(p) + 1 > max_c and atual:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    if atual:
        linhas.append(atual)
    total = sum(len(l) + 3 for l in linhas)
    out, t = [], ini
    for l in linhas:
        dt = (fim - ini) * (len(l) + 3) / total
        out.append((t, t + dt, l))
        t += dt
    return out


def escapa(t: str) -> str:
    return t.replace("{", "(").replace("}", ")").replace("\n", "\\N")


def legenda_ass(ep: dict, saida: Path, inicio_cena: dict) -> None:
    ev = []
    for c in ep["cenas"]:
        t0 = inicio_cena[c["id"]]
        for f, (a, b) in zip(c["frases"], c["t_frases"]):
            for x, y, l in pedacos(f, t0 + a, t0 + b):
                ev.append(f"Dialogue: 0,{ass_t(x)},{ass_t(y - 0.02)},Legenda,,0,0,0,,{escapa(l)}")
        # etiqueta da fonte da imagem em cada plano
        for (a, b), et in zip(c["t_planos"], c["etiquetas"]):
            if not et or b - a < 1.2:
                continue
            est = "EtiquetaReal" if et == "VIDA REAL" else "Etiqueta"
            ev.append(f"Dialogue: 1,{ass_t(t0 + a + .15)},{ass_t(t0 + b - .1)},{est},,0,0,0,,"
                      f"{{\\fad(200,150)}}{escapa(et)}")
        if c.get("capitulo"):
            ev.append(f"Dialogue: 1,{ass_t(t0)},{ass_t(t0 + c['dur'])},Capitulo,,0,0,0,,"
                      f"{{\\fad(300,300)}}{escapa(c['capitulo'].upper())}")
        for dq in c.get("destaques", []):
            a = c["t_frases"][dq.get("f", 0)][0] + dq.get("atraso", 0.15)
            b = min(c["dur"], a + dq.get("dur", 3.6))
            ini, fim = t0 + a, t0 + b
            cor = {"rosa": ROSA, "laranja": LARANJA, "ciano": CIANO, "lima": LIMA}.get(dq.get("cor", "rosa"), ROSA)
            tam = dq.get("tam", 150)
            pos = dq.get("pos", "esq")
            if pos == "centro":
                cab = f"{{\\an5\\pos(960,470)\\fs{tam}\\fad(120,250)\\fscx60\\fscy60\\t(0,220,\\fscx100\\fscy100)\\1c{ass_cor(cor)}\\shad6\\4c&H40240612}}"
                ev.append(f"Dialogue: 2,{ass_t(ini)},{ass_t(fim)},Grande,,0,0,0,,{cab}{escapa(dq['t'].upper())}")
                if dq.get("s"):
                    ev.append(f"Dialogue: 2,{ass_t(ini + .25)},{ass_t(fim)},Apoio,,0,0,0,,"
                              f"{{\\an5\\pos(960,{470 + tam // 2 + 60})\\fad(150,250)}}{escapa(dq['s'])}")
            else:
                x0 = 110
                cab = (f"{{\\an1\\fs{tam}\\fad(100,250)\\move({x0 - 140},860,{x0},860,0,260)"
                       f"\\1c{ass_cor(cor)}\\shad6\\4c&H40240612}}")
                ev.append(f"Dialogue: 2,{ass_t(ini)},{ass_t(fim)},Grande,,0,0,0,,{cab}{escapa(dq['t'].upper())}")
                if dq.get("s"):
                    ev.append(f"Dialogue: 2,{ass_t(ini + .2)},{ass_t(fim)},Apoio,,0,0,0,,"
                              f"{{\\an7\\pos({x0 + 8},878)\\fad(150,250)}}{escapa(dq['s'])}")
    cab = CAB.replace("{ciano}", ass_cor(CIANO)).replace("{rosa}", ass_cor(ROSA))
    saida.write_text(cab + "\n".join(ev) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# montagem
# ---------------------------------------------------------------------------
def montar(ep: dict, trab: Path, saida: Path) -> Path:
    pl_dir = trab / "planos"
    pl_dir.mkdir(parents=True, exist_ok=True)
    lista, inicio, t = [], {}, 0.0
    for c in ep["cenas"]:
        inicio[c["id"]] = t
        c["t_planos"] = tempos_planos(c)
        c["etiquetas"] = []
        for i, (p, (a, b)) in enumerate(zip(c["planos"], c["t_planos"])):
            arq = pl_dir / f"{c['id']}-{i:02d}.mp4"
            # duração em quadros inteiros, acumulando o erro para não descasar do áudio
            n = round((t + b) * FPS) - round((t + a) * FPS)
            print(f"  plano {c['id']}#{i} {p['v']} {n / FPS:.1f}s", flush=True)
            c["etiquetas"].append(render_plano(p, n / FPS, arq, trab, i + len(lista)))
            lista.append(arq)
        t += c["dur"]
    concat = trab / "planos.txt"
    concat.write_text("".join(f"file '{p}'\n" for p in lista))
    mudo = trab / "imagem.mp4"
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", concat, "-c", "copy", mudo)
    # áudio: cenas em sequência + trilha opcional bem baixa
    alista = trab / "audio.txt"
    alista.write_text("".join(f"file '{c['audio']}'\n" for c in ep["cenas"]))
    voz = trab / "voz.wav"
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", alista, "-c", "pcm_s16le", voz)
    ass = trab / "legenda.ass"
    legenda_ass(ep, ass, inicio)
    shutil.copy(ass, saida.with_suffix(".ass"))
    lg = trab / "logo-canto.png"
    l = Image.open(LOGO).convert("RGBA")
    l = l.resize((int(l.width * 46 / l.height), 46), Image.LANCZOS)
    l.save(lg)
    fontes = trab / "fontes"
    fontes.mkdir(exist_ok=True)
    for f in ("f1.ttf", "f2.ttf", "f4.ttf"):
        shutil.copy(FONTES / f, fontes / f)
    trilha = ep.get("trilha")
    entradas = ["-i", mudo, "-i", voz, "-i", lg]
    filtro = (f"[0:v][2:v]overlay=W-w-52:H-h-44:format=auto[v1];"
              f"[v1]subtitles={ass}:fontsdir={fontes}[v]")
    amix = "[1:a]anull[a]"
    if trilha and (RAIZ / trilha).exists():
        entradas += ["-stream_loop", "-1", "-i", RAIZ / trilha]
        amix = "[3:a]volume=0.07[m];[1:a][m]amix=inputs=2:duration=first:normalize=0[a]"
    sh("ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", f"{filtro};{amix}",
       "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", ep.get("preset", "veryfast"), "-crf", "21",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", saida)
    return saida


def capa(ep: dict, saida: Path) -> None:
    cp = ep["capa"]
    base = Image.open(oficial(cp["imagem"])).convert("RGB")
    base = base.resize((1280, int(base.height * 1280 / base.width)), Image.LANCZOS)
    if base.height < 720:
        base = base.resize((int(base.width * 720 / base.height), 720), Image.LANCZOS)
    base = base.crop((0, 0, 1280, 720))
    im = base.convert("RGBA")
    sombra = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sombra)
    for x in range(760):
        a = int(235 * (1 - x / 760) ** 1.2)
        sd.line([(x, 0), (x, 720)], fill=(18, 6, 36, a))
    im.alpha_composite(sombra)
    d = ImageDraw.Draw(im)
    y = 120
    for linha, tam in cp["linhas"]:
        f = fonte(ANTON, tam)
        d.text((52, y + 6), linha.upper(), font=f, fill=(18, 6, 36))
        texto_degrade(im, (46, y), linha.upper(), f)
        y += int(tam * 1.08)
    fe = fonte(ANTON, 44)
    tl = fe.getlength(cp["etiqueta"])
    d.rounded_rectangle([46, y + 16, 46 + tl + 36, y + 84], radius=12, fill=CIANO)
    d.text((64, y + 20), cp["etiqueta"], font=fe, fill=NOITE)
    l = Image.open(LOGO).convert("RGBA")
    l = l.resize((int(l.width * 52 / l.height), 52), Image.LANCZOS)
    im.alpha_composite(l, (46, 40))
    im.convert("RGB").save(saida, quality=92)


def descricao(ep: dict, saida: Path, inicio: dict) -> None:
    linhas = [ep["titulo"], "", ep["descricao"].strip(), "", "Capítulos:"]
    for c in ep["cenas"]:
        if c.get("capitulo"):
            s = int(inicio[c["id"]])
            linhas.append(f"{s // 60}:{s % 60:02d} {c['capitulo']}")
    linhas += ["", "Imagens do jogo: material oficial da Rockstar Games (site e trailer de lançamento de GTA VI).",
               "Fotos reais: Wikimedia Commons, licenças livres:"]
    linhas += [f"- {c}" for c in sorted(set(CREDITOS))]
    linhas += ["", "Site: https://pixelzada.com.br", "Instagram: @pixelzada.br", "", ep.get("tags", "")]
    saida.write_text("\n".join(linhas).strip() + "\n", encoding="utf-8")


def tudo(arq: Path) -> int:
    ep = carregar(arq)
    slug = arq.stem
    trab = RAIZ / "trabalho/narrado" / slug
    trab.mkdir(parents=True, exist_ok=True)
    print("== voz", flush=True)
    voz = narrar(ep, trab)
    print("voz:", voz)
    print("== planos e montagem", flush=True)
    final = trab / f"{slug}.mp4"
    montar(ep, trab, final)
    inicio, t = {}, 0.0
    for c in ep["cenas"]:
        inicio[c["id"]] = t
        t += c["dur"]
    capa(ep, trab / "capa.jpg")
    descricao(ep, trab / "descricao.txt", inicio)
    rel = {"voz": voz, "duracao": round(duracao(final), 1),
           "cenas": [{"id": c["id"], "dur": round(c["dur"], 2),
                      "frases": [[round(a, 2), round(b, 2)] for a, b in c["t_frases"]]} for c in ep["cenas"]]}
    (trab / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1))
    print(json.dumps(rel, ensure_ascii=False)[:1500])
    return 0


def amostras(arq: Path) -> int:
    """Só as artes (mapa, cartão, fundo, capa), sem voz: para conferir a identidade rápido."""
    ep = carregar(arq)
    pasta = RAIZ / "trabalho/narrado" / arq.stem / "amostras"
    pasta.mkdir(parents=True, exist_ok=True)
    fundo_vice().save(pasta / "fundo.jpg", quality=88)
    arte_mapa(None).save(pasta / "mapa.jpg", quality=88)
    arte_mapa("kalaga").save(pasta / "mapa-kalaga.jpg", quality=88)
    arte_cartao("Montanha?", "Ponto mais alto da Flórida: 105 m").save(pasta / "cartao.jpg", quality=88)
    capa(ep, pasta / "capa.jpg")
    return 0


if __name__ == "__main__":
    cmd, arq = sys.argv[1], Path(sys.argv[2])
    sys.exit({"tudo": tudo, "amostras": amostras}[cmd](arq))
