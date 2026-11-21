"""Amostras de voz do narrador (Guia Vice City). Usa so a chave GRATIS do Gemini.

    python -m scripts.longo.vozes_amostra scripts/longo/vozes_amostra.txt

Arquivo de pedido: 1a linha = vozes separadas por espaco; resto = texto.
Saida: previas/longo/amostras-voz/<voz>.mp3 + resultado.json
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SAIDA = RAIZ / "previas/longo/amostras-voz"
MODELOS = ["gemini-2.5-flash-preview-tts"]  # o mesmo modelo do vídeo: a amostra é a voz de verdade
ESTILO = ("Narre em português do Brasil como o Leo, um jovem gamer brasileiro de uns 20 anos que tem um "
          "canal de guias de GTA no YouTube: animado, simpático, falando direto com quem assiste, como um "
          "amigo contando um segredo, ritmo rápido mas claro, sem gritar. Leia exatamente este texto:\n\n")


def pedir(modelo: str, chave: str, voz: str, texto: str) -> bytes:
    corpo = {"contents": [{"parts": [{"text": ESTILO + texto}]}],
             "generationConfig": {"responseModalities": ["AUDIO"], "temperature": 0.5,
                                  "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": chave})
    with urllib.request.urlopen(req, timeout=240) as r:
        d = json.loads(r.read())
    return base64.b64decode(d["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])


def main(arq: str) -> int:
    linhas = Path(arq).read_text(encoding="utf-8").strip().split("\n", 1)
    vozes, texto = linhas[0].split(), linhas[1].strip()
    chave = os.environ.get("GEMINI_API_KEY_GRATIS", "").strip()
    res = {"chave_gratis": bool(chave), "vozes": {}}
    SAIDA.mkdir(parents=True, exist_ok=True)
    if not chave:
        print("SEM GEMINI_API_KEY_GRATIS")
    for voz in vozes:
        if not chave:
            break
        for modelo in MODELOS:
            try:
                pcm = pedir(modelo, chave, voz, texto)
            except urllib.error.HTTPError as e:
                corpo = e.read().decode("utf-8", "replace")[:300]
                print(f"{voz} {modelo}: HTTP {e.code} {corpo}")
                res["vozes"].setdefault(voz, {}).setdefault("erros", []).append(f"{modelo}: {e.code}")
                continue
            except Exception as e:  # noqa: BLE001
                print(f"{voz} {modelo}: {e}")
                res["vozes"].setdefault(voz, {}).setdefault("erros", []).append(f"{modelo}: {e}")
                continue
            wav = SAIDA / f"{voz}.wav"
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af", "loudnorm=I=-16",
                            "-b:a", "128k", str(SAIDA / f"{voz}.mp3")], check=True)
            wav.unlink()
            res["vozes"].setdefault(voz, {})["modelo"] = modelo
            print(f"{voz}: ok ({modelo})")
            break
        time.sleep(3)
    (SAIDA / "resultado.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
