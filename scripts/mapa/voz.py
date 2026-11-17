"""Gera a narração do vídeo do mapa (Gemini TTS), um WAV por segmento e por voz. Roda no Actions."""
import base64, json, os, re, sys, time, urllib.error, urllib.request, wave
from pathlib import Path
R = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
OUT = Path(sys.argv[2])
MODELOS = os.environ.get("TTS_MODELOS", "gemini-2.5-flash-preview-tts,gemini-3.1-flash-tts-preview").split(",")
chave = os.environ["GEMINI_API_KEY"].strip()
travado = None
import socket
socket.setdefaulttimeout(90)

def pedir(modelo, voz, texto):
    corpo = {"contents": [{"parts": [{"text": R["estilo"] + texto}]}],
             "generationConfig": {"responseModalities": ["AUDIO"], "temperature": 0.5,
                                  "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voz}}}}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                                 data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": chave})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())

log = []
for voz in R["vozes"]:
    (OUT / voz).mkdir(parents=True, exist_ok=True)
    for s in R["segmentos"]:
        dest = OUT / voz / f"{s['id']}.wav"
        if dest.exists():
            continue
        for modelo in ([travado] if travado else MODELOS):
            ok = False
            for t in range(3):
                try:
                    d = pedir(modelo, voz, s["texto"])
                    p = d["candidates"][0]["content"]["parts"][0]["inlineData"]
                    taxa = int((re.search(r"rate=(\d+)", p.get("mimeType", "")) or [0, 24000])[1])
                    with wave.open(str(dest), "wb") as w:
                        w.setnchannels(1); w.setsampwidth(2); w.setframerate(taxa); w.writeframes(base64.b64decode(p["data"]))
                    travado = modelo; ok = True
                    log.append(f"{voz} {s['id']} {modelo}")
                    break
                except urllib.error.HTTPError as e:
                    corpo = e.read().decode("utf8", "replace")
                    print(voz, s["id"], modelo, e.code, corpo[:300], flush=True)
                    if e.code in (429, 500, 503):
                        time.sleep(10 * (t + 1)); continue
                    break
                except (KeyError, IndexError, TypeError) as e:
                    print("sem áudio", e, flush=True); time.sleep(5); continue
            if ok:
                break
        if not dest.exists():
            print("FALHOU", voz, s["id"], flush=True)
            log.append(f"FALHOU {voz} {s['id']}")
        print(time.strftime("%H:%M:%S"), voz, s["id"], dest.exists(), flush=True)
(OUT / "log.txt").write_text("\n".join(log))
print("\n".join(log))
