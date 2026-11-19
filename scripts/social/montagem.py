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
simples e verdadeiro. Título genérico ("está bombando", "o caos começou") o Diego reprovou
(18/11): nesse caso o Gemini vê e ouve o vídeo e escreve pela regra de scripts/social/titulos.py;
se nem assim sair um título que diga o que acontece, o vídeo espera a próxima rodada.
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

from . import reels as R, seguranca as SEG, titulos as TIT
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
# Teste do Diego (11/11): 1/3 moldura simples branca, 1/3 simples preta, 1/3 estilo da
# identidade (rodízio acima). Quem decide é a posição do horário na grade do dia.
SIMPLES = {"simples-branca": "Simples branca", "simples-preta": "Simples preta"}
TERCOS = ["simples-branca", "simples-preta", None]


def eh_streamer(mp4: Path) -> bool:
    """Corte de live (lives.py grava perfil twitch/<canal> ou kick/<canal>)."""
    try:
        perfil = json.loads(mp4.with_suffix(".json").read_text(encoding="utf-8")).get("perfil") or ""
    except (OSError, ValueError):
        return False
    return perfil.lower().startswith(("twitch/", "kick/"))


# Os 3 modelos de corte de streamer que o Diego aprovou (18/11), em rodízio; a etiqueta
# modelo_streamer fica no Reel para comparar o desempenho.
MODELOS_STREAMER = {"dividido": "Dividido (modelo 1)", "streamer-branca": "Branca + frase (modelo 2)",
                    "streamer-desfocado": "Desfocado + título + legenda (modelo 3)"}
ORDEM_STREAMER = ["dividido", "streamer-branca", "streamer-desfocado"]


def modelo_streamer(fila: list[dict], info: dict, ja_nesta: int = 0) -> str:
    """Próximo modelo do rodízio. Modelo 2 precisa da câmera; modelo 3, do clipe original."""
    feitos = [((i.get("etiquetas") or {}).get("modelo_streamer") or (i.get("etiquetas") or {}).get("teste_modelo") or "")
              for i in fila if ((i.get("origem") or {}).get("perfil") or "").lower().startswith(("twitch/", "kick/"))]
    ultimo = next((f for f in reversed(feitos) if f), "")
    ultimo = {"modelo1-dividido": "dividido", "modelo2-branca-frase": "streamer-branca",
              "modelo3-desfocado-legenda": "streamer-desfocado"}.get(ultimo, ultimo)
    k = (ORDEM_STREAMER.index(ultimo) + 1 + ja_nesta) % 3 if ultimo in ORDEM_STREAMER else ja_nesta % 3
    for passo in range(3):
        m = ORDEM_STREAMER[(k + passo) % 3]
        if m == "streamer-branca" and info.get("camera") is False:
            continue
        if m == "streamer-desfocado" and not info.get("falas"):
            continue
        return m
    return "dividido"


def montar_streamer(estilo: str, mp4: Path, info: dict, titulo: str, saida: Path) -> bool:
    if estilo == "dividido":
        shutil.copy(mp4, saida)
        return True
    g = GERADOR.parent
    with tempfile.TemporaryDirectory() as tmp:
        if estilo == "streamer-branca":
            cmd = ["node", str(g / "streamer-modelo2.js"), str(mp4), titulo, str(saida), str(g)]
        else:
            original = mp4.with_name(mp4.stem + "-original.mp4")
            if not original.exists():
                return False
            falas = Path(tmp) / "falas.json"
            f = dict(info.get("falas") or {})
            f["titulo"] = re.sub(r"</?em>", "", titulo)
            falas.write_text(json.dumps(f, ensure_ascii=False), encoding="utf-8")
            cmd = ["node", str(g / "streamer-modelo3.js"), str(original), str(falas), str(saida), str(g)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode or not saida.exists():
        print(f"  {estilo} falhou ({(r.stderr or '')[-300:]}); vai no modelo 1")
        saida.unlink(missing_ok=True)
        return False
    return True


def estilo_do_horario(dia: str, hora: str) -> str | None:
    """simples-branca / simples-preta, ou None para o rodízio da identidade."""
    grade = R.horarios(dia)
    return TERCOS[grade.index(hora) % 3] if hora in grade else None


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
- prefira o molde de meme de identificação, que é o que mais viraliza no perfil: "Eu quando...",
  "Eu indo...", "Como vou me sentir...", "Quando [personagem] não dá mais dinheiro..." (sem inventar o que não está no vídeo);
- PROIBIDO título genérico que serve para qualquer vídeo ("está bombando", "o caos começou", "olha isso",
  "esse vídeo de GTA 6", "isso é insano"); se a legenda não diz o que acontece, responda {"titulo": ""};
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
    # Diego, 18/11: sem frase de CTA ("Segue @pixelzada.br pra acompanhar...") na legenda.
    return f"{texto} {emoji}\n\n{' '.join(todas)}"


def legenda_streamer(canal: str) -> str:
    """Só o crédito do canal de origem (nome da Twitch), sem frase inventada (Diego, 18/11)."""
    tag = re.sub(r"[^a-z0-9_]", "", canal.lower())
    return f"🎮 {canal} jogando GTA 6\n📺 twitch.tv/{tag}\n\n#gta6 #gtavi #{tag} #pixelzada"


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
    # não remontar vídeo cujo link já está na fila (ex.: montado à mão antes; duplicou em 11/11)
    na_fila = {(i.get("origem") or {}).get("link", "").rstrip("/").lower() for i in fila} - {""}
    for mp4 in list(videos):
        try:
            link = json.loads(mp4.with_suffix(".json").read_text(encoding="utf-8")).get("link") or ""
        except (OSError, ValueError):
            continue
        if link.rstrip("/").lower() in na_fila:
            print(f"  {mp4.name}: já está na fila ({link}); bruto apagado")
            videos.remove(mp4)
            mp4.unlink()
            mp4.with_suffix(".json").unlink()
    print(f"{len(videos)} vídeo(s) esperando montagem; {len(livres)} horário(s) livre(s) nos próximos 14 dias")
    if not videos or not livres:
        return 0
    videos = [v for v in videos if passa_na_checagem(v)][:len(livres)]
    if not videos:
        return 0
    vagas = livres[:len(videos)]  # cada vídeo já sabe o horário: o estilo depende dele
    # Diego, 18/11: todo Reel que não é corte de streamer sai em moldura simples branca
    # com o título escrito; os cortes da Twitch/Kick seguem o layout próprio deles.
    # Diego, 18/11 21h: nunca mais a moldura da identidade (TV, Celular etc.) com CTA. O corte
    # de streamer pronto vira "dividido" lá embaixo; qualquer outro sai na simples branca.
    estilos = ["simples-branca" for _ in videos]
    slugs = {i["slug"] for i in fila}
    pedido, itens = [], []
    for n, (mp4, estilo) in enumerate(zip(videos, estilos)):
        info = json.loads(mp4.with_suffix(".json").read_text(encoding="utf-8"))
        tema = info.get("tema") if info.get("tema") in CTA else "games"
        if info.get("pronto") == "dividido":
            # Diego, 18/11 19h: corte de streamer sai SÓ com o vídeo (formato dividido), sem título,
            # gancho, frase ou CTA inventados; a legenda só credita o canal de origem (da Twitch).
            canal = (info.get("perfil") or "/").split("/", 1)[1] or "streamer"
            texto = {"titulo": "", "emoji": "", "hashtags": [], "slug": slugify(f"gta6-corte-{canal}"), "fonte": "canal"}
            info["legenda_streamer"] = legenda_streamer(canal)
            estilo = "dividido"
        else:
            texto = gerar_texto(info)
        if texto["fonte"] in ("canal",):
            pass
        elif texto["fonte"] == "padrao" or TIT.generico(texto["titulo"]):
            falas_t = TIT.limpar((info.get("falas") or {}).get("titulo", ""))
            if falas_t and not TIT.generico(falas_t):
                texto = {**texto, "titulo": falas_t, "emoji": (info.get("falas") or {}).get("emoji") or "🎮", "fonte": "gemini-falas"}
            else:
                ctx = TIT.contexto_do_item({"origem": {"perfil": info.get("perfil"), "titulo_clipe": info.get("legenda")}})
                t = TIT.titular(mp4, ctx)
                if not t:
                    print(f"  {mp4.name}: sem título que diga o que acontece; espera a próxima rodada")
                    continue
                texto = {**texto, "titulo": t["titulo"], "emoji": t["emoji"], "fonte": "gemini-regra"}
        base = texto["slug"] or slugify(f"{info.get('jogo', 'games')}-{info.get('perfil', '')}")
        slug, k = base or f"motor-{n}", 2
        while slug in slugs or (VIDEOS / f"{slug}.mp4").exists():
            slug, k = f"{base}-{k}", k + 1
        slugs.add(slug)
        if info.get("pronto") == "dividido":
            # corte de live: um dos 3 modelos que o Diego aprovou (18/11), em rodízio
            print(f"  {mp4.name} -> {slug} (dividido, sem texto; {info.get('perfil')})")
            itens.append((mp4, slug, estilo, texto, tema, info))
            continue
        print(f"  {mp4.name} -> {slug} ({estilo}, título {texto['fonte']}): {texto['titulo']}")
        pedido.append({"video": str(mp4), "saida": str(VIDEOS / slug), "estilo": estilo,
                       "cor": CORES[(len(fila) + n) % len(CORES)], "jogo": info.get("jogo", ""),
                       "titulo": texto["titulo"], "frase": CTA[tema], "max_seg": 40})
        itens.append((mp4, slug, estilo, texto, tema, info))
    with tempfile.TemporaryDirectory() as tmp:
        ped, res = Path(tmp) / "pedido.json", Path(tmp) / "resultado.json"
        ped.write_text(json.dumps(pedido, ensure_ascii=False), encoding="utf-8")
        if pedido:
            subprocess.run(["node", str(GERADOR), str(ped), str(res)], check=False)
        resultado = json.loads(res.read_text(encoding="utf-8")) if res.exists() and pedido else []
    for (mp4, slug, estilo, texto, tema, info) in itens:
        if estilo in MODELOS_STREAMER:
            VIDEOS.mkdir(parents=True, exist_ok=True)
            if not montar_streamer(estilo, mp4, info, texto["titulo"], VIDEOS / f"{slug}.mp4"):
                shutil.copy(mp4, VIDEOS / f"{slug}.mp4")  # se o modelo falhar, sai no modelo 1
                itens[itens.index((mp4, slug, estilo, texto, tema, info))] = (mp4, slug, "dividido", texto, tema, info)
            f = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(VIDEOS / f"{slug}.mp4"),
                                "-frames:v", "1", "-q:v", "2", str(VIDEOS / f"{slug}.jpg")], capture_output=True)
            resultado.append({"saida": str(VIDEOS / slug), "ok": f.returncode == 0})
    ok = {r["saida"] for r in resultado if r.get("ok")}
    usados = 0
    for (mp4, slug, estilo, texto, tema, info) in itens:
        if str(VIDEOS / slug) not in ok:
            print(f"  {slug}: a montagem falhou; o vídeo bruto fica em {mp4.relative_to(ROOT)}")
            continue
        dia, hora = vagas[itens.index((mp4, slug, estilo, texto, tema, info))]
        usados += 1
        fila.append({"slug": slug, "data": dia, "horario": hora, "status": "agendado",
                     "estilo": SIMPLES.get(estilo) or NOME_ESTILO.get(estilo) or MODELOS_STREAMER.get(estilo) or "Dividido",
                     "legenda": info.get("legenda_streamer") or legenda(texto["titulo"], texto["emoji"], tema, texto["hashtags"]),
                     "tentativas": 0,
                     "origem": {"motor": True, "perfil": info.get("perfil"), "link": info.get("link"),
                                "titulo": texto["fonte"], "revisado": False},
                     # etiquetas para a análise semanal (Diego, 10/11)
                     "etiquetas": {"formato": info.get("formato") or "outro", "tema": info.get("tema") or "games",
                                   "jogo": info.get("jogo") or "",
                                   "moldura": estilo if estilo in SIMPLES or estilo in MODELOS_STREAMER else "identidade",
                                   **({"modelo_streamer": estilo} if estilo in MODELOS_STREAMER else {}),
                                   **({"modelo_streamer": info["etiqueta_modelo"]} if info.get("etiqueta_modelo") else {})},
                     "checagem": info.get("checagem")})
        mp4.unlink()
        mp4.with_suffix(".json").unlink()
        mp4.with_name(mp4.stem + "-original.mp4").unlink(missing_ok=True)
        print(f"  {slug}: na fila {dia} {hora}")
    for pasta in ENTRADA.glob("*"):
        if pasta.is_dir() and not any(pasta.iterdir()):
            pasta.rmdir()
    novos_gta = [slug for (_, slug, _, _, tema, _) in itens if tema == "gta6"
                 and any(i["slug"] == slug for i in fila)]
    for a in furar_fila(fila, novos_gta, agora):
        print(" ", a)
    R.salvar(fila)
    print(f"{usados} Reel(s) montado(s) e agendado(s)")
    return 0 if usados or not itens else 1


def passa_na_checagem(mp4: Path) -> bool:
    """Barreira de nudez (Diego, 16/11): o Reel do Eren com titãs levou violação de "Nudez
    ou atividade sexual" em 15/11. Vídeo com risco médio ou alto não entra na fila: o bruto
    é apagado e o motivo fica em social/reels/barrados.json. Grava o resultado no .json do
    bruto para a fila guardar (item["checagem"])."""
    meta = mp4.with_suffix(".json")
    info = json.loads(meta.read_text(encoding="utf-8"))
    chk = SEG.checagem(mp4, info.get("legenda_completa") or info.get("legenda") or "")
    print(f"  {mp4.name}: risco de nudez {chk['risco']} ({chk['por']}): {chk['motivo']}")
    if SEG.barrar(chk["risco"]):
        SEG.registrar_barrado({"slug": None, "bruto": mp4.name, "link": info.get("link"),
                               "perfil": info.get("perfil"), "legenda": info.get("legenda") or "", **chk})
        print(f"  AVISO: {mp4.name} barrado (risco de violação de nudez); bruto apagado")
        mp4.unlink()
        meta.unlink()
        return False
    info["checagem"] = chk
    meta.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def furar_fila(fila: list[dict], novos: list[str], agora: datetime | None = None) -> list[str]:
    """Lançamento do GTA 6 (Diego, 10/11): de 18 a 22/11 a cena nova do jogo não pode
    esperar 2 dias atrás do estoque. Os Reels novos de GTA 6 passam para os primeiros
    horários livres e os do motor que já estavam agendados andam para trás, na mesma
    ordem. Só mexe em Reels do motor: os que o Diego mandou ficam no horário combinado, e os
    marcados "fixo" (memes da virada, 18/11) também não andam."""
    agora = agora or datetime.now(TZ)
    if not R.lancamento(agora.date()) or not novos:
        return []
    futuros = sorted((i for i in fila if i["status"] == "agendado" and (i.get("origem") or {}).get("motor")
                      and not i.get("fixo") and R.quando(i) > agora + FOLGA), key=R.quando)
    vagas = [(i["data"], i["horario"]) for i in futuros]
    frente = [i for i in futuros if i["slug"] in novos]
    ordem = frente + [i for i in futuros if i["slug"] not in novos]
    avisos = []
    for item, (d, h) in zip(ordem, vagas):
        if (item["data"], item["horario"]) != (d, h):
            if item["slug"] in novos:
                avisos.append(f"{item['slug']}: furou a fila, sai {d} {h}")
            item.update(data=d, horario=h)
    return avisos


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
