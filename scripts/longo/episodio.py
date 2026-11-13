"""Vídeo longo de lista (série "TOP Pixelzada") + cortes curtos + capas.

Plano: https://claude.ai/artifact/9HAZy4Y7riwAwxPEMug8TN (Diego, 13/11/2026).

Um episódio é um JSON em scripts/longo/episodios/ (gancho, abertura, 10 itens, fechamento).
Este script, no GitHub Actions:

  1. banco   pega clipes do jogo mais vistos da Twitch (API oficial, chave do motor),
             corta a câmera do streamer (scripts/social/rosto.py) e guarda em trabalho/clipes/
  2. voz     narra cada trecho: voz do Google AI Studio (Gemini TTS, secret GEMINI_API_KEY);
             sem a chave, usa a voz reserva da Microsoft (edge-tts)
  3. montar  monta o vídeo longo 16:9, o corte curto 9:16 do item nº 1, 3 capas e a descrição
             com capítulos, em previas/longo/<slug>/

    python -m scripts.longo.episodio tudo scripts/longo/episodios/<slug>.json [--altura 720]

Nada aqui publica nada: a saída é só prévia para o Diego avaliar.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageStat

RAIZ = Path(__file__).resolve().parents[2]
AQUI = Path(__file__).resolve().parent
FONTES = RAIZ / "scripts/social/gerador/fonts"
ANTON = str(FONTES / "f1.ttf")
ARCHIVO = str(FONTES / "f2.ttf")
PIXEL = str(FONTES / "f4.ttf")
LOGO = AQUI / "logo.png"

LIMA = (198, 255, 26)
NOITE = (11, 10, 16)
CARVAO = (23, 21, 31)
BRANCO = (255, 255, 255)
CINZA = (167, 163, 181)
MAGENTA = (255, 61, 139)

VOZ_GEMINI = os.environ.get("VOZ_GEMINI", "Charon")
MODELOS_TTS = [m for m in [os.environ.get("TTS_MODELO"), "gemini-2.5-flash-preview-tts",
                           "gemini-3.1-flash-tts-preview", "gemini-2.5-pro-preview-tts"] if m]
ESTILO = ("Narre em português do Brasil, como um apresentador de canal de games no YouTube: "
          "animado, confiante, ritmo rápido mas claro, sem exagero. Leia exatamente este texto:\n\n")
VOZ_EDGE = os.environ.get("VOZ_EDGE", "pt-BR-AntonioNeural")


def sh(*args, **kw) -> subprocess.CompletedProcess:
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True, **kw)
    if r.returncode:
        raise RuntimeError(f"{args[0]} falhou: {(r.stderr or r.stdout)[-600:]}")
    return r


def duracao(arq: Path) -> float:
    r = sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", arq)
    return float(r.stdout.strip() or 0)


def fonte(caminho: str, tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(caminho, max(8, int(tam)))


def quebrar(texto: str, f: ImageFont.FreeTypeFont, largura: int) -> list[str]:
    linhas, atual = [], ""
    texto = re.sub(r"GTA (\d)", r"GTA§\1", texto)  # "GTA 6" nunca quebra
    for p in [x.replace("§", " ") for x in texto.split()]:
        teste = f"{atual} {p}".strip()
        if f.getlength(teste) <= largura or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    # nunca deixar o "6" de "GTA 6" sozinho no começo da linha
    for i in range(1, len(linhas)):
        if re.match(r"^\d\b", linhas[i]) and linhas[i - 1].endswith("GTA"):
            linhas[i - 1] = linhas[i - 1][:-3].rstrip()
            linhas[i] = "GTA " + linhas[i]
    return [l for l in linhas if l]


def segmentos(ep: dict) -> list[dict]:
    seg = [{"id": "gancho", "tipo": "gancho", **ep["gancho"]},
           {"id": "abertura", "tipo": "abertura", **ep["abertura"]}]
    for it in ep["itens"]:
        seg.append({"id": f"item{it['numero']:02d}", "tipo": "item", **it})
    seg.append({"id": "fechamento", "tipo": "fechamento", **ep["fechamento"]})
    return seg


# ---------------------------------------------------------------------------
# 1. Banco de imagens: clipes da Twitch sem o rosto do streamer
# ---------------------------------------------------------------------------
def banco(ep: dict, trab: Path, quantos: int = 12) -> list[dict]:
    pasta = trab / "clipes"
    pasta.mkdir(parents=True, exist_ok=True)
    feitos = sorted(pasta.glob("*.mp4"))
    info_arq = pasta / "clipes.json"
    if len(feitos) >= quantos and info_arq.exists():
        return json.loads(info_arq.read_text())
    sys.path.insert(0, str(RAIZ))
    from scripts.social import lives, rosto  # noqa: E402

    tw = lives.Twitch()
    gid = tw.jogo(ep.get("jogo_twitch", "Grand Theft Auto V"))
    if not gid:
        raise RuntimeError("a Twitch não achou o jogo")
    desde = datetime.now(timezone.utc) - timedelta(days=int(ep.get("dias_clipes", 7)))
    brutos = []
    cursor = None
    for _ in range(3):  # até 300 clipes
        params = {"game_id": gid, "started_at": lives._rfc(desde), "first": 100}
        if cursor:
            params["after"] = cursor
        d = tw.get("clips", **params)
        brutos += d.get("data", [])
        cursor = (d.get("pagination") or {}).get("cursor")
        if not cursor:
            break
    idiomas = {"pt": 3, "pt-br": 3, "en": 2, "es": 1}

    def nota(c):
        return (idiomas.get((c.get("language") or "").lower(), 0), c.get("view_count", 0))

    bons = [c for c in brutos if 20 <= (c.get("duration") or 0) <= 62]
    bons.sort(key=nota, reverse=True)
    print(f"{len(brutos)} clipes na Twitch; {len(bons)} com 20-60 s")
    usados, por_canal = [], {}
    for c in bons:
        if len(usados) >= quantos:
            break
        canal = c["broadcaster_name"]
        if por_canal.get(canal, 0) >= 2:  # variedade: no máximo 2 por canal
            continue
        destino = pasta / f"{len(usados) + 1:02d}.mp4"
        res = lives.baixar_e_limpar({"link": c["url"]}, destino)
        print(f"  {canal} ({c.get('language')}, {c.get('view_count')} views): {res.get('motivo')}")
        if not res.get("ok"):
            continue
        por_canal[canal] = por_canal.get(canal, 0) + 1
        usados.append({"arquivo": destino.name, "canal": canal, "link": c["url"], "titulo": c.get("title"),
                       "idioma": c.get("language"), "views": c.get("view_count"), "corte": res.get("corte")})
    info_arq.write_text(json.dumps(usados, ensure_ascii=False, indent=2))
    if not usados:
        raise RuntimeError("nenhum clipe aproveitável")
    return usados


# ---------------------------------------------------------------------------
# 2. Voz
# ---------------------------------------------------------------------------
def voz_gemini(texto: str, saida: Path) -> str:
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave:
        raise RuntimeError("sem GEMINI_API_KEY")
    corpo = {"contents": [{"parts": [{"text": ESTILO + texto}]}],
             "generationConfig": {"responseModalities": ["AUDIO"],
                                  "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOZ_GEMINI}}}}}
    erros = []
    for modelo in MODELOS_TTS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
        req = urllib.request.Request(url, data=json.dumps(corpo).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": chave})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            parte = d["candidates"][0]["content"]["parts"][0]["inlineData"]
            pcm = base64.b64decode(parte["data"])
            taxa = 24000
            m = re.search(r"rate=(\d+)", parte.get("mimeType", ""))
            if m:
                taxa = int(m.group(1))
            with wave.open(str(saida), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(taxa)
                w.writeframes(pcm)
            return f"Google Gemini TTS ({modelo}, voz {VOZ_GEMINI})"
        except urllib.error.HTTPError as e:
            erros.append(f"{modelo}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:200]}")
        except Exception as e:  # noqa: BLE001
            erros.append(f"{modelo}: {e}")
    raise RuntimeError("; ".join(erros))


def voz_edge(texto: str, saida: Path) -> str:
    mp3 = saida.with_suffix(".mp3")
    sh("edge-tts", "--voice", VOZ_EDGE, "--rate", "+8%", "--text", texto, "--write-media", mp3)
    sh("ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", "24000", "-ac", "1", saida)
    mp3.unlink(missing_ok=True)
    return f"Microsoft Edge TTS ({VOZ_EDGE}), reserva"


def narrar(segs: list[dict], trab: Path) -> str:
    pasta = trab / "voz"
    pasta.mkdir(parents=True, exist_ok=True)
    usadas = set()
    for s in segs:
        wav = pasta / f"{s['id']}.wav"
        if not wav.exists() and os.environ.get("VOZ_TESTE"):
            seg = max(2.0, len(s["texto"].split()) / 2.7)
            sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=220:duration={seg:.2f}",
               "-af", "volume=0.05", "-ar", "24000", "-ac", "1", wav)
            usadas.add("teste (sem voz)")
        if not wav.exists():
            try:
                usadas.add(voz_gemini(s["texto"], wav))
            except Exception as e:  # noqa: BLE001
                print(f"  voz do Google indisponível em {s['id']}: {e}")
                usadas.add(voz_edge(s["texto"], wav))
        # respiro de 0,35 s no fim de cada trecho
        final = pasta / f"{s['id']}-final.wav"
        sh("ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af", "apad=pad_dur=0.35,loudnorm=I=-16:TP=-1.5",
           "-ar", "48000", "-ac", "2", final)
        s["audio"] = final
        s["dur"] = duracao(final)
        print(f"  {s['id']}: {s['dur']:.1f} s")
    return " + ".join(sorted(usadas)) or "?"


# ---------------------------------------------------------------------------
# 3. Artes (Pillow) e montagem (ffmpeg)
# ---------------------------------------------------------------------------
class Tela:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.k = w / 1920 if w > h else w / 1080

    def px(self, v: float) -> int:
        return int(round(v * self.k))


def logo(alt: int) -> Image.Image:
    im = Image.open(LOGO).convert("RGBA")
    return im.resize((int(im.width * alt / im.height), alt), Image.LANCZOS)


def pilula(d: ImageDraw.ImageDraw, x: int, y: int, texto: str, f, cor_fundo, cor_texto, pad: int) -> tuple[int, int]:
    larg = int(f.getlength(texto)) + 2 * pad
    asc, desc = f.getmetrics()
    alt = asc + desc + pad
    d.rectangle([x, y, x + larg, y + alt], fill=cor_fundo)
    d.text((x + pad, y + pad // 2), texto, font=f, fill=cor_texto)
    return larg, alt


def arte_item(t: Tela, ep: dict, s: dict, total: int) -> Image.Image:
    im = Image.new("RGBA", (t.w, t.h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # degradê escuro embaixo para o texto ler bem
    for i in range(t.px(420)):
        a = int(215 * (i / t.px(420)) ** 1.4)
        y = t.h - t.px(420) + i
        d.line([(0, y), (t.w, y)], fill=(11, 10, 16, a))
    m = t.px(72)
    fn = fonte(ANTON, t.px(250))
    num = f"#{s['numero']}"
    d.text((m, t.h - t.px(330)), num, font=fn, fill=LIMA, stroke_width=t.px(4), stroke_fill=NOITE)
    xn = m + int(fn.getlength(num)) + t.px(40)
    ft = fonte(ANTON, t.px(92))
    linhas = quebrar(s["nome"].upper(), ft, t.w - xn - m)
    y = t.h - t.px(300)
    for l in linhas[:2]:
        d.text((xn, y), l, font=ft, fill=BRANCO)
        y += t.px(102)
    fp = fonte(ANTON, t.px(54))
    pilula(d, xn, y + t.px(14), s["destaque"], fp, LIMA, NOITE, t.px(18))
    # logo e série no topo
    lg = logo(t.px(58))
    im.alpha_composite(lg, (m, t.px(48)))
    fs = fonte(PIXEL, t.px(26))
    serie = f"{ep['serie'].upper()} · {ep['capa']['linha1']} {ep['capa']['linha2']}"
    d.text((t.w - m - fs.getlength(serie), t.px(62)), serie, font=fs, fill=BRANCO,
           stroke_width=t.px(3), stroke_fill=NOITE)
    # barra de progresso: 10 casas, a atual acesa
    casa, vao = t.px(52), t.px(10)
    x0 = t.w - m - total * casa - (total - 1) * vao
    pos = total - s["numero"]
    for i in range(total):
        cor = LIMA if i == pos else ((255, 255, 255, 200) if i < pos else (255, 255, 255, 70))
        d.rectangle([x0 + i * (casa + vao), t.h - t.px(40), x0 + i * (casa + vao) + casa, t.h - t.px(30)], fill=cor)
    return im


def arte_cartao_numero(t: Tela, s: dict) -> Image.Image:
    """Cartão de entrada do item: número gigante no meio (primeiros ~1,3 s)."""
    im = Image.new("RGBA", (t.w, t.h), (11, 10, 16, 150))
    d = ImageDraw.Draw(im)
    fn = fonte(ANTON, t.px(520))
    num = str(s["numero"])
    bb = d.textbbox((0, 0), num, font=fn)
    d.text(((t.w - (bb[2] - bb[0])) / 2 - bb[0], (t.h - (bb[3] - bb[1])) / 2 - bb[1] - t.px(40)), num, font=fn,
           fill=LIMA, stroke_width=t.px(8), stroke_fill=NOITE)
    ft = fonte(ANTON, t.px(84))
    nome = s["nome"].upper()
    d.text(((t.w - ft.getlength(nome)) / 2, t.h / 2 + t.px(250)), nome, font=ft, fill=BRANCO,
           stroke_width=t.px(4), stroke_fill=NOITE)
    return im


def arte_texto_central(t: Tela, titulo: str, apoio: str, com_logo: bool = True) -> Image.Image:
    im = Image.new("RGBA", (t.w, t.h), (11, 10, 16, 120))
    d = ImageDraw.Draw(im)
    y = t.h * 0.30
    if com_logo:
        lg = logo(t.px(120))
        im.alpha_composite(lg, (int((t.w - lg.width) / 2), int(t.h * 0.16)))
        y = t.h * 0.42
    ft = fonte(ANTON, t.px(130))
    for l in quebrar(titulo.upper(), ft, t.w - t.px(240)):
        d.text(((t.w - ft.getlength(l)) / 2, y), l, font=ft, fill=BRANCO, stroke_width=t.px(5), stroke_fill=NOITE)
        y += t.px(150)
    fa = fonte(ARCHIVO, t.px(56))
    for l in quebrar(apoio, fa, t.w - t.px(300)):
        d.text(((t.w - fa.getlength(l)) / 2, y + t.px(20)), l, font=fa, fill=LIMA, stroke_width=t.px(3),
               stroke_fill=NOITE)
        y += t.px(70)
    return im


def pedacos_legenda(texto: str, dur: float, por: int = 4) -> list[tuple[float, float, str]]:
    """Legenda aproximada: blocos de ~4 palavras, tempo proporcional ao tamanho."""
    p = texto.split()
    blocos = [" ".join(p[i:i + por]) for i in range(0, len(p), por)]
    total = sum(len(b) + 2 for b in blocos)
    t, util, out = 0.0, max(0.5, dur - 0.35), []
    for b in blocos:
        dt = util * (len(b) + 2) / total
        out.append((t, t + dt, b))
        t += dt
    return out


def arte_legenda(t: Tela, texto: str, y_frac: float) -> Image.Image:
    im = Image.new("RGBA", (t.w, t.h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = fonte(ANTON, t.px(84))
    y = int(t.h * y_frac)
    for l in quebrar(texto.upper(), f, t.w - t.px(140)):
        d.text(((t.w - f.getlength(l)) / 2, y), l, font=f, fill=BRANCO, stroke_width=t.px(7), stroke_fill=NOITE)
        y += t.px(96)
    return im


def fundo_cmd(clipe: Path, dur: float, w: int, h: int, desfoque: bool = False) -> list[str]:
    """Entrada de vídeo em loop, cortada para cobrir a tela com zoom leve (tira HUD e marca d'água das bordas)."""
    ini = 0.0
    try:
        dc = duracao(clipe)
        if dc > dur + 2:
            ini = random.uniform(0, dc - dur - 1)
    except Exception:  # noqa: BLE001
        pass
    vf = (f"scale={int(w * 1.14)}:{int(h * 1.14)}:force_original_aspect_ratio=increase,"
          f"crop={w}:{h},setsar=1,fps=30")
    if desfoque:
        vf += ",gblur=sigma=18,eq=brightness=-0.12"
    else:
        vf += ",eq=brightness=-0.04:saturation=1.12"
    return ["-ss", f"{ini:.2f}", "-stream_loop", "-1", "-i", str(clipe)], vf


def render_segmento(t: Tela, s: dict, clipe: Path, artes: list[tuple[Path, float, float | None]], saida: Path,
                    desfoque: bool = False):
    entrada, vf = fundo_cmd(clipe, s["dur"], t.w, t.h, desfoque)
    args = ["ffmpeg", "-y", "-loglevel", "error", *entrada, "-i", str(s["audio"])]
    for arq, _, _ in artes:
        args += ["-loop", "1", "-i", str(arq)]
    filtro = f"[0:v]{vf}[v0]"
    ult = "v0"
    for i, (_, de, ate) in enumerate(artes):
        quando = f"between(t,{de:.2f},{ate:.2f})" if ate is not None else f"gte(t,{de:.2f})"
        filtro += f";[{ult}][{i + 2}:v]overlay=0:0:enable='{quando}'[v{i + 1}]"
        ult = f"v{i + 1}"
    args += ["-filter_complex", filtro, "-map", f"[{ult}]", "-map", "1:a", "-t", f"{s['dur']:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-maxrate", "1600k", "-bufsize", "3200k",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", str(saida)]
    sh(*args)


def montar_longo(ep: dict, segs: list[dict], clipes: list[Path], trab: Path, saida: Path, altura: int) -> list[str]:
    t = Tela(int(altura * 16 / 9) // 2 * 2, altura)
    pasta = trab / "segmentos"
    pasta.mkdir(parents=True, exist_ok=True)
    partes, capitulos, relogio = [], [], 0.0
    total = len(ep["itens"])
    for i, s in enumerate(segs):
        clipe = clipes[i % len(clipes)]
        artes = []
        if s["tipo"] == "gancho":
            a = pasta / f"{s['id']}-a.png"
            arte_texto_central(t, f"{ep['capa']['linha1']} {ep['capa']['linha2']}", ep["capa"]["apoio"],
                               com_logo=False).save(a)
            leg = []
            for j, (de, ate, txt) in enumerate(pedacos_legenda(s["texto"], s["dur"])):
                arq = pasta / f"{s['id']}-leg{j:02d}.png"
                arte_legenda(t, txt, 0.78).save(arq)
                leg.append((arq, de, ate))
            artes = [(a, s["dur"] - 3.2, None)] + [x for x in leg if x[1] < s["dur"] - 3.2]
        elif s["tipo"] == "abertura":
            a = pasta / f"{s['id']}.png"
            arte_texto_central(t, ep["serie"], "segue o canal: vídeo novo toda semana").save(a)
            artes = [(a, 0, None)]
        elif s["tipo"] == "item":
            c = pasta / f"{s['id']}-cartao.png"
            p = pasta / f"{s['id']}-painel.png"
            arte_cartao_numero(t, s).save(c)
            arte_item(t, ep, s, total).save(p)
            artes = [(c, 0, 1.4), (p, 1.4, None)]
        else:
            a = pasta / f"{s['id']}.png"
            arte_texto_central(t, "Qual número te surpreendeu?", "comenta aí embaixo · segue a Pixelzada").save(a)
            artes = [(a, 0, None)]
        arq = pasta / f"{i:02d}-{s['id']}.mp4"
        render_segmento(t, s, clipe, artes, arq, desfoque=s["tipo"] in ("abertura", "fechamento"))
        partes.append(arq)
        if s["tipo"] in ("gancho", "item", "fechamento"):
            nome = {"gancho": "Introdução", "fechamento": "Conclusão"}.get(s["tipo"])
            nome = nome or f"#{s['numero']} {s['nome']}"
            capitulos.append(f"{int(relogio // 60)}:{int(relogio % 60):02d} {nome}")
        relogio += s["dur"]
        print(f"  segmento {s['id']} pronto ({relogio:.0f} s acumulados)")
    lista = pasta / "lista.txt"
    lista.write_text("".join(f"file '{p.resolve()}'\n" for p in partes))
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lista, "-c", "copy",
       "-movflags", "+faststart", saida)
    return capitulos


def montar_curto(ep: dict, s: dict, clipe: Path, trab: Path, saida: Path, altura: int):
    """Corte 9:16 de um item: título em cima, vídeo no meio, legenda grande, chamada embaixo."""
    h = altura
    w = int(h * 9 / 16) // 2 * 2
    t = Tela(w, h)
    pasta = trab / "curto"
    pasta.mkdir(parents=True, exist_ok=True)
    fundo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(fundo)
    lg = logo(t.px(70))
    fundo.alpha_composite(lg, ((w - lg.width) // 2, t.px(110)))
    ft = fonte(ANTON, t.px(92))
    y = t.px(230)
    titulo = f"{ep['capa']['linha1']} {ep['capa']['linha2']}: #{s['numero']}"
    for l in quebrar(titulo.upper(), ft, w - t.px(120)):
        d.text(((w - ft.getlength(l)) / 2, y), l, font=ft, fill=BRANCO, stroke_width=t.px(5), stroke_fill=NOITE)
        y += t.px(104)
    fp = fonte(ANTON, t.px(70))
    larg = fp.getlength(s["destaque"]) + t.px(40)
    pilula(d, int((w - larg) / 2), t.px(1310), s["destaque"], fp, LIMA, NOITE, t.px(20))
    fc = fonte(ARCHIVO, t.px(46))
    yc = t.px(1600)
    for l in quebrar("Essa é a página pra seguir e acompanhar o GTA 6", fc, w - t.px(160)):
        d.text(((w - fc.getlength(l)) / 2, yc), l, font=fc, fill=BRANCO, stroke_width=t.px(3), stroke_fill=NOITE)
        yc += t.px(60)
    base = pasta / "base.png"
    fundo.save(base)
    leg = []
    for j, (de, ate, txt) in enumerate(pedacos_legenda(s["texto"], s["dur"], por=3)):
        arq = pasta / f"leg{j:02d}.png"
        arte_legenda(t, txt, 0.585).save(arq)
        leg.append((arq, de, ate))
    # fundo: o mesmo clipe desfocado; no meio, o clipe 16:9 grande
    jw = w - t.px(40)
    jh = int(jw * 9 / 16) // 2 * 2
    jy = t.px(520)
    ini = 0.0
    try:
        dc = duracao(clipe)
        if dc > s["dur"] + 2:
            ini = random.uniform(0, dc - s["dur"] - 1)
    except Exception:  # noqa: BLE001
        pass
    args = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ini:.2f}", "-stream_loop", "-1", "-i", str(clipe),
            "-i", str(s["audio"]), "-loop", "1", "-i", str(base)]
    for arq, _, _ in leg:
        args += ["-loop", "1", "-i", str(arq)]
    filtro = (f"[0:v]fps=30,split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
              f"gblur=sigma=24,eq=brightness=-0.25[fundo];"
              f"[b]scale={int(jw * 1.12)}:{int(jh * 1.12)}:force_original_aspect_ratio=increase,crop={jw}:{jh}[meio];"
              f"[fundo][meio]overlay={(w - jw) // 2}:{jy}[c0];[c0][2:v]overlay=0:0[c1]")
    ult = "c1"
    for i, (_, de, ate) in enumerate(leg):
        filtro += f";[{ult}][{i + 3}:v]overlay=0:0:enable='between(t,{de:.2f},{ate:.2f})'[l{i}]"
        ult = f"l{i}"
    args += ["-filter_complex", filtro, "-map", f"[{ult}]", "-map", "1:a", "-t", f"{s['dur']:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(saida)]
    sh(*args)


def melhores_quadros(clipes: list[Path], trab: Path, n: int = 3) -> list[Path]:
    """Tira alguns quadros de cada clipe e fica com os mais coloridos e nítidos."""
    pasta = trab / "quadros"
    pasta.mkdir(parents=True, exist_ok=True)
    notas = []
    for c in clipes:
        try:
            dc = duracao(c)
        except Exception:  # noqa: BLE001
            continue
        for k, frac in enumerate((0.25, 0.5, 0.75)):
            q = pasta / f"{c.stem}-{k}.jpg"
            try:
                sh("ffmpeg", "-y", "-loglevel", "error", "-ss", f"{dc * frac:.2f}", "-i", c, "-frames:v", "1",
                   "-q:v", "2", q)
            except RuntimeError:
                continue
            im = Image.open(q).convert("RGB")
            st = ImageStat.Stat(im.convert("HSV") if hasattr(im, "convert") else im)
            sat = st.mean[1]
            nit = ImageStat.Stat(im.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]
            notas.append((sat * 0.6 + nit * 4, q, c.stem))
    notas.sort(reverse=True)
    escolhidos, vistos = [], set()
    for _, q, cl in notas:
        if cl in vistos:
            continue
        vistos.add(cl)
        escolhidos.append(q)
        if len(escolhidos) >= n:
            break
    return escolhidos


def preparar_quadro(q: Path, w: int, h: int) -> Image.Image:
    im = Image.open(q).convert("RGB")
    esc = max(w / im.width, h / im.height) * 1.12
    im = im.resize((int(im.width * esc), int(im.height * esc)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    im = im.crop((x, y, x + w, y + h))
    im = ImageEnhance.Color(im).enhance(1.35)
    im = ImageEnhance.Contrast(im).enhance(1.15)
    return im.convert("RGBA")


def capas(ep: dict, quadros: list[Path], pasta: Path) -> list[Path]:
    w, h = 1280, 720
    t = Tela(w, h)
    c = ep["capa"]
    itens = {it["numero"]: it for it in ep["itens"]}
    saidas = []
    for v, q in zip("abc", quadros + quadros[:3]):
        im = preparar_quadro(q, w, h)
        d = ImageDraw.Draw(im)
        if v == "a":  # número gigante à esquerda + título
            grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            gd = ImageDraw.Draw(grad)
            for x in range(int(w * 0.68)):
                a = int(235 * (1 - x / (w * 0.68)) ** 0.8)
                gd.line([(x, 0), (x, h)], fill=(11, 10, 16, a))
            im.alpha_composite(grad)
            d = ImageDraw.Draw(im)
            fn = fonte(ANTON, t.px(760))
            d.text((t.px(40), t.px(-60)), c["numero"], font=fn, fill=LIMA, stroke_width=t.px(10), stroke_fill=NOITE)
            ft = fonte(ANTON, t.px(170))
            d.text((t.px(560), t.px(180)), c["linha1"], font=ft, fill=BRANCO, stroke_width=t.px(8),
                   stroke_fill=NOITE)
            d.text((t.px(560), t.px(370)), c["linha2"], font=ft, fill=BRANCO, stroke_width=t.px(8),
                   stroke_fill=NOITE)
            fa = fonte(ANTON, t.px(66))
            pilula(d, t.px(566), t.px(600), c["apoio"].upper(), fa, LIMA, NOITE, t.px(18))
        elif v == "b":  # o maior número do episódio estampado + círculo
            top = itens[1]
            faixa = Image.new("RGBA", (w, h), (11, 10, 16, 0))
            fd = ImageDraw.Draw(faixa)
            fd.rectangle([0, int(h * 0.56), w, h], fill=(11, 10, 16, 215))
            im.alpha_composite(faixa)
            d = ImageDraw.Draw(im)
            ft = fonte(ANTON, t.px(250))
            txt = top["destaque"]
            while ft.getlength(txt) > w - t.px(120) and ft.size > 40:
                ft = fonte(ANTON, ft.size - 6)
            d.text(((w - ft.getlength(txt)) / 2, h * 0.58), txt, font=ft, fill=LIMA, stroke_width=t.px(8),
                   stroke_fill=NOITE)
            fs = fonte(ANTON, t.px(96))
            sub = f"{c['linha1']} {c['linha2']}"
            pilula(d, t.px(70), t.px(70), sub, fs, BRANCO, NOITE, t.px(22))
        else:  # "o GTA 6 consegue?" lado a lado
            grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            gd = ImageDraw.Draw(grad)
            for x in range(w):
                a = int(225 * max(0.0, (x - w * 0.35) / (w * 0.65)) ** 0.9)
                gd.line([(x, 0), (x, h)], fill=(11, 10, 16, a))
            im.alpha_composite(grad)
            d = ImageDraw.Draw(im)
            ft = fonte(ANTON, t.px(150))
            y = t.px(120)
            for l in ["O GTA 6", "BATE", "ISSO?"]:
                d.text((w - t.px(70) - ft.getlength(l), y), l, font=ft, fill=BRANCO if l != "BATE" else LIMA,
                       stroke_width=t.px(8), stroke_fill=NOITE)
                y += t.px(175)
            fa = fonte(ANTON, t.px(70))
            larg = fa.getlength(c["linha2"]) + t.px(36)
            pilula(d, int(w - t.px(70) - larg), y + t.px(30), c["linha2"], fa, LIMA, NOITE, t.px(18))
        lg = logo(t.px(62))
        im.alpha_composite(lg, (w - lg.width - t.px(40), h - lg.height - t.px(36)) if v != "c"
                           else (t.px(40), h - lg.height - t.px(36)))
        arq = pasta / f"capa-{v}.jpg"
        im.convert("RGB").save(arq, quality=90)
        saidas.append(arq)
    return saidas


def tudo(ep_arq: Path, altura: int, so_teste: bool = False) -> int:
    ep = json.loads(ep_arq.read_text())
    slug = ep["slug"]
    trab = RAIZ / "trabalho" / slug
    saida = RAIZ / "previas" / "longo" / slug
    saida.mkdir(parents=True, exist_ok=True)
    trab.mkdir(parents=True, exist_ok=True)
    print("1/3 banco de imagens")
    if so_teste:
        clipes_info = [{"arquivo": p.name} for p in sorted((trab / "clipes").glob("*.mp4"))]
    else:
        clipes_info = banco(ep, trab)
    clipes = [trab / "clipes" / c["arquivo"] for c in clipes_info]
    print("2/3 voz")
    segs = segmentos(ep)
    voz_usada = narrar(segs, trab)
    print("3/3 montagem")
    random.seed(slug)
    capitulos = montar_longo(ep, segs, clipes, trab, saida / "video-longo.mp4", altura)
    um = next(s for s in segs if s["tipo"] == "item" and s["numero"] == 1)
    montar_curto(ep, um, clipes[0], trab, saida / "curto-item-1.mp4", int(altura * 16 / 9))
    quadros = melhores_quadros(clipes, trab)
    capas(ep, quadros, saida)
    desc = [ep["titulo"], "",
            "Os 10 números mais absurdos do GTA 5 e o que o GTA 6 vai ter que bater a partir de 19/11.",
            "Comenta qual número te surpreendeu mais!", "", "Capítulos:", *capitulos, "",
            "Imagens: gameplay de GTA 5 (clipes públicos da Twitch, sem rosto de streamer).",
            "A Pixelzada não tem ligação com a Rockstar Games.", "", "#GTA5 #GTA6 #Pixelzada"]
    (saida / "descricao.txt").write_text("\n".join(desc) + "\n")
    rel = {"slug": slug, "gerado_em": datetime.now(timezone.utc).isoformat(), "voz": voz_usada,
           "duracao_s": round(duracao(saida / "video-longo.mp4"), 1), "altura": altura,
           "clipes": clipes_info, "capitulos": capitulos}
    (saida / "relatorio.json").write_text(json.dumps(rel, ensure_ascii=False, indent=2))
    print(json.dumps(rel, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("acao", choices=["tudo", "teste-local"])
    ap.add_argument("episodio")
    ap.add_argument("--altura", type=int, default=720)
    a = ap.parse_args(argv)
    return tudo(Path(a.episodio), a.altura, so_teste=a.acao == "teste-local")


if __name__ == "__main__":
    sys.exit(main())
