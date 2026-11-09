"""Montagem automática dos Reels que o motor de pesquisa baixou.

Pega os vídeos de social/reels/entrada/<dia>/ (cada mp4 com um .json ao lado,
gravado por scripts/social/pesquisa.py), escreve o título e a legenda, monta na
identidade da Pixelzada (scripts/social/gerador/montar.js, as 20 molduras v4) e
põe cada um no próximo horário livre da fila (social/reels/fila.json).

Assim os 6 Reels por dia não dependem de ninguém: o robô de pesquisa baixa, este
script monta e o workflow Reels publica. O Claude revisa depois e troca o que
ficou ruim.

    python -m scripts.social.montagem faltam        quantos horários dos próximos dias estão sem vídeo
    python -m scripts.social.montagem automatico    monta tudo o que está em social/reels/entrada/

Título e legenda: o GitHub Models (GITHUB_TOKEN do Actions) adapta a legenda
original para um título curto em português, sem inventar. Sem ele, usa um título
simples e verdadeiro ("Esse vídeo de GTA 6 está bombando hoje").
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from . import reels as R
from .pauta import ROOT, TZ

ENTRADA = ROOT / "social" / "reels" / "entrada"
VIDEOS = R.PASTA / "videos"
GERADOR = Path(__file__).resolve().parent / "gerador" / "montar.js"
DIAS_RESERVA = 3          # hoje + 2 dias de reserva na fila
FOLGA = timedelta(minutes=40)  # horário que começa em menos de 40 min já não recebe vídeo novo

CTA = {
    "gta6": "Essa é a página pra seguir e acompanhar o GTA 6",
    "battlefield6": "Essa é a página pra seguir e acompanhar o Battlefield 6",
    "forza6": "Essa é a página pra seguir e acompanhar o Forza Horizon 6",
    "games": "Essa é a página pra seguir e acompanhar o universo dos games",
}
SEGUE = {
    "gta6": "o GTA 6", "battlefield6": "o Battlefield 6", "forza6": "o Forza Horizon 6", "games": "o universo dos games",
}
CORES = ["#FF3D8B", "#2EE6FF", "#FFD23F", "#8C5BFF", "#3DFF8B", "#FF7A2E"]
TAGS = {
    "gta6": ["#gta6", "#gtavi", "#gta"], "battlefield6": ["#battlefield6", "#bf6", "#battlefield"],
    "forza6": ["#forzahorizon6", "#forza", "#fh6"], "games": ["#games", "#memesgamer", "#gamer"],
}
NOME_ESTILO = {
    "moldura": "Moldura", "legenda": "Legenda", "faixa": "Faixa", "hud": "HUD", "fliperama": "Fliperama",
    "polaroid": "Polaroid", "conversa": "Conversa", "plantao": "Plantão", "cartaz": "Cartaz", "gigante": "Gigante",
    "celular": "Celular", "stories": "Stories", "tv": "TV", "claquete": "Claquete", "missao": "Missão",
    "conquista": "Conquista", "quadrinho": "Quadrinho", "figurinha": "Figurinha", "inventario": "Inventário",
    "carregando": "Carregando",
}


# ---------------------------------------------------------------------------
# Horários livres
# ---------------------------------------------------------------------------
def horarios_livres(fila: list[dict], agora: datetime | None = None, dias: int = DIAS_RESERVA) -> list[tuple[str, str]]:
    agora = agora or datetime.now(TZ)
    ocupados = {(i["data"], i["horario"]) for i in fila if i["status"] in ("agendado", "publicado")}
    livres = []
    for d in range(dias):
        dia = (agora + timedelta(days=d)).date().isoformat()
        for h in R.horarios(dia):
            t = datetime.fromisoformat(f"{dia}T{h}:00").replace(tzinfo=TZ)
            if t > agora + FOLGA and (dia, h) not in ocupados:
                livres.append((dia, h))
    return livres


def pendentes() -> list[Path]:
    return sorted(p for p in ENTRADA.glob("*/*.mp4") if p.with_suffix(".json").exists()) if ENTRADA.exists() else []


def faltam(agora: datetime | None = None) -> int:
    """Quantos vídeos ainda precisam ser baixados para cobrir hoje e os próximos 2 dias."""
    return max(0, len(horarios_livres(R.carregar(), agora)) - len(pendentes()))


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
PROMPT = """Você escreve os títulos dos Reels do @pixelzada.br, perfil brasileiro de games.
Recebe a legenda original de um vídeo de outro perfil (pode estar em inglês) e devolve SÓ um JSON:
{"titulo": "...", "emoji": "...", "hashtags": ["#...", "#..."], "slug": "..."}

Regras do título:
- português do Brasil, tom solto de meme, no máximo 90 caracteres;
- diga o que acontece no vídeo usando SÓ o que a legenda diz; nada de inventar fato, número ou piada que não está lá;
- se a legenda não diz nada útil, escreva algo simples e verdadeiro sobre o jogo;
- o nome do jogo principal vai entre <em> e </em> (uma vez só); "GTA 6" escrito assim, nunca "GTA VI";
- sem emoji, sem hashtag, sem @, sem link, sem "comenta", sem pergunta no fim, sem aspas.
emoji: 1 emoji que combine com o vídeo. hashtags: 2 ou 3, minúsculas, do assunto (sem #pixelzada).
slug: 3 a 5 palavras em minúsculas, sem acento, separadas por hífen, que resumam o vídeo."""


def gerar_texto(info: dict) -> dict:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        corpo = {
            "model": os.environ.get("MODELO_TITULO", "openai/gpt-4.1-mini"),
            "temperature": 0.4,
            "messages": [
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": f"Jogo: {info.get('jogo')}\nPerfil: @{info.get('perfil')}\n"
                                            f"Legenda original: {info.get('legenda_completa') or info.get('legenda') or '(vazia)'}"},
            ],
        }
        req = urllib.request.Request("https://models.github.ai/inference/chat/completions",
                                     data=json.dumps(corpo).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                              "Accept": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                bruto = r.read().decode("utf-8", "replace")
            try:
                txt = json.loads(bruto)["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError):
                raise RuntimeError(f"resposta inesperada: {bruto[:200]!r}") from None
            dado = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
            titulo = limpar_titulo(dado.get("titulo", ""))
            if 8 <= len(re.sub(r"<[^>]+>", "", titulo)) <= 110:
                return {"titulo": titulo, "emoji": (dado.get("emoji") or "🎮")[:4],
                        "hashtags": [h for h in dado.get("hashtags", []) if re.fullmatch(r"#[a-z0-9_]+", h)][:3],
                        "slug": slugify(dado.get("slug", "")), "fonte": "modelo"}
            print(f"  título do modelo fora do padrão: {titulo!r}")
        except urllib.error.HTTPError as e:
            print(f"  GitHub Models HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}; título simples")
        except Exception as e:  # sem modelo, segue com o título simples
            print(f"  GitHub Models indisponível ({str(e)[:200]}); título simples")
    jogo = info.get("jogo") or "o universo dos games"
    titulo = ("Esse vídeo está bombando hoje no <em>universo dos games</em>" if info.get("tema") == "games"
              else f"Esse vídeo de <em>{jogo}</em> está bombando hoje")
    return {"titulo": titulo, "emoji": "🎮", "hashtags": [], "slug": "", "fonte": "padrao"}


def limpar_titulo(t: str) -> str:
    t = re.sub(r"[#@]\S+|https?://\S+", "", t or "")
    t = "".join(c for c in t if unicodedata.category(c) != "So")  # sem emoji (o Chromium do Actions não tem a fonte)
    t = re.sub(r"\bGTA ?VI\b", "GTA 6", t).strip(" \"'“”")
    if t.count("<em>") != t.count("</em>"):
        t = re.sub(r"</?em>", "", t)
    return re.sub(r"\s+", " ", t).strip()


def slugify(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60]


def legenda(titulo: str, emoji: str, tema: str, tags: list[str]) -> str:
    texto = re.sub(r"</?em>", "", titulo)
    base = TAGS.get(tema, TAGS["games"])
    todas = list(dict.fromkeys([*tags, *base]))[:4] + ["#pixelzada"]
    return f"{texto} {emoji}\n\nSegue @pixelzada.br pra acompanhar {SEGUE.get(tema, SEGUE['games'])}.\n\n{' '.join(todas)}"


def proximos_estilos(fila: list[dict], n: int) -> list[str]:
    """Rodízio: começa pelos estilos usados há mais tempo."""
    ultimo = {}
    for i, item in enumerate(fila):
        for chave, nome in NOME_ESTILO.items():
            if item.get("estilo") == nome:
                ultimo[chave] = i
    ordem = sorted(NOME_ESTILO, key=lambda k: ultimo.get(k, -1))
    return [ordem[i % len(ordem)] for i in range(n)]


# ---------------------------------------------------------------------------
# Comando
# ---------------------------------------------------------------------------
def automatico(agora: datetime | None = None) -> int:
    fila = R.carregar()
    livres = horarios_livres(fila, agora, dias=14)
    videos = sorted(pendentes(), key=lambda p: (not p.name.startswith("00-link"), str(p)))  # os do Diego primeiro
    print(f"{len(videos)} vídeo(s) esperando montagem; {len(livres)} horário(s) livre(s) nos próximos 14 dias")
    if not videos or not livres:
        return 0
    videos = videos[:len(livres)]
    estilos = proximos_estilos(fila, len(videos))
    slugs = {i["slug"] for i in fila}
    pedido, itens = [], []
    for n, (mp4, estilo) in enumerate(zip(videos, estilos)):
        info = json.loads(mp4.with_suffix(".json").read_text(encoding="utf-8"))
        tema = info.get("tema") if info.get("tema") in CTA else "games"
        texto = gerar_texto(info)
        base = texto["slug"] or slugify(f"{info.get('jogo', 'games')}-{info.get('perfil', '')}")
        slug, k = base or f"motor-{n}", 2
        while slug in slugs or (VIDEOS / f"{slug}.mp4").exists():
            slug, k = f"{base}-{k}", k + 1
        slugs.add(slug)
        print(f"  {mp4.name} -> {slug} ({estilo}, título {texto['fonte']}): {texto['titulo']}")
        pedido.append({"video": str(mp4), "saida": str(VIDEOS / slug), "estilo": estilo,
                       "cor": CORES[(len(fila) + n) % len(CORES)], "jogo": info.get("jogo", ""),
                       "titulo": texto["titulo"], "frase": CTA[tema], "max_seg": 40})
        itens.append((mp4, slug, estilo, texto, tema, info))
    with tempfile.TemporaryDirectory() as tmp:
        ped, res = Path(tmp) / "pedido.json", Path(tmp) / "resultado.json"
        ped.write_text(json.dumps(pedido, ensure_ascii=False), encoding="utf-8")
        subprocess.run(["node", str(GERADOR), str(ped), str(res)], check=False)
        resultado = json.loads(res.read_text(encoding="utf-8")) if res.exists() else []
    ok = {r["saida"] for r in resultado if r.get("ok")}
    usados = 0
    for (mp4, slug, estilo, texto, tema, info) in itens:
        if str(VIDEOS / slug) not in ok:
            print(f"  {slug}: a montagem falhou; o vídeo bruto fica em {mp4.relative_to(ROOT)}")
            continue
        dia, hora = livres[usados]
        usados += 1
        fila.append({"slug": slug, "data": dia, "horario": hora, "status": "agendado",
                     "estilo": NOME_ESTILO[estilo],
                     "legenda": legenda(texto["titulo"], texto["emoji"], tema, texto["hashtags"]),
                     "tentativas": 0,
                     "origem": {"motor": True, "perfil": info.get("perfil"), "link": info.get("link"),
                                "titulo": texto["fonte"], "revisado": False}})
        mp4.unlink()
        mp4.with_suffix(".json").unlink()
        print(f"  {slug}: na fila {dia} {hora}")
    for pasta in ENTRADA.glob("*"):
        if pasta.is_dir() and not any(pasta.iterdir()):
            pasta.rmdir()
    R.salvar(fila)
    print(f"{usados} Reel(s) montado(s) e agendado(s)")
    return 0 if usados or not itens else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("faltam")
    sub.add_parser("automatico")
    args = ap.parse_args(argv)
    if args.cmd == "faltam":
        livres = horarios_livres(R.carregar())
        print(f"horários livres até daqui a {DIAS_RESERVA - 1} dias: {len(livres)}; vídeos esperando montagem: "
              f"{len(pendentes())}; faltam baixar: {faltam()}")
        for d, h in livres:
            print(f"  {d} {h}")
        return 0
    return automatico()


if __name__ == "__main__":
    sys.exit(main())
