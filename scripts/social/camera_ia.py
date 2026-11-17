"""Segunda barreira contra o rosto do streamer (Diego, 10/11: só a imagem do jogo).

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

Você recebe 3 quadros do mesmo clipe. Responda SÓ um JSON:
{"pessoa_real": true|false, "caixas": [[ymin, xmin, ymax, xmax], ...], "motivo": "frase curta"}

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
        for tentativa in range(3):
            try:
                dado = json.loads(SEG._post(url, corpo, {"x-goog-api-key": chave}, timeout=180))
                cand = (dado.get("candidates") or [{}])[0]
                txt = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
                j = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
                caixas = [[int(v) for v in c][:4] for c in (j.get("caixas") or []) if len(c) >= 4]
                return {"pessoa_real": bool(j.get("pessoa_real")), "caixas": caixas,
                        "motivo": str(j.get("motivo", ""))[:160], "modelo": modelo}
            except urllib.error.HTTPError as e:
                ultimo = f"Gemini {modelo} HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:120]}"
                if e.code in (429, 500, 503) and tentativa < 2:
                    time.sleep(15 * (tentativa + 1))
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


if __name__ == "__main__":
    ent, sai = Path(sys.argv[1]), Path(sys.argv[2])
    shutil.copy(ent, sai)
    print(json.dumps(limpar(sai), ensure_ascii=False))
