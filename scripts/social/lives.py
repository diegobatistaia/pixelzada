"""Cortes das lives para o lançamento do GTA 6 (Diego, 10/11).

A plateia de cada live cria "clipes" dos melhores momentos. A partir das 8h de 18/11
(o jogo libera na Nova Zelândia), toda rodada da pesquisa (de 30 em 30 min) pega os
clipes de GTA 6 mais vistos das últimas horas na Twitch (API oficial, grátis) e, quando
der, na Kick. Cada clipe passa pelo recorte da câmera do streamer (scripts/social/rosto.py:
só a imagem do jogo; se não der para tirar o rosto, o clipe é descartado) e cai em
social/reels/entrada/, de onde a montagem de sempre põe na identidade e agenda. No pico
(18 a 22/11) o Reel novo de GTA 6 fura a fila (montagem.furar_fila).

Tudo fica no bloco `lives` de social/pesquisa/config.yaml. Chave da Twitch: secrets
TWITCH_CLIENT_ID_PIXELZADA e TWITCH_CLIENT_SECRET_PIXELZADA (app grátis em dev.twitch.tv).

No GitHub Actions:

    python -m scripts.social.lives rodada            só age dentro do período do config
    python -m scripts.social.lives teste [JOGO]      ensaio: procura clipes (padrão GTA 5),
                                                     baixa e corta 3, sem pôr na fila; grava
                                                     o resultado em social/pesquisa/lives-teste.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import pesquisa as Q
from . import rosto

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

    def clipes(self, desde: datetime, game_id: str, canais: list[str]) -> list[dict]:
        achados = {}
        for c in self.get("clips", game_id=game_id, started_at=_rfc(desde), first=100).get("data", []):
            achados[c["id"]] = c
        if canais:
            ids = self.get("users", login=canais[:100]).get("data", [])
            for u in ids:
                for c in self.get("clips", broadcaster_id=u["id"], started_at=_rfc(desde), first=50).get("data", []):
                    if c.get("game_id") == game_id:
                        achados[c["id"]] = {**c, "_favorito": True}
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
def nota(c: dict) -> float:
    return c["views"] * (3 if c.get("favorito") else 1)


def escolher(cfg: dict, clipes: list[dict], ja: set[str]) -> list[dict]:
    lv = cfg["lives"]
    dmin, dmax = lv.get("duracao", [8, 60])
    bons = [c for c in clipes if c["id"] not in ja and c["link"] not in ja
            and dmin <= (c["duracao"] or dmin) <= dmax and c["views"] >= lv.get("min_views", 0)]
    return sorted(bons, key=nota, reverse=True)


def baixar_e_limpar(c: dict, destino: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        bruto = Path(tmp) / "bruto.mp4"
        r = subprocess.run(["yt-dlp", "--quiet", "--no-warnings", "-f", "mp4/bv*+ba/b", "--merge-output-format", "mp4",
                            "-o", str(bruto), c["link"]], capture_output=True, text=True, timeout=300)
        if not bruto.exists() or bruto.stat().st_size < 20000:
            return {"ok": False, "motivo": f"download falhou: {(r.stderr or r.stdout).strip()[-160:]}"}
        destino.parent.mkdir(parents=True, exist_ok=True)
        return rosto.limpar(bruto, destino)


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
            clipes += tw.clipes(desde, gid, lv.get("canais_twitch") or [])
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
    for c in fila:
        if feitos >= lv.get("por_rodada", 2) or tentados >= 3 * lv.get("por_rodada", 2):
            break
        tentados += 1
        destino = nome_arquivo(pasta, 90 + tentados, c)
        r = baixar_e_limpar(c, destino)
        ja.update({c["id"], c["link"]})  # descartado também não volta
        print(f"  {c['fonte']} {c['canal']} ({c['views']} views): {r['motivo']}")
        if r["ok"]:
            destino.with_suffix(".json").write_text(json.dumps(info_entrada(cfg, c), ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
            feitos += 1
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
        clipes = tw.clipes(agora - timedelta(hours=lv.get("janela_horas", 3)), gid, lv.get("canais_twitch") or []) if gid else []
    except Falha as e:
        print(f"twitch: {e}")
    kick = clipes_kick(lv.get("canais_kick") or [], jogo, agora - timedelta(days=1))
    fila = escolher(cfg, clipes + kick, set())
    resultado = {"em": agora.isoformat(timespec="seconds"), "jogo": jogo, "twitch": len(clipes), "kick": len(kick),
                 "clipes": []}
    with tempfile.TemporaryDirectory() as tmp:
        for c in fila[:3]:
            r = baixar_e_limpar(c, Path(tmp) / "saida.mp4")
            resultado["clipes"].append({**{k: c[k] for k in ("fonte", "canal", "views", "duracao", "titulo", "link")}, **r})
            print(f"  {c['canal']} ({c['views']} views): {r['motivo']}")
    (cfg["_pasta"] / "lives-teste.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
    return 0 if resultado["clipes"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(Q.CONFIG_PADRAO))
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rodada")
    r.add_argument("--forcar", action="store_true")
    t = sub.add_parser("teste")
    t.add_argument("jogo", nargs="?", default="Grand Theft Auto V")
    args = ap.parse_args(argv)
    cfg = Q.carregar_config(Path(args.config))
    if args.cmd == "rodada":
        return rodada(cfg, args.forcar)
    return teste(cfg, args.jogo)


if __name__ == "__main__":
    sys.exit(main())
