"""TikTok e YouTube Shorts do @pixelzada.br pelo Buffer (Diego, 11/11).

Depois que o Reel sai no Instagram, o mesmo vídeo (já público em pixelzada.com.br/ig/reel-<slug>/)
vai para o TikTok e para o YouTube Shorts pela API do Buffer (api.buffer.com, GraphQL).
Chave: segredo BUFFER_TOKEN_PIXELZADA. Configuração: social/reels/buffer.json.

    python -m scripts.social.buffer teste      lista contas e canais e grava os ids em buffer.json
    python -m scripts.social.buffer publicar   manda o Reel do pedido atual (social/saida/pedido-reel.json)
    python -m scripts.social.buffer enviar SLUG manda um Reel já publicado no Instagram (teste à mão)
    python -m scripts.social.buffer conferir   busca o link dos posts já enviados (1 consulta por rede)

Regras:
- Plano grátis: 1.000 pedidos por rede a cada 30 dias. Cada vídeo gasta 1 pedido por rede; a
  conferência busca vários posts de uma vez. O contador fica em buffer.json ("uso").
- YouTube só recebe vídeo próprio (sem "origem.link"): vídeo de outro perfil ou corte de streamer
  derruba alcance (regra de 01/10/2026 dos Shorts) e pode levar aviso de direitos.
- TikTok: no máximo 5 hashtags.
- Falha no Buffer nunca atrapalha o Instagram: o passo roda depois e não derruba a rodada.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import timedelta

from . import instagram as IG, reels as R

API = "https://api.buffer.com"
CONFIG = R.PASTA / "buffer.json"
REDES = ("tiktok", "youtube")


class BufferError(RuntimeError):
    pass


def config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}


def salvar_config(cfg: dict) -> None:
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def contar(cfg: dict, rede: str, n: int = 1) -> None:
    mes = IG.agora().strftime("%Y-%m")
    uso = cfg.setdefault("uso", {})
    if uso.get("mes") != mes:
        uso.clear()
        uso["mes"] = mes
    uso[rede] = uso.get(rede, 0) + n


def gql(query: str, variables: dict | None = None) -> dict:
    token = os.environ.get("BUFFER_TOKEN_PIXELZADA")
    if not token:
        raise BufferError("falta o segredo BUFFER_TOKEN_PIXELZADA")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    for tentativa in range(3):
        req = urllib.request.Request(API, data=body, method="POST", headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json",
            "User-Agent": "pixelzada-bot"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                dados = json.loads(r.read())
        except urllib.error.HTTPError as e:
            texto = e.read().decode(errors="replace")[:500]
            if e.code == 429 and tentativa < 2:
                time.sleep(min(int(e.headers.get("Retry-After") or 30), 120))
                continue
            raise BufferError(f"HTTP {e.code}: {texto}")
        if dados.get("errors"):
            raise BufferError(json.dumps(dados["errors"], ensure_ascii=False)[:800])
        return dados["data"]
    raise BufferError("limite de pedidos do Buffer (429)")


# ---------------------------------------------------------------- teste

TIPOS = ["ShareMode", "SchedulingType", "PostStatus", "Service", "YoutubePrivacy", "YoutubeLicense",
         "CreatePostInput", "PostInputMetaData", "YoutubePostMetadataInput", "TikTokPostMetadataInput",
         "AssetInput", "VideoAssetInput", "PostActionPayload", "PostsFiltersInput", "PostInput"]


def _tipo(nome: str) -> str:
    q = """query T($n: String!) { __type(name: $n) { kind enumValues { name }
             inputFields { name type { kind name ofType { kind name ofType { name } } } }
             possibleTypes { name } } }"""
    try:
        t = gql(q, {"n": nome})["__type"]
    except BufferError as e:
        return f"(erro: {e})"
    if not t:
        return "(não existe)"
    if t.get("enumValues"):
        return ", ".join(v["name"] for v in t["enumValues"])
    if t.get("possibleTypes"):
        return " | ".join(v["name"] for v in t["possibleTypes"])

    def nome_tipo(x):
        if not x:
            return "?"
        if x.get("kind") == "NON_NULL":
            return nome_tipo(x.get("ofType")) + "!"
        if x.get("kind") == "LIST":
            return "[" + nome_tipo(x.get("ofType")) + "]"
        return x.get("name") or "?"
    try:
        return ", ".join(f"{c['name']}: {nome_tipo(c['type'])}" for c in t.get("inputFields") or [])
    except Exception as e:  # o teste nunca para por causa do formato
        return f"(erro ao ler: {e}) {json.dumps(t)[:400]}"


def cmd_teste(args) -> int:
    cfg = config()
    orgs = gql("query { account { organizations { id name } } }")["account"]["organizations"]
    print("organizações:", json.dumps(orgs, ensure_ascii=False))
    canais = []
    for o in orgs:
        cs = gql("""query C($o: OrganizationId!) { channels(input: { organizationId: $o }) {
                      id name displayName service isDisconnected isQueuePaused } }""", {"o": o["id"]})["channels"]
        canais += [dict(c, org=o["id"]) for c in cs]
    for c in canais:
        print(f"canal: {c['service']:<12} {c.get('displayName') or c['name']}  id={c['id']}"
              f"{'  DESCONECTADO' if c.get('isDisconnected') else ''}")
    for rede in REDES:
        c = next((c for c in canais if rede in str(c["service"]).lower()), None)
        if c:
            cfg.setdefault("canais", {})[rede] = {"id": c["id"], "nome": c.get("displayName") or c["name"]}
            cfg["organizacao"] = c["org"]
        else:
            print(f"AVISO: nenhum canal de {rede} conectado no Buffer")
    print("\ntipos da API:")
    for t in TIPOS:
        print(f"  {t}: {_tipo(t)}")
    cfg.setdefault("ativo", False)
    salvar_config(cfg)
    return 0


# ---------------------------------------------------------------- textos

def _so_5_hashtags(texto: str) -> str:
    vistas = 0

    def troca(m):
        nonlocal vistas
        vistas += 1
        return m.group(0) if vistas <= 5 else ""
    out = re.sub(r"(?<!\w)#\w+", troca, texto)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", out)).strip()


def texto_tiktok(item: dict) -> str:
    # No TikTok o @ é outro (conta "pixelzadabr0"): a chamada fica sem o @ do Instagram.
    t = re.sub(r"Segue @pixelzada\.br", "Segue o perfil", item["legenda"])
    return _so_5_hashtags(t)[:2200]


def texto_youtube(item: dict) -> str:
    t = re.sub(r"Segue @pixelzada\.br", "Se inscreve no canal", item["legenda"])
    return (t + ("" if "#shorts" in t.lower() else " #Shorts"))[:4900]


def titulo_youtube(item: dict) -> str:
    linha = next((l for l in item["legenda"].splitlines() if l.strip()), item["slug"])
    linha = re.sub(r"[<>]", "", re.sub(r"(?<!\w)#\w+", "", linha)).strip()
    if len(linha) > 88:
        linha = linha[:87].rsplit(" ", 1)[0] + "…"
    return f"{linha} #Shorts"


def _gta6(item: dict) -> bool:
    et = item.get("etiquetas") or {}
    return et.get("tema") == "gta6" or "gta6" in item["slug"].replace("-", "") or "GTA 6" in str(et.get("jogo", ""))


def vai_para(item: dict, rede: str, cfg: dict) -> bool:
    """youtube_terceiros: false = só vídeo próprio; "gta6" = próprios + de outros perfis só de GTA 6; true = todos."""
    if rede != "youtube" or not (item.get("origem") or {}).get("link"):
        return True
    modo = cfg.get("youtube_terceiros")
    return modo is True or (modo == "gta6" and _gta6(item))


# ---------------------------------------------------------------- envio

CRIAR = """mutation P($input: CreatePostInput!) { createPost(input: $input) {
  ... on PostActionSuccess { post { id status dueAt externalLink } }
  ... on MutationError { message } } }"""


def _entrada(item: dict, rede: str, cfg: dict, video: str) -> dict:
    canal = cfg["canais"][rede]["id"]
    agora_ = IG.agora()
    entrada = {"channelId": canal, "schedulingType": "automatic", "assets": [{"video": {"url": video}}]}
    modo = cfg.get("modo", "shareNow")
    entrada["mode"] = modo
    if modo == "customScheduled":
        entrada["dueAt"] = (agora_ + timedelta(minutes=2)).astimezone(IG.P.TZ).isoformat()
    if cfg.get("needsApproval", True):
        entrada["needsApproval"] = False
    if rede == "tiktok":
        entrada["text"] = texto_tiktok(item)
    else:
        entrada["text"] = texto_youtube(item)
        entrada["metadata"] = {"youtube": {"title": titulo_youtube(item), "categoryId": "20",
                                           "madeForKids": False, "notifySubscribers": True}}
    return entrada


def enviar(item: dict, video: str, cfg: dict) -> dict:
    """Manda o Reel para cada rede que ainda não recebeu. Devolve {rede: resultado}."""
    res = {}
    redes = item.setdefault("redes", {})
    for rede in REDES:
        if rede not in cfg.get("canais", {}) or (redes.get(rede) or {}).get("post_id"):
            continue
        if rede in (cfg.get("pausadas") or []):
            # Diego, 13/11: TikTok pausado para aquecer a conta (vídeos zerados com 16 envios/dia).
            # Fica marcado como pulado para não despejar a fila atrasada quando a rede voltar.
            redes[rede] = {"pulado": "rede pausada (buffer.json: pausadas)"}
            continue
        if not vai_para(item, rede, cfg):
            redes[rede] = {"pulado": "vídeo de outro perfil"}
            continue
        usados = (cfg.get("uso") or {}).get(rede, 0) if (cfg.get("uso") or {}).get("mes") == IG.agora().strftime("%Y-%m") else 0
        if usados >= cfg.get("limite_mes", 980):
            # Plano grátis: 1.000 pedidos por rede a cada 30 dias. Para antes do teto e avisa no painel.
            redes[rede] = {"pulado": f"limite do mês no Buffer ({usados} pedidos)"}
            print(f"AVISO {rede}: limite do mês no Buffer ({usados})")
            continue
        t = IG.agora().isoformat(timespec="seconds")
        try:
            contar(cfg, rede)
            r = gql(CRIAR, {"input": _entrada(item, rede, cfg, video)})["createPost"]
            if "post" not in r:
                raise BufferError(r.get("message") or json.dumps(r, ensure_ascii=False))
            redes[rede] = {"post_id": r["post"]["id"], "em": t, "status": r["post"].get("status"),
                           "link": r["post"].get("externalLink")}
            print(f"{rede}: enviado ao Buffer (post {r['post']['id']}, {r['post'].get('status')})")
        except BufferError as e:
            n = (redes.get(rede) or {}).get("tentativas", 0) + 1
            redes[rede] = {"erro": str(e)[:500], "em": t, "tentativas": n}
            print(f"ERRO {rede}: {e}")
        res[rede] = redes[rede]
    return res


def cmd_publicar(args) -> int:
    cfg = config()
    if not cfg.get("ativo"):
        print("Buffer desligado (buffer.json: ativo=false)")
        return 0
    pedido = json.loads(R.PEDIDO.read_text(encoding="utf-8"))
    fila = R.carregar()
    item = next(i for i in fila if i["slug"] == pedido["slug"])
    if item.get("status") != "publicado":
        print("o Reel não saiu no Instagram; nada vai para o Buffer")
        return 0
    res = enviar(item, IG.url_publica(pedido["pasta"], "video.mp4"), cfg)
    R.salvar(fila)
    salvar_config(cfg)
    return 1 if any("erro" in r for r in res.values()) else 0


def cmd_enviar(args) -> int:
    cfg = config()
    fila = R.carregar()
    item = next(i for i in fila if i["slug"] == args.slug)
    video = IG.url_publica(f"reel-{item['slug']}", "video.mp4")
    IG.conferir_urls([video])
    res = enviar(item, video, cfg)
    R.salvar(fila)
    salvar_config(cfg)
    return 1 if any("erro" in r for r in res.values()) else 0


LISTAR = """query L($o: OrganizationId!, $c: [ChannelId!]) {
  posts(first: 50, input: { organizationId: $o, filter: { channelIds: $c } }) {
    edges { node { id status sentAt externalLink error { message } } } } }"""


def cmd_conferir(args) -> int:
    cfg = config()
    fila = R.carregar()
    abertos = {}
    for i in fila:
        for rede, r in (i.get("redes") or {}).items():
            if r.get("post_id") and not r.get("link"):
                abertos[r["post_id"]] = (i, rede)
    if not abertos:
        print("nada para conferir")
        return 0
    redes = sorted({rede for _, rede in abertos.values()})
    ids = [cfg["canais"][r]["id"] for r in redes]
    for r in redes:
        contar(cfg, r)
    nodes = [e["node"] for e in gql(LISTAR, {"o": cfg["organizacao"], "c": ids})["posts"]["edges"]]
    for n in nodes:
        if n["id"] in abertos:
            item, rede = abertos[n["id"]]
            reg = item["redes"][rede]
            reg["status"] = n.get("status")
            if n.get("externalLink"):
                reg["link"] = n["externalLink"]
            if n.get("sentAt"):
                reg["saiu"] = n["sentAt"]
            if n.get("error"):
                reg["erro"] = n["error"]["message"]
            print(f"{rede} {item['slug']}: {reg.get('status')} {reg.get('link') or reg.get('erro') or ''}")
    R.salvar(fila)
    salvar_config(cfg)
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("teste")
    sub.add_parser("publicar")
    sub.add_parser("conferir")
    e = sub.add_parser("enviar")
    e.add_argument("slug")
    args = ap.parse_args(argv)
    return {"teste": cmd_teste, "publicar": cmd_publicar, "conferir": cmd_conferir, "enviar": cmd_enviar}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
