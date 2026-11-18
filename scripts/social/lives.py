"""Cortes das lives para o lançamento do GTA 6 (Diego, 10/11).

A plateia de cada live cria "clipes" dos melhores momentos. A partir das 8h de 18/11
(o jogo libera na Nova Zelândia), toda rodada da pesquisa (de 30 em 30 min) pega os
clipes de GTA 6 mais vistos das últimas horas na Twitch (API oficial, grátis) e, quando
der, na Kick. Com lives.formato = dividido (Diego, 18/11) o clipe já sai pronto: câmera do
streamer em cima, jogo embaixo, sem moldura (camera_ia.dividir); sem isso, passa pelo recorte
da câmera (rosto.py + camera_ia.limpar). Cai em social/reels/entrada/ e a montagem agenda. No pico
(18 a 22/11) o Reel novo de GTA 6 fura a fila (montagem.furar_fila).

Tudo fica no bloco `lives` de social/pesquisa/config.yaml. Chave da Twitch: secrets
TWITCH_CLIENT_ID_PIXELZADA e TWITCH_CLIENT_SECRET_PIXELZADA (app grátis em dev.twitch.tv).

No GitHub Actions:

    python -m scripts.social.lives rodada            só age dentro do período do config
    python -m scripts.social.lives teste [JOGO]      ensaio: procura clipes (padrão GTA 5),
                                                     baixa e corta 3, sem pôr na fila; grava
                                                     o resultado em social/pesquisa/lives-teste.json
    python -m scripts.social.lives canais [LOGINS]   confere os canais (existe, ao vivo, clipes de
                                                     GTA nos últimos 30 dias) e lista quem faz mais
                                                     clipes de GTA em português; grava
                                                     social/pesquisa/lives-canais.json
    python -m scripts.social.lives refazer           refaz no formato dividido os cortes da fila
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
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import pesquisa as Q
from . import camera_ia, rosto

TZ = Q.TZ
UA = "Mozilla/5.0 (compatible; pixelzada-bot)"


class Falha(RuntimeError):
    pass


def _json(url: str, data: bytes | None = None, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise Falha(f"HTTP {e.code} em {url.split('?')[0]}: {e.read().decode('utf-8', 'replace')[:200]}") from e
    except urllib.error.URLError as e:
        raise Falha(f"sem resposta de {url.split('?')[0]}: {e}") from e


def _rfc(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Twitch (API oficial Helix)
# ---------------------------------------------------------------------------
class Twitch:
    def __init__(self):
        self.cid = os.environ.get("TWITCH_CLIENT_ID_PIXELZADA", "").strip()
        segredo = os.environ.get("TWITCH_CLIENT_SECRET_PIXELZADA", "").strip()
        if not self.cid or not segredo:
            raise Falha("as chaves da Twitch (TWITCH_CLIENT_ID_PIXELZADA / TWITCH_CLIENT_SECRET_PIXELZADA) não estão cadastradas")
        corpo = urllib.parse.urlencode({"client_id": self.cid, "client_secret": segredo,
                                        "grant_type": "client_credentials"}).encode()
        self.token = _json("https://id.twitch.tv/oauth2/token", data=corpo)["access_token"]

    def get(self, caminho: str, **params) -> dict:
        q = urllib.parse.urlencode(params, doseq=True)
        return _json(f"https://api.twitch.tv/helix/{caminho}?{q}",
                     headers={"Client-ID": self.cid, "Authorization": f"Bearer {self.token}"})

    def jogo(self, nome: str) -> str | None:
        d = self.get("games", name=nome).get("data") or []
        return d[0]["id"] if d else None

    def ao_vivo(self, game_id: str, idioma: str | None, limite: int = 40) -> list[dict]:
        """Lives no ar agora nesse jogo (filtradas por idioma), da maior para a menor plateia."""
        p = {"game_id": game_id, "first": 100}
        if idioma:
            p["language"] = idioma
        return self.get("streams", **p).get("data", [])[:limite]

    def clipes(self, desde: datetime, game_id: str, canais: list[str], idiomas: list[str] | None = None,
               descobrir: int = 0, idiomas_descobrir: list[str] | None = None) -> list[dict]:
        """Clipes do jogo desde `desde`.

        - geral: os 100 mais vistos da categoria, só nos `idiomas` (vazio = todos);
        - favoritos (`canais`): sempre entram e pesam 3x;
        - descobrir: até N canais no idioma que estão AO VIVO no jogo agora entram na busca
          (assim um streamer brasileiro fora da lista também é achado).
        """
        idiomas = [i.lower() for i in (idiomas or [])]
        achados = {}
        for c in self.get("clips", game_id=game_id, started_at=_rfc(desde), first=100).get("data", []):
            if not idiomas or (c.get("language") or "").lower() in idiomas:
                achados[c["id"]] = c
        logins = [x.lower() for x in canais[:100]]
        favoritos = set(logins)
        if descobrir:
            for idioma in (idiomas_descobrir or idiomas or [None]):
                try:
                    for s in self.ao_vivo(game_id, idioma, descobrir):
                        if s["user_login"].lower() not in logins:
                            logins.append(s["user_login"].lower())
                except Falha as e:
                    print(f"   lives ao vivo: {e}")
        for i in range(0, len(logins), 100):
            for u in self.get("users", login=logins[i:i + 100]).get("data", []):
                fav = u["login"].lower() in favoritos
                for c in self.get("clips", broadcaster_id=u["id"], started_at=_rfc(desde), first=50).get("data", []):
                    if c.get("game_id") == game_id:
                        achados[c["id"]] = {**c, "_favorito": fav}
        return [{"id": f"twitch:{c['id']}", "fonte": "twitch", "link": c["url"], "canal": c["broadcaster_name"],
                 "titulo": c.get("title") or "", "views": c.get("view_count", 0), "duracao": c.get("duration", 0),
                 "idioma": c.get("language"), "criado": c.get("created_at"), "favorito": bool(c.get("_favorito"))}
                for c in achados.values()]


# ---------------------------------------------------------------------------
# Kick (sem API oficial de clipes: tenta o endereço público do site; se recusar, segue sem)
# ---------------------------------------------------------------------------
def clipes_kick(canais: list[str], jogo: str, desde: datetime) -> list[dict]:
    saida = []
    for canal in canais:
        try:
            d = _json(f"https://kick.com/api/v2/channels/{canal}/clips?sort=view&time=day",
                      headers={"Accept": "application/json"})
        except Falha as e:
            print(f"   kick @{canal}: {str(e)[:120]}")
            continue
        for c in d.get("clips", []):
            cat = ((c.get("category") or {}).get("name") or "")
            criado = c.get("created_at") or ""
            try:
                recente = datetime.fromisoformat(criado.replace("Z", "+00:00")) >= desde
            except ValueError:
                recente = True
            if jogo.lower() not in cat.lower() or not recente:
                continue
            link = c.get("video_url") or c.get("clip_url") or f"https://kick.com/{canal}/clips/{c.get('id')}"
            saida.append({"id": f"kick:{c.get('id')}", "fonte": "kick", "link": link, "canal": canal,
                          "titulo": c.get("title") or "", "views": c.get("view_count") or c.get("views") or 0,
                          "duracao": c.get("duration") or 0, "criado": criado, "favorito": True})
    return saida


# ---------------------------------------------------------------------------
# Escolha, download e corte
# ---------------------------------------------------------------------------
PESO_FAVORITO = 3.0


def nota(c: dict) -> float:
    # os melhores primeiro: mais views; favorito pesa PESO_FAVORITO (config lives.peso_favorito);
    # clipe de live em português pesa 2x (público brasileiro)
    return c["views"] * (PESO_FAVORITO if c.get("favorito") else 1) * (2 if (c.get("idioma") or "").startswith("pt") else 1)


def _idiomas_busca(lv: dict) -> list[str]:
    """Idiomas aceitos na busca geral: os principais (pt) e, se houver, os de reserva (en...)."""
    principais = lv.get("idiomas") or []
    return (principais + (lv.get("idiomas_reserva") or [])) if principais else []


def eh_reserva(lv: dict, c: dict) -> bool:
    """Clipe em idioma de reserva (não está nos `idiomas` principais e não é favorito)."""
    principais = [i.lower() for i in (lv.get("idiomas") or [])]
    if not principais or c.get("favorito"):
        return False
    return not any((c.get("idioma") or "").lower().startswith(i) for i in principais)


def escolher(cfg: dict, clipes: list[dict], ja: set[str]) -> list[dict]:
    """Ordem: primeiro TODOS os clipes nos idiomas principais (pt) e dos favoritos; os de
    reserva (en...) só entram depois, para completar a rodada quando falta clipe em português."""
    lv = cfg["lives"]
    global PESO_FAVORITO
    PESO_FAVORITO = float(lv.get("peso_favorito", 3))
    dmin, dmax = lv.get("duracao", [8, 60])
    bons = [c for c in clipes if c["id"] not in ja and c["link"] not in ja
            and dmin <= (c["duracao"] or dmin) <= dmax and c["views"] >= lv.get("min_views", 0)]
    return sorted(bons, key=lambda c: (not eh_reserva(lv, c), nota(c)), reverse=True)


def baixar_e_limpar(c: dict, destino: Path, mutar: bool = False, dividido: bool = False) -> dict:
    """Baixa, tira a câmera do streamer e, se `mutar`, tira o áudio (clipe de reserva em
    outro idioma: fica só a imagem do jogo; a montagem põe trilha muda)."""
    with tempfile.TemporaryDirectory() as tmp:
        bruto = Path(tmp) / "bruto.mp4"
        r = subprocess.run(["yt-dlp", "--quiet", "--no-warnings", "-f", "mp4/bv*+ba/b", "--merge-output-format", "mp4",
                            "-o", str(bruto), c["link"]], capture_output=True, text=True, timeout=120)
        if not bruto.exists() or bruto.stat().st_size < 20000:
            return {"ok": False, "motivo": f"download falhou: {(r.stderr or r.stdout).strip()[-160:]}"}
        destino.parent.mkdir(parents=True, exist_ok=True)
        if dividido:
            # Diego, 18/11: câmera do streamer em cima, jogo embaixo, sem moldura (Reel já pronto)
            res = camera_ia.dividir(bruto, destino)
            if not res["ok"]:
                destino.unlink(missing_ok=True)
                return res
            # Diego aprovou 3 modelos (18/11): o original e as falas ficam ao lado para a montagem
            # escolher o modelo 3 (desfocado + título + fala). Clipe de reserva (outro idioma) não.
            if not mutar:
                shutil.copy(bruto, original_de(destino))
                res["falas"] = camera_ia.transcrever(bruto)
            res["camera"] = bool((res.get("dividido") or {}).get("camera"))
        else:
            res = rosto.limpar(bruto, destino)
        if not dividido and res.get("ok") and destino.exists():
            # 2ª barreira: o Gemini confere se sobrou câmera/pessoa real (na dúvida, descarta)
            ia = camera_ia.limpar(destino)
            if not ia["ok"]:
                destino.unlink(missing_ok=True)
                return {"ok": False, "motivo": f"{res.get('motivo', '')}; {ia['motivo']}"}
            res = {**res, "motivo": f"{res.get('motivo', '')}; {ia['motivo']}", **{k: v for k, v in ia.items() if k == "corte_ia"}}
        if res.get("ok") and mutar and destino.exists():
            mudo = Path(tmp) / "mudo.mp4"
            m = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(destino), "-c:v", "copy", "-an", str(mudo)],
                               capture_output=True, text=True)
            if m.returncode != 0 or not mudo.exists():
                destino.unlink(missing_ok=True)
                return {"ok": False, "motivo": f"tirar o áudio falhou: {m.stderr.strip()[-160:]}"}
            shutil.move(str(mudo), str(destino))
            res = {**res, "motivo": f"{res.get('motivo', '')} (sem áudio: clipe em {c.get('idioma')})".strip()}
        return res


def original_de(mp4: Path) -> Path:
    return mp4.with_name(mp4.stem + "-original.mp4")


def eh_dividido(lv: dict) -> bool:
    return (lv.get("formato") or "") == "dividido"


def refazer(cfg: dict) -> int:
    """Refaz no formato dividido os cortes da Twitch que já estão na fila e ainda não saíram
    (Diego, 18/11). Baixa de novo o clipe original pelo link guardado na fila."""
    from . import reels as R
    fila = R.carregar()
    agora = datetime.now(TZ)
    feitos = 0
    for item in fila:
        o = item.get("origem") or {}
        link = o.get("link") or ""
        if item.get("status") != "agendado" or "twitch.tv" not in link or item.get("estilo") == "Dividido":
            continue
        quando = datetime.fromisoformat(f"{item['data']}T{item['horario']}:00").replace(tzinfo=TZ)
        if quando < agora + timedelta(minutes=4):
            print(f"  {item['slug']}: sai agora ({item['horario']}), não dá tempo")
            continue
        mp4 = R.PASTA / "videos" / f"{item['slug']}.mp4"
        with tempfile.TemporaryDirectory() as tmp:
            novo = Path(tmp) / "novo.mp4"
            c = {"link": link, "idioma": None}
            r = baixar_e_limpar(c, novo, dividido=True)
            print(f"  {item['slug']} ({item['data']} {item['horario']}): {r['motivo']}")
            if not r["ok"] or not novo.exists():
                continue
            shutil.copy(novo, mp4)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(mp4), "-frames:v", "1", "-q:v", "2",
                            str(mp4.with_suffix(".jpg"))], check=False)
        item["estilo"] = "Dividido"
        item.setdefault("etiquetas", {})["moldura"] = "dividido"
        item["checagem"] = None  # a barreira de nudez confere o vídeo novo
        feitos += 1
    R.salvar(fila)
    print(f"{feitos} corte(s) refeito(s) no formato dividido")
    return 0


def modelo(links: list[str]) -> int:
    """Prévias para o Diego escolher o formato: guarda o clipe original e o dividido em
    social/reels/modelos/ (não mexe na fila)."""
    pasta = Q.ROOT / "social" / "reels" / "modelos"
    pasta.mkdir(parents=True, exist_ok=True)
    if links == ["falas"]:  # só a transcrição dos originais que já estão na pasta
        for bruto in sorted(pasta.glob("clipe*-original.mp4")):
            fala = camera_ia.transcrever(bruto)
            print(f"  {bruto.name}: {json.dumps(fala, ensure_ascii=False)[:400]}")
            bruto.with_name(bruto.name.replace("-original.mp4", "-falas.json")).write_text(
                json.dumps(fala, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    if links and links[0].startswith("auto"):
        # os melhores clipes de GTA 6 em português de streamers diferentes (auto ou auto:N)
        quantos = int(links[0].split(":")[1]) if ":" in links[0] else 4
        cfg = Q.carregar_config(Q.CONFIG_PADRAO)
        lv = cfg["lives"]
        clipes = escolher(cfg, procurar(cfg, datetime.now(TZ), lv["jogo_twitch"]), set())
        vistos, links = set(), []
        for c in clipes:
            if c["canal"].lower() in vistos or eh_reserva(lv, c):
                continue
            vistos.add(c["canal"].lower())
            links.append(c["link"])
            print(f"  escolhido: {c['canal']} {c['views']} views {c['titulo']!r} {c['link']}")
            if len(links) >= quantos:
                break
    for n, link in enumerate(links, 1):
        bruto = pasta / f"clipe{n}-original.mp4"
        r = subprocess.run(["yt-dlp", "--quiet", "--no-warnings", "-f", "mp4/bv*+ba/b", "--merge-output-format", "mp4",
                            "-o", str(bruto), link], capture_output=True, text=True, timeout=120)
        if not bruto.exists():
            print(f"  {link}: download falhou {(r.stderr or '')[-160:]}")
            continue
        ia = camera_ia.perguntar(bruto)
        (pasta / f"clipe{n}.json").write_text(json.dumps({"link": link, "canal": link.split("/")[3], **ia}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {link}: {ia}")
        fala = camera_ia.transcrever(bruto)
        print(f"  falas: {json.dumps(fala, ensure_ascii=False)[:400]}")
        (pasta / f"clipe{n}-falas.json").write_text(json.dumps(fala, ensure_ascii=False, indent=2), encoding="utf-8")
        d = camera_ia.dividir(bruto, pasta / f"clipe{n}-dividido.mp4")
        print(f"  dividido: {d['motivo']}")
    return 0


def nome_arquivo(pasta: Path, n: int, c: dict) -> Path:
    canal = re.sub(r"[^a-z0-9]+", "-", c["canal"].lower()).strip("-") or "live"
    return pasta / f"{n:02d}-gta6-{c['fonte']}-{canal}.mp4"


def info_entrada(cfg: dict, c: dict) -> dict:
    leg = re.sub(r"\s+", " ", c["titulo"]).strip()
    return {"numero": 0, "perfil": f"{c['fonte']}/{c['canal']}", "link": c["link"], "jogo": cfg["temas"]["gta6"]["nome"],
            "tema": "gta6", "formato": "gameplay", "legenda": leg[:160],
            "legenda_completa": f"Clipe da live de {c['canal']} jogando GTA 6: {leg}"[:700],
            "horario_sugerido": None, "via": c["fonte"]}


def dentro_do_periodo(cfg: dict, agora: datetime) -> bool:
    lv = cfg.get("lives") or {}
    ini = datetime.fromisoformat(lv["inicio"]).replace(tzinfo=TZ)
    fim = datetime.fromisoformat(lv["fim"]).replace(tzinfo=TZ)
    return ini <= agora <= fim


def procurar(cfg: dict, agora: datetime, jogo: str) -> list[dict]:
    lv = cfg["lives"]
    desde = agora - timedelta(hours=lv.get("janela_horas", 3))
    ini = datetime.fromisoformat(lv["inicio"]).replace(tzinfo=TZ)
    if jogo == lv["jogo_twitch"]:
        desde = max(desde, ini)  # nada gravado antes da liberação oficial (regra da Rockstar)
    clipes = []
    try:
        tw = Twitch()
        gid = tw.jogo(jogo)
        if gid:
            clipes += tw.clipes(desde, gid, lv.get("canais_twitch") or [], _idiomas_busca(lv),
                                lv.get("descobrir_ao_vivo", 0), lv.get("idiomas") or [])
        else:
            print(f"a Twitch ainda não tem a categoria '{jogo}'")
    except Falha as e:
        print(f"twitch: {e}")
    clipes += clipes_kick(lv.get("canais_kick") or [], jogo, desde)
    print(f"{len(clipes)} clipe(s) de '{jogo}' desde {desde.astimezone(TZ):%d/%m %H:%M}")
    return clipes


def rodada(cfg: dict, forcar: bool = False) -> int:
    agora = datetime.now(TZ)
    if not forcar and not dentro_do_periodo(cfg, agora):
        print("fora do período das lives (config.yaml, bloco lives); nada a fazer")
        return 0
    lv = cfg["lives"]
    ja = Q.usados(cfg)
    fila = escolher(cfg, procurar(cfg, agora, lv["jogo_twitch"]), ja)
    pasta = cfg["_entrada"] / agora.date().isoformat()
    feitos, tentados = 0, 0
    limite = time.monotonic() + 60 * lv.get("orcamento_min", 9)
    por_canal: dict[str, int] = {}
    for c in fila:
        if feitos >= lv.get("por_rodada", 2) or tentados >= 3 * lv.get("por_rodada", 2):
            break
        if por_canal.get(c["canal"].lower(), 0) >= lv.get("max_por_canal", 1):
            continue  # variedade: no máximo N clipes do mesmo streamer por rodada
        if time.monotonic() > limite:
            print(f"  tempo da rodada esgotado ({lv.get('orcamento_min', 9)} min): o resto fica para a próxima")
            break
        tentados += 1
        destino = nome_arquivo(pasta, 90 + tentados, c)
        r = baixar_e_limpar(c, destino, mutar=lv.get("mutar_reserva", True) and eh_reserva(lv, c),
                            dividido=eh_dividido(lv))
        ja.update({c["id"], c["link"]})  # descartado também não volta
        print(f"  {c['fonte']} {c['canal']} ({c['views']} views): {r['motivo']}")
        if r["ok"]:
            info = info_entrada(cfg, c)
            if eh_dividido(lv):
                info["pronto"] = "dividido"  # a montagem escolhe um dos 3 modelos do Diego
                info["camera"] = r.get("camera", True)
                if r.get("falas"):
                    info["falas"] = r["falas"]
            destino.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
            feitos += 1
            por_canal[c["canal"].lower()] = por_canal.get(c["canal"].lower(), 0) + 1
        Q.salvar_usados(cfg, ja)  # a cada clipe: se o job for cortado, o que já foi tentado não volta
    Q.salvar_usados(cfg, ja)
    print(f"{feitos} clipe(s) de live pronto(s) para a montagem")
    return 0


def teste(cfg: dict, jogo: str) -> int:
    """Ensaio (ex.: com GTA 5): procura, baixa e corta 3 clipes sem pôr na fila."""
    agora = datetime.now(TZ)
    lv = cfg["lives"]
    clipes = []
    try:
        tw = Twitch()
        gid = tw.jogo(jogo)
        clipes = tw.clipes(agora - timedelta(hours=lv.get("janela_horas", 3)), gid, lv.get("canais_twitch") or [],
                           _idiomas_busca(lv), lv.get("descobrir_ao_vivo", 0), lv.get("idiomas") or []) if gid else []
    except Falha as e:
        print(f"twitch: {e}")
    kick = clipes_kick(lv.get("canais_kick") or [], jogo, agora - timedelta(days=1))
    fila = escolher(cfg, clipes + kick, set())
    resultado = {"em": agora.isoformat(timespec="seconds"), "jogo": jogo, "twitch": len(clipes), "kick": len(kick),
                 "clipes": []}
    fotos = cfg["_pasta"] / "lives-teste"
    shutil.rmtree(fotos, ignore_errors=True)
    fotos.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        limite = time.monotonic() + 60 * lv.get("orcamento_min", 9)
        for n, c in enumerate(fila[:6], 1):
            if time.monotonic() > limite:
                print("  tempo do ensaio esgotado")
                break
            saida = Path(tmp) / f"saida-{n}.mp4"
            r = baixar_e_limpar(c, saida, mutar=lv.get("mutar_reserva", True) and eh_reserva(lv, c))
            if saida.exists():  # quadro do meio, para conferir o corte a olho
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(max(1, (c["duracao"] or 10) / 2)),
                                "-i", str(saida), "-frames:v", "1", "-vf", "scale=640:-2", str(fotos / f"{n}.jpg")])
            resultado["clipes"].append({"n": n, **{k: c[k] for k in ("fonte", "canal", "views", "duracao", "titulo", "link")}, **r})
            print(f"  {c['canal']} ({c['views']} views): {r['motivo']}")
    (cfg["_pasta"] / "lives-teste.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
    return 0 if resultado["clipes"] else 1


def canais(cfg: dict, logins: list[str], jogos: list[str], dias: int = 30) -> int:
    """Confere na API oficial cada canal da lista: existe? está ao vivo? quantos clipes fez
    nos últimos `dias` dias nos `jogos` (ex.: GTA 5) e quantas views. Também lista quem faz
    mais clipes em português nesses jogos (para achar canais que faltam).
    Resultado em social/pesquisa/lives-canais.json."""
    agora = datetime.now(TZ)
    desde = agora - timedelta(days=dias)
    lv = cfg["lives"]
    logins = [x.strip().lower().lstrip("@") for x in (logins or lv.get("canais_twitch") or []) if x.strip()]
    tw = Twitch()
    gids = {}
    for j in jogos:
        gid = tw.jogo(j)
        gids[j] = gid
        print(f"categoria '{j}': {gid or 'não existe ainda'}")
    usuarios = {}
    for i in range(0, len(logins), 100):
        for u in tw.get("users", login=logins[i:i + 100]).get("data", []):
            usuarios[u["login"].lower()] = u
    no_ar = {}
    ids = [u["id"] for u in usuarios.values()]
    for i in range(0, len(ids), 100):
        for s in tw.get("streams", user_id=ids[i:i + 100], first=100).get("data", []):
            no_ar[s["user_login"].lower()] = s
    linhas = []
    for login in logins:
        u = usuarios.get(login)
        if not u:
            linhas.append({"login": login, "existe": False})
            print(f"  {login}: NÃO EXISTE na Twitch")
            continue
        info = (tw.get("channels", broadcaster_id=u["id"]).get("data") or [{}])[0]
        seguidores = None
        try:
            seguidores = tw.get("channels/followers", broadcaster_id=u["id"], first=1).get("total")
        except Falha:
            pass
        clipes, cursor = [], None
        for _ in range(5):  # até 500 clipes do período
            p = {"broadcaster_id": u["id"], "started_at": _rfc(desde), "first": 100}
            if cursor:
                p["after"] = cursor
            d = tw.get("clips", **p)
            clipes += d.get("data", [])
            cursor = (d.get("pagination") or {}).get("cursor")
            if not cursor:
                break
        por_jogo = {j: [c for c in clipes if gid and c.get("game_id") == gid] for j, gid in gids.items()}
        s = no_ar.get(login)
        linha = {"login": login, "existe": True, "nome": u["display_name"], "tipo": u.get("broadcaster_type"),
                 "criado": u.get("created_at", "")[:10], "descricao": (u.get("description") or "")[:160], "titulo_live": (info.get("title") or "")[:100], "idioma": info.get("broadcaster_language"),
                 "ultimo_jogo": info.get("game_name"), "seguidores": seguidores,
                 "ao_vivo": bool(s), "ao_vivo_jogo": s and s.get("game_name"), "ao_vivo_plateia": s and s.get("viewer_count"),
                 "clipes_periodo": len(clipes), "views_clipes_periodo": sum(c.get("view_count", 0) for c in clipes),
                 "por_jogo": {j: {"clipes": len(v), "views": sum(c.get("view_count", 0) for c in v),
                                  "melhor": max((c.get("view_count", 0) for c in v), default=0)}
                              for j, v in por_jogo.items()}}
        linhas.append(linha)
        print(f"  {login}: {linha['clipes_periodo']} clipes em {dias}d; "
              + "; ".join(f"{j}: {v['clipes']} clipes/{v['views']} views" for j, v in linha["por_jogo"].items())
              + f"; último jogo: {linha['ultimo_jogo']}; ao vivo: {linha['ao_vivo_jogo'] or '-'}")
    # Descoberta: quem mais gera clipes em português nesses jogos (últimos 7 dias) e quem está no ar agora
    descoberta = {}
    for j, gid in gids.items():
        if not gid:
            continue
        cont, cursor = {}, None
        for _ in range(10):  # até 1.000 clipes mais vistos da semana
            p = {"game_id": gid, "started_at": _rfc(agora - timedelta(days=7)), "first": 100}
            if cursor:
                p["after"] = cursor
            d = tw.get("clips", **p)
            for c in d.get("data", []):
                if (c.get("language") or "").lower() != "pt":
                    continue
                k = c["broadcaster_name"]
                x = cont.setdefault(k, {"canal": k, "clipes": 0, "views": 0})
                x["clipes"] += 1
                x["views"] += c.get("view_count", 0)
            cursor = (d.get("pagination") or {}).get("cursor")
            if not cursor:
                break
        try:
            vivos = [{"canal": s["user_login"], "plateia": s["viewer_count"], "titulo": s["title"][:80]}
                     for s in tw.ao_vivo(gid, "pt", 30)]
        except Falha as e:
            vivos = [{"erro": str(e)[:120]}]
        descoberta[j] = {"clipes_pt_7d": sorted(cont.values(), key=lambda x: x["views"], reverse=True)[:40],
                         "ao_vivo_pt_agora": vivos}
    resultado = {"em": agora.isoformat(timespec="seconds"), "dias": dias, "jogos": gids, "canais": linhas,
                 "descoberta": descoberta}
    (cfg["_pasta"] / "lives-canais.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                                                     encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(Q.CONFIG_PADRAO))
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rodada")
    r.add_argument("--forcar", action="store_true")
    t = sub.add_parser("teste")
    t.add_argument("jogo", nargs="?", default="Grand Theft Auto V")
    k = sub.add_parser("canais")
    k.add_argument("logins", nargs="*", help="logins da Twitch (vazio = favoritos do config)")
    k.add_argument("--jogos", default="Grand Theft Auto V|Grand Theft Auto VI")
    k.add_argument("--dias", type=int, default=30)
    sub.add_parser("refazer", help="refaz no formato dividido os cortes da Twitch que estão na fila")
    mo = sub.add_parser("modelo", help="prévias do formato com clipes da Twitch (não mexe na fila)")
    mo.add_argument("links", nargs="+")
    args = ap.parse_args(argv)
    cfg = Q.carregar_config(Path(args.config))
    if args.cmd == "rodada":
        return rodada(cfg, args.forcar)
    if args.cmd == "modelo":
        return modelo(args.links)
    if args.cmd == "refazer":
        return refazer(cfg)
    if args.cmd == "canais":
        return canais(cfg, args.logins, [j for j in args.jogos.split("|") if j], args.dias)
    return teste(cfg, args.jogo)


if __name__ == "__main__":
    sys.exit(main())
