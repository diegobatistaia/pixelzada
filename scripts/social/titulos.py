"""Títulos dos Reels: regra de gancho (Diego, 18/11) e refação dos títulos genéricos.

O Diego reprovou o título padrão "Esse vídeo de GTA 6 está bombando hoje": frase vaga,
que serve para qualquer vídeo. A regra abaixo saiu dos Reels que mais renderam no perfil
(métricas de 18/11) e dos concorrentes que passaram de 3x a média (listas do motor):

  - Mortal Kombat (42 mil views, 1.750 compartilhamentos): "Quando Mortal Kombat não dá mais
    dinheiro e os lutadores precisam arrumar outro emprego" (situação concreta + humor)
  - "O segredo da Máscara da Verdade em Zelda: os personagens veem a máscara do Link e reagem"
    (curiosidade específica)
  - "Como vou me sentir desinstalando o GTA 5 pra instalar o GTA 6" / "Eu indo pra casa no dia
    19..." (identificação)
  - "A mira do GTA 6 contra a do GTA 5" (comparação concreta)
  - concorrentes: "O Series S vai conseguir acompanhar o PS5 em GTA 6?" (132x e 34x a média):
    pergunta sobre uma disputa concreta.

O Gemini (segredo GEMINI_API_KEY) ouve o áudio e vê 4 quadros do vídeo final e escreve o
título dizendo o que ACONTECE no clipe.

    python -m scripts.social.titulos refazer           todos os agendados com título genérico
    python -m scripts.social.titulos refazer slug1,slug2
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from . import reels as R
from . import seguranca as SEG

REGRA = """Você escreve o título dos Reels do @pixelzada.br, perfil brasileiro de GTA 6 e games.
Você recebe o áudio e alguns quadros do vídeo, e às vezes o título do clipe ou a legenda original.
Responda SÓ um JSON: {"titulo": "...", "emoji": "...", "nota": 0}

O título vai escrito em cima do vídeo e é o gancho que segura quem está rolando o feed.

REGRAS
1. Diga o que ACONTECE neste vídeo: a cena, a fala, o detalhe, a reação. Quem lê o título tem
   que imaginar o vídeo. Se o título serve para qualquer outro vídeo, está errado.
2. Use um destes ganchos (os que mais renderam no perfil e nos concorrentes):
   - situação de identificação: "Eu quando...", "Eu indo...", "Quando você..."
   - humor com a cena: "Mal saiu o jogo e o Alan já tretou com uma iguana"
   - curiosidade específica: "Os NPCs de GTA 6 desviam da poça quando chove"
   - comparação concreta: "A mira do GTA 6 contra a do GTA 5"
   - pergunta sobre algo concreto: "O Series S vai aguentar GTA 6?"
3. Português do Brasil, solto, de conversa. De 25 a 70 caracteres. "GTA 6" sempre assim.
4. Só o que dá para ver ou ouvir no vídeo, ou o que está no texto recebido. Nada de inventar fato,
   número, nome ou fala. Streamer: use o apelido conhecido (alanzoka = Alan, Bisteconee = Bistecone,
   PaulinhoLOKObr = Paulinho) quando o vídeo for dele.
5. PROIBIDO (títulos genéricos que o Diego reprovou): "está bombando", "o caos começou",
   "olha isso", "olha esse vídeo", "isso é insano", "você precisa ver", "esse vídeo de GTA 6",
   "simplesmente incrível", "de outro mundo", "o melhor vídeo", "ninguém esperava", "isso aqui".
   Sem emoji, sem hashtag, sem @, sem aspas, sem "comenta", sem "segue".

BONS: "O Alan levou 3 estrelas tentando estacionar o carro" / "Quando o NPC de GTA 6 revida a
buzinada" / "Eu na primeira hora de GTA 6 só andando de jet ski" / "A chuva de GTA 6 molha até
o asfalto da rodovia"
RUINS: "Esse vídeo de GTA 6 está bombando hoje" / "O caos começou em GTA 6" / "Olha isso no GTA 6"
/ "GTA 6 é simplesmente insano"

emoji: 1 emoji que combine com a cena (vai na legenda, não no vídeo).
nota: de 0 a 10, quanto você entendeu do que acontece no vídeo (0 = não deu para entender nada)."""

GENERICOS = re.compile(
    r"bombando|o caos come[çc]ou|olha (s[oó] )?(isso|esse v[ií]deo)|isso (aqui )?[ée] insano|voc[eê] precisa ver|"
    r"esse v[ií]deo d[eo]|simplesmente (incr[ií]vel|insano)|de outro mundo|o melhor v[ií]deo|ningu[eé]m esperava|"
    r"^isso aqui", re.I)

APELIDO = {"alanzoka": "Alan", "bisteconee": "Bistecone", "paulinholokobr": "Paulinho", "burgaofps": "Burgão"}


def generico(titulo: str) -> bool:
    t = re.sub(r"<[^>]+>", "", titulo or "")
    return bool(GENERICOS.search(t)) or len(t.strip()) < 15


def _quadros(video: Path, pasta: Path, n: int = 4) -> list[Path]:
    try:
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                             "-of", "csv=p=0", str(video)], text=True).strip() or 0)
    except (subprocess.CalledProcessError, ValueError):
        dur = 0
    saida = []
    for k in range(n):
        q = pasta / f"q{k}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.2, dur * (k + 1) / (n + 1)):.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "5", str(q)], capture_output=True)
        if q.exists():
            saida.append(q)
    return saida


def titular(video: Path, contexto: str = "") -> dict:
    """{"titulo", "emoji", "nota"} pelo Gemini com a regra; {} se não der ou se sair genérico."""
    chave = os.environ.get("GEMINI_API_KEY", "").strip()
    if not chave or not video.exists():
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        aud = Path(tmp) / "a.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-b:a", "48k", "-t", "60", str(aud)],
                       capture_output=True)
        partes = [{"text": "Escreva o título deste vídeo seguindo a regra." + (f"\n\nContexto:\n{contexto}" if contexto else "")}]
        if aud.exists() and aud.stat().st_size > 1000:
            partes.append({"inline_data": {"mime_type": "audio/mp3", "data": base64.b64encode(aud.read_bytes()).decode()}})
        partes += [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(q.read_bytes()).decode()}}
                   for q in _quadros(video, Path(tmp))]
    corpo = {"systemInstruction": {"parts": [{"text": REGRA}]},
             "contents": [{"role": "user", "parts": partes}],
             "generationConfig": {"temperature": 0.6, "responseMimeType": "application/json"}}
    for modelo in dict.fromkeys([os.environ.get("MODELO_GEMINI_TITULO") or "gemini-flash-latest", SEG._modelo_gemini()]):
        for _ in range(2):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
                dado = json.loads(SEG._post(url, corpo, {"x-goog-api-key": chave}, timeout=90))
                txt = "".join(p.get("text", "") for p in ((dado.get("candidates") or [{}])[0].get("content") or {}).get("parts", []))
                j = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
                titulo = limpar(j.get("titulo", ""))
                if generico(titulo) or len(titulo) > 90:
                    print(f"  título do Gemini recusado ({titulo!r}); de novo")
                    continue
                return {"titulo": titulo, "emoji": (j.get("emoji") or "🎮")[:4], "nota": j.get("nota"), "modelo": modelo}
            except Exception as e:
                print(f"  titular {modelo}: {str(e)[:160]}")
                break
    return {}


def limpar(t: str) -> str:
    import unicodedata
    t = re.sub(r"[#@]\S+|https?://\S+|</?em>", "", t or "")
    t = "".join(c for c in t if unicodedata.category(c) != "So")
    t = re.sub(r"\bGTA ?VI\b", "GTA 6", t, flags=re.I).strip(" \"'“”.")
    return re.sub(r"\s+", " ", t).strip()


def contexto_do_item(item: dict) -> str:
    o = item.get("origem") or {}
    perfil = o.get("perfil") or ""
    linhas = []
    if perfil.lower().startswith(("twitch/", "kick/")):
        canal = perfil.split("/", 1)[1]
        linhas.append(f"Clipe da live do streamer {canal} (apelido: {APELIDO.get(canal.lower(), canal)}), jogando GTA 6.")
    elif perfil:
        linhas.append(f"Vídeo do perfil @{perfil}.")
    if o.get("titulo_clipe"):
        linhas.append(f"Título do clipe: {o['titulo_clipe']}")
    return "\n".join(linhas)


def trocar_legenda(legenda: str, titulo: str, emoji: str) -> str:
    resto = (legenda or "").split("\n", 1)
    return f"{titulo} {emoji}" + ("\n" + resto[1] if len(resto) > 1 else "")


def refazer_topo_modelo2(item: dict, titulo: str) -> bool:
    """Modelo 2 (branca + frase): repinta só o topo branco do vídeo final com o título novo."""
    g = Path(__file__).resolve().parent / "gerador"
    mp4 = R.PASTA / "videos" / f"{item['slug']}.mp4"
    with tempfile.TemporaryDirectory() as tmp:
        saida = Path(tmp) / "novo.mp4"
        r = subprocess.run(["node", str(g / "topo-modelo2.js"), str(mp4), titulo, str(saida), str(g)],
                           capture_output=True, text=True, timeout=600)
        if r.returncode or not saida.exists():
            print(f"  {item['slug']}: topo do modelo 2 falhou ({(r.stderr or '')[-200:]})")
            return False
        mp4.write_bytes(saida.read_bytes())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(mp4), "-frames:v", "1", "-q:v", "2",
                    str(mp4.with_suffix(".jpg"))], capture_output=True)
    return True


def refazer(alvo: str) -> int:
    from datetime import datetime
    from .pauta import TZ
    fila = R.carregar()
    agora = datetime.now(TZ)
    futuros = [i for i in fila if i["status"] == "agendado" and R.quando(i) > agora]
    if alvo == "todos":
        itens = [i for i in futuros if generico((i.get("legenda") or "").split("\n")[0])
                 or (i.get("origem") or {}).get("titulo") == "padrao"]
    else:
        slugs = {s.strip() for s in alvo.split(",") if s.strip()}
        itens = [i for i in futuros if i["slug"] in slugs]
    print(f"{len(itens)} Reel(s) com título para refazer")
    brancos, feitos = [], 0
    for item in itens:
        mp4 = R.PASTA / "videos" / f"{item['slug']}.mp4"
        antes = (item.get("legenda") or "").split("\n")[0]
        t = titular(mp4, contexto_do_item(item))
        if not t:
            print(f"  {item['slug']}: sem título novo; fica como está")
            continue
        estilo = item.get("estilo") or ""
        if estilo.startswith("Branca + frase"):
            if not refazer_topo_modelo2(item, t["titulo"]):
                continue
        item["legenda"] = trocar_legenda(item.get("legenda", ""), t["titulo"], t["emoji"])
        item.setdefault("origem", {})["titulo"] = "gemini-regra"
        item["origem"]["titulo_antes"] = antes
        if estilo == "Simples branca":
            brancos.append(item["slug"])
        feitos += 1
        print(f"  {item['slug']} ({item['data']} {item['horario']}, {estilo}; nota {t.get('nota')}):\n"
              f"     antes: {antes}\n     agora: {t['titulo']}")
    R.salvar(fila)
    if brancos:  # título escrito no vídeo: monta de novo na moldura branca
        from . import refazer as REF
        REF.main([",".join(brancos)])
    print(f"{feitos} de {len(itens)} título(s) refeito(s)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "refazer":
        sys.exit(refazer(sys.argv[2] if len(sys.argv) > 2 else "todos"))
    print(__doc__)
    sys.exit(2)
