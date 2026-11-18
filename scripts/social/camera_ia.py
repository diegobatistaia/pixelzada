"""Segunda barreira contra o rosto do streamer (Diego, 10/11: só a imagem do jogo).
Também descarta clipe que é só cutscene (política da Rockstar) ou menu/carregamento (18/11).

O detector de rostos do OpenCV (rosto.py) deixou passar câmeras no ensaio de 17/11 (streamer
olhando para baixo, rosto de lado, câmera pequena). Aqui a checagem é feita pelo Gemini
(segredo GEMINI_API_KEY): 3 quadros do clipe vão para o modelo, que diz se há câmera/rosto de
pessoa real e onde fica (caixa). Se houver, o clipe é cortado fora da caixa (rosto.melhor_corte)
e conferido de novo. Na dúvida (sem chave, erro, câmera no meio da tela) o clipe é DESCARTADO.

    python -m scripts.social.camera_ia ENTRADA.mp4 SAIDA.mp4
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
from pathlib import Path

from . import rosto
from . import seguranca as SEG

PROMPT = """Você confere clipes de lives de videogame (GTA) para um perfil que só pode mostrar a
imagem do JOGO. É proibido aparecer qualquer pessoa REAL: a câmera (webcam/facecam) do
streamer, mesmo pequena, no canto, de lado, olhando para baixo, de costas, só um pedaço do
corpo/mão, ou com fundo removido (chroma key). Personagens do jogo (gráficos 3D) NÃO contam.

Diga também o que o clipe mostra (conteudo):
- "jogo": gameplay de verdade (personagem andando, dirigindo, atirando, mapa aberto), mesmo com HUD;
- "cutscene": cena de cinema/história do jogo sem controle do jogador (barras pretas, câmera de
  filme, diálogo da história) na MAIOR parte dos quadros;
- "menu": menus, configurações, tela de carregamento, arte de loading, tela preta, notificações
  do console, logo/créditos na maior parte dos quadros.

Você recebe 3 quadros do mesmo clipe. Responda SÓ um JSON:
{"pessoa_real": true|false, "caixas": [[ymin, xmin, ymax, xmax], ...], "conteudo": "jogo"|"cutscene"|"menu", "motivo": "frase curta"}

caixas: uma por câmera/pessoa real, em coordenadas de 0 a 1000 do quadro (iguais nos 3
quadros), cobrindo a moldura inteira da câmera com folga. Lista vazia se pessoa_real=false.
Na dúvida, responda pessoa_real=true."""

FOLGA = 30  # (de 1000) a mais em cada lado da caixa


def _quadros(video: Path, pasta: Path) -> list[Path]:
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ff or not fp:
        return []
    try:
        dur = float(subprocess.check_output([fp, "-v", "error", "-show_entries", "format=duration",
                                             "-of", "csv=p=0", str(video)], text=True).strip() or 0)
    except (subprocess.CalledProcessError, ValueError):
        return []
    saida = []
    for n, f in enumerate((0.2, 0.5, 0.8)):
        q = pasta / f"q{n}.jpg"
        subprocess.run([ff, "-v", "error", "-y", "-ss", f"{max(0.1, dur * f):.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "4", str(q)], capture_output=True)
        if q.exists():
            saida.append(q)
    return saida


def _modelo() -> str:
    return os.environ.get("MODELO_GEMINI_CAMERA") or "gemini-flash-latest"


def perguntar(video: Path) -> dict:
    """{"pessoa_real": bool|None, "caixas": [...], "motivo": str}. None = não deu para saber."""
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave:
        return {"pessoa_real": None, "caixas": [], "motivo": "sem GEMINI_API_KEY"}
    with tempfile.TemporaryDirectory() as tmp:
        qs = _quadros(video, Path(tmp))
        if not qs:
            return {"pessoa_real": None, "caixas": [], "motivo": "não deu para tirar quadros"}
        partes = [{"text": "Há pessoa real/câmera do streamer nestes quadros?"}]
        partes += [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(q.read_bytes()).decode()}}
                   for q in qs]
    corpo = {"systemInstruction": {"parts": [{"text": PROMPT}]},
             "contents": [{"role": "user", "parts": partes}],
             "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    modelos = [_modelo()]
    if SEG._modelo_gemini() not in modelos:
        modelos.append(SEG._modelo_gemini())
    ultimo = "Gemini sem resposta"
    for modelo in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
        for tentativa in range(2):
            try:
                dado = json.loads(SEG._post(url, corpo, {"x-goog-api-key": chave}, timeout=int(os.environ.get("CAMERA_IA_TIMEOUT", "50"))))
                cand = (dado.get("candidates") or [{}])[0]
                txt = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
                j = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
                caixas = [[int(v) for v in c][:4] for c in (j.get("caixas") or []) if len(c) >= 4]
                return {"pessoa_real": bool(j.get("pessoa_real")), "caixas": caixas,
                        "conteudo": str(j.get("conteudo") or "jogo").lower(),
                        "motivo": str(j.get("motivo", ""))[:160], "modelo": modelo}
            except urllib.error.HTTPError as e:
                ultimo = f"Gemini {modelo} HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:120]}"
                if e.code in (429, 500, 503) and tentativa < 1:
                    time.sleep(10)
                    continue
                break
            except Exception as e:
                ultimo = f"Gemini {modelo}: {str(e)[:120]}"
                break
    return {"pessoa_real": None, "caixas": [], "motivo": ultimo}


def _tamanho(video: Path) -> tuple[int, int]:
    s = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=width,height", "-of", "csv=p=0:s=x", str(video)], text=True).strip()
    w, h = s.split("x")[:2]
    return int(w), int(h)


def limpar(video: Path) -> dict:
    """Confere (e se der, corta) o vídeo NO LUGAR. {"ok": bool, "motivo": str}."""
    r = perguntar(video)
    if r["pessoa_real"] is None:
        return {"ok": False, "motivo": f"checagem de câmera indisponível ({r['motivo']}): descartado por segurança"}
    if r.get("conteudo") in ("cutscene", "menu"):
        # Rockstar derruba cutscene isolada; menu/carregamento não rende Reel
        return {"ok": False, "motivo": f"IA: {r['conteudo']}, não é gameplay ({r['motivo']})"}
    if not r["pessoa_real"]:
        return {"ok": True, "motivo": f"IA: sem pessoa real ({r['motivo']})"}
    if not r["caixas"]:
        return {"ok": False, "motivo": f"IA: pessoa real sem posição ({r['motivo']})"}
    w, h = _tamanho(video)
    cams = []
    for (y0, x0, y1, x1) in r["caixas"]:
        cams.append((max(0, int((x0 - FOLGA) * w / 1000)), max(0, int((y0 - FOLGA) * h / 1000)),
                     min(w, int((x1 + FOLGA) * w / 1000)), min(h, int((y1 + FOLGA) * h / 1000))))
    corte = rosto.melhor_corte(w, h, cams)
    if not corte:
        return {"ok": False, "motivo": f"IA: câmera cobre jogo demais ({r['motivo']})"}
    x, y, cw, ch = corte
    with tempfile.TemporaryDirectory() as tmp:
        saida = Path(tmp) / "cortado.mp4"
        f = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", f"crop={cw}:{ch}:{x}:{y}",
                            "-c:a", "copy", str(saida)], capture_output=True, text=True)
        if f.returncode or not saida.exists():
            return {"ok": False, "motivo": f"ffmpeg falhou: {f.stderr.strip()[-160:]}"}
        de_novo = perguntar(saida)
        if de_novo["pessoa_real"] is not False:
            return {"ok": False, "motivo": f"IA: ainda há pessoa real depois do corte ({de_novo['motivo']})"}
        shutil.move(str(saida), str(video))
    return {"ok": True, "motivo": f"IA cortou a câmera ({r['motivo']})", "corte_ia": [x, y, cw, ch]}


# ---------------------------------------------------------------------------
# Formato dividido (Diego, 18/11, com print de referência): tela 9:16 sem moldura, a câmera
# do streamer em cima (40%) e o jogo embaixo (60%), preenchendo tudo. Substitui o corte que
# tirava a câmera.
LARG, ALT_CAM, ALT_JOGO = 1080, 768, 1152
APERTO = 12  # (de 1000) o Gemini devolve a caixa com folga; aperta um pouco para não pegar jogo


def _par(v: int) -> int:
    return max(2, v - v % 2)


def caixas_divididas(w: int, h: int, caixa: list[int] | None) -> tuple[tuple, tuple | None]:
    """(recorte do jogo, recorte da câmera ou None), cada um (x, y, largura, altura) em pixels."""
    gh = h
    gw = min(w, int(h * LARG / ALT_JOGO))
    cam = None
    if caixa:
        y0, x0, y1, x1 = caixa
        cx0, cy0 = max(0, int((x0 + APERTO) * w / 1000)), max(0, int((y0 + APERTO) * h / 1000))
        cx1, cy1 = min(w, int((x1 - APERTO) * w / 1000)), min(h, int((y1 - APERTO) * h / 1000))
        if cx1 - cx0 > 40 and cy1 - cy0 > 40:
            cam = (cx0, cy0, _par(cx1 - cx0), _par(cy1 - cy0))
    gx = (w - gw) // 2
    if cam:  # afasta o recorte do jogo da câmera, se der (câmera costuma ficar no canto)
        a0, a1 = cam[0], cam[0] + cam[2]
        if gx < a1 and gx + gw > a0:
            esq, dir_ = a0 - gw, a1  # jogo todo à esquerda ou à direita da câmera
            opcoes = [x for x in (esq, dir_) if 0 <= x <= w - gw]
            if opcoes:
                gx = min(opcoes, key=lambda x: abs(x - (w - gw) // 2))
    return (gx, 0, _par(gw), _par(gh)), cam


def montar_dividido(video: Path, saida: Path, caixa: list[int] | None, max_seg: int = 59) -> dict:
    w, h = _tamanho(video)
    jogo, cam = caixas_divididas(w, h, caixa)
    gx, gy, gw, gh = jogo
    baixo = f"crop={gw}:{gh}:{gx}:{gy},scale={LARG}:{ALT_JOGO}:force_original_aspect_ratio=increase,crop={LARG}:{ALT_JOGO}"
    if cam:
        x, y, cw, ch = cam
        filtro = (f"[0:v]split[a][b];[a]crop={cw}:{ch}:{x}:{y},scale={LARG}:{ALT_CAM}:force_original_aspect_ratio=increase,"
                  f"crop={LARG}:{ALT_CAM},setsar=1[cima];[b]{baixo},setsar=1[baixo];[cima][baixo]vstack,fps=30,format=yuv420p[v]")
    else:  # sem câmera: o jogo preenche a tela inteira
        filtro = (f"[0:v]crop={_par(min(w, int(h * 9 / 16)))}:{h}:{(w - min(w, int(h * 9 / 16))) // 2}:0,"
                  f"scale={LARG}:1920,setsar=1,fps=30,format=yuv420p[v]")
    f = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-t", str(max_seg),
                        "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "21", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(saida)],
                       capture_output=True, text=True)
    if f.returncode or not saida.exists():
        return {"ok": False, "motivo": f"ffmpeg falhou: {f.stderr.strip()[-160:]}"}
    return {"ok": True, "jogo": list(jogo), "camera": list(cam) if cam else None}


def dividir(bruto: Path, saida: Path) -> dict:
    """Confere o clipe (cutscene/menu = descarta) e monta no formato dividido."""
    r = perguntar(bruto)
    if r["pessoa_real"] is None:
        return {"ok": False, "motivo": f"checagem da IA indisponível ({r['motivo']}): descartado por segurança"}
    if r.get("conteudo") in ("cutscene", "menu"):
        return {"ok": False, "motivo": f"IA: {r['conteudo']}, não é gameplay ({r['motivo']})"}
    caixa = None
    if r["pessoa_real"] and r["caixas"]:
        caixa = max(r["caixas"], key=lambda c: (c[2] - c[0]) * (c[3] - c[1]))
        if (caixa[2] - caixa[0]) * (caixa[3] - caixa[1]) > 600_000:
            return {"ok": False, "motivo": f"IA: câmera ocupa a tela quase toda, não é jogo ({r['motivo']})"}
    m = montar_dividido(bruto, saida, caixa)
    if not m["ok"]:
        return m
    tipo = "câmera em cima, jogo embaixo" if m["camera"] else "sem câmera: só o jogo"
    return {"ok": True, "motivo": f"formato dividido ({tipo}; {r['motivo']})", "dividido": m}


PROMPT_FALAS = """Você recebe o áudio e 3 quadros de um clipe de live de GTA 6 de um streamer brasileiro.
Responda SÓ um JSON:
{"titulo": "...", "emoji": "...", "falas": [{"ini": 0.0, "fim": 1.2, "texto": "..."}]}
titulo: gancho de meme em português do Brasil (máx. 70 caracteres) sobre o que ACONTECE no clipe, usando o
apelido do streamer se ele for conhecido (ex.: "Mal saiu o jogo e o Alan já tretou com a IGUANA"). Só o que
dá para ouvir/ver; nada inventado. Sem hashtag, sem aspas. emoji: 1 emoji que combine.
falas: transcrição do que o streamer fala, em pedaços curtos de 1 a 4 palavras, com início e fim em segundos,
texto em MAIÚSCULAS, sem palavrão pesado (troque por ***). Lista vazia se não há fala."""


def transcrever(video: Path) -> dict:
    """Título de meme + legenda falada (pedaços curtos com tempo) pelo Gemini. {} se não der."""
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave:
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        aud = Path(tmp) / "a.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-b:a", "64k", str(aud)],
                       capture_output=True)
        partes = [{"text": "Transcreva e escreva o título."}]
        if aud.exists():
            partes.append({"inline_data": {"mime_type": "audio/mp3", "data": base64.b64encode(aud.read_bytes()).decode()}})
        partes += [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(q.read_bytes()).decode()}}
                   for q in _quadros(video, Path(tmp))]
    corpo = {"systemInstruction": {"parts": [{"text": PROMPT_FALAS}]},
             "contents": [{"role": "user", "parts": partes}],
             "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}}
    for modelo in dict.fromkeys([_modelo(), SEG._modelo_gemini()]):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
            dado = json.loads(SEG._post(url, corpo, {"x-goog-api-key": chave}, timeout=90))
            txt = "".join(p.get("text", "") for p in ((dado.get("candidates") or [{}])[0].get("content") or {}).get("parts", []))
            return json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        except Exception as e:
            print(f"  transcrever {modelo}: {str(e)[:160]}")
    return {}


if __name__ == "__main__":
    ent, sai = Path(sys.argv[1]), Path(sys.argv[2])
    if len(sys.argv) > 3 and sys.argv[3] == "dividido":
        print(json.dumps(dividir(ent, sai), ensure_ascii=False))
    else:
        shutil.copy(ent, sai)
        print(json.dumps(limpar(sai), ensure_ascii=False))
