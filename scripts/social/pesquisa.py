"""Motor de pesquisa de vídeos dos concorrentes (Reels).

Todo dia ele lê os posts recentes dos perfis concorrentes pela API oficial do
Instagram (Business Discovery), mede quais vídeos foram muito acima da média do
próprio perfil, monta a lista do dia com links e horário sugerido, e baixa
sozinho os vídeos que o Diego escolher. Depois disso o fluxo de Reels de sempre
(moldura v4, fila.json, publicação) segue igual.

Tudo o que é da marca fica em social/pesquisa/config.yaml. Para outra marca,
copie o arquivo e passe --config.

No GitHub Actions (.github/workflows/pesquisa.yml), que tem internet e a chave:

    python -m scripts.social.pesquisa teste             confere a chave e lê 1 perfil
    python -m scripts.social.pesquisa coletar [--forcar] coleta + lista do dia
    python -m scripts.social.pesquisa baixar DATA 1,4,7  baixa os escolhidos da lista

Na sessão do Claude (sem chave, sem internet):

    python -m scripts.social.pesquisa lista [DATA]      mostra a lista do dia
    python -m scripts.social.pesquisa analisar ARQUIVO  refaz a lista a partir de uma coleta salva
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
TZ = ZoneInfo("America/Sao_Paulo")
CONFIG_PADRAO = ROOT / "social" / "pesquisa" / "config.yaml"
CAMPOS_POST = ["id", "caption", "media_type", "media_product_type", "permalink", "timestamp",
               "like_count", "comments_count", "view_count", "media_url", "thumbnail_url"]


class ApiError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
def carregar_config(caminho: Path, hoje: date | None = None) -> dict:
    """Lê o config e aplica o modo lançamento quando a data chegar."""
    import yaml
    cfg = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    hoje = hoje or datetime.now(TZ).date()
    lanc = cfg.get("lancamento") or {}
    cfg["em_lancamento"] = bool(lanc.get("desde")) and hoje >= date.fromisoformat(str(lanc["desde"]))
    if cfg["em_lancamento"]:
        for chave in ("coletas", "janela_horas", "lista_tamanho"):
            if chave in lanc:
                cfg[chave] = lanc[chave]
        for tema, peso in (lanc.get("pesos") or {}).items():
            cfg["temas"][tema]["peso"] = peso
    cfg["_pasta"] = ROOT / cfg.get("pasta", "social/pesquisa")
    cfg["_entrada"] = ROOT / cfg.get("entrada", "social/reels/entrada")
    return cfg


# ---------------------------------------------------------------------------
# API oficial (login do Facebook, graph.facebook.com)
# ---------------------------------------------------------------------------
def call(api: str, path: str, token: str, **params) -> dict:
    params["access_token"] = token
    url = f"{api}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")
        # Nunca imprimir a URL: ela carrega a chave. Só o corpo do erro sai.
        raise ApiError(f"HTTP {e.code} em {path.split('?')[0]}: {corpo[:400]}") from None
    except urllib.error.URLError as e:
        raise ApiError(f"sem resposta de {path.split('?')[0]}: {e.reason}") from None


def conta(cfg: dict) -> tuple[str, str]:
    """Chave e id do perfil profissional da marca. Aceita chave de Página ou de usuário."""
    token = os.environ.get(cfg["segredo"], "").strip()
    if not token:
        raise ApiError(f"o secret {cfg['segredo']} não está cadastrado no GitHub")
    api, alvo = cfg["api"], cfg["conta"]
    candidatos = []
    try:  # chave de Página: a própria página
        me = call(api, "me", token, fields="instagram_business_account{id,username}")
        if me.get("instagram_business_account"):
            candidatos.append(me["instagram_business_account"])
    except ApiError:
        pass
    if not candidatos:  # chave de usuário: as páginas que ele administra
        pags = call(api, "me/accounts", token, fields="name,instagram_business_account{id,username}")
        candidatos = [p["instagram_business_account"] for p in pags.get("data", []) if p.get("instagram_business_account")]
    for c in candidatos:
        if c.get("username") == alvo:
            return token, c["id"]
    achados = ", ".join("@" + c.get("username", "?") for c in candidatos) or "nenhum"
    raise ApiError(f"a chave não dá acesso ao @{alvo} (perfis encontrados: {achados}). "
                   "O Instagram precisa estar ligado a uma Página do Facebook da mesma conta.")


def ler_perfil(cfg: dict, token: str, ig_id: str, perfil: str) -> dict:
    """Posts recentes de um perfil profissional. Tira view_count se a versão não aceitar."""
    campos = list(CAMPOS_POST)
    for _ in range(2):
        q = (f"business_discovery.username({perfil})"
             f"{{username,followers_count,media_count,media.limit({cfg['posts_por_perfil']}){{{','.join(campos)}}}}}")
        try:
            r = call(cfg["api"], ig_id, token, fields=q)
            bd = r.get("business_discovery") or {}
            return {"perfil": perfil, "seguidores": bd.get("followers_count"),
                    "posts": (bd.get("media") or {}).get("data", [])}
        except ApiError as e:
            if "view_count" in str(e) and "view_count" in campos:
                campos.remove("view_count")
                continue
            raise
    raise ApiError(f"@{perfil}: não consegui ler")


# ---------------------------------------------------------------------------
# Análise (roda sem internet: só usa a coleta salva)
# ---------------------------------------------------------------------------
def eh_video(p: dict) -> bool:
    return p.get("media_type") == "VIDEO" or p.get("media_product_type") == "REELS"


def metrica(p: dict) -> tuple[float, str]:
    if p.get("view_count"):
        return float(p["view_count"]), "views"
    return float((p.get("like_count") or 0) + 3 * (p.get("comments_count") or 0)), "engaj"


def tema_de(cfg: dict, legenda: str, padrao: str) -> str:
    texto = (legenda or "").lower()
    for chave, t in cfg["temas"].items():
        if any(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", texto) for w in t.get("palavras", [])):
            return chave
    return padrao if padrao in cfg["temas"] else "games"


def usados(cfg: dict) -> set[str]:
    f = cfg["_pasta"] / "usados.json"
    return set(json.loads(f.read_text(encoding="utf-8"))) if f.exists() else set()


def analisar(cfg: dict, coleta: dict, agora: datetime | None = None) -> list[dict]:
    agora = agora or datetime.now(TZ)
    limite = agora - timedelta(hours=cfg["janela_horas"])
    ja = usados(cfg)
    padrao = {c["perfil"]: c.get("tema", "games") for c in cfg["concorrentes"]}
    candidatos = []
    for perf in coleta["perfis"]:
        videos = [p for p in perf.get("posts", []) if eh_video(p)]
        if len(videos) < 3:
            continue
        valores = [metrica(p) for p in videos]
        tipo = "views" if sum(1 for _, t in valores if t == "views") >= len(valores) / 2 else "engaj"
        base = statistics.median([v for v, t in valores if t == tipo] or [0]) or 1
        for p in videos:
            quando = datetime.fromisoformat(p["timestamp"].replace("+0000", "+00:00")).astimezone(TZ)
            if quando < limite or p["id"] in ja or p.get("permalink") in ja:
                continue
            v, t = metrica(p)
            if t != tipo:
                continue
            vezes = v / base
            if vezes < cfg["minimo_vezes_media"]:
                continue
            tema = tema_de(cfg, p.get("caption", ""), padrao.get(perf["perfil"], "games"))
            candidatos.append({
                "id": p["id"], "perfil": perf["perfil"], "link": p.get("permalink"),
                "tema": tema, "jogo": cfg["temas"][tema]["nome"],
                "publicado": quando.strftime("%d/%m %H:%M"),
                "views": p.get("view_count"), "curtidas": p.get("like_count"),
                "comentarios": p.get("comments_count"),
                "vezes_media": round(vezes, 1), "medida": tipo,
                "nota": round(vezes * cfg["temas"][tema]["peso"], 2),
                "tem_arquivo": bool(p.get("media_url")),
                "legenda": re.sub(r"\s+", " ", (p.get("caption") or ""))[:160],
            })
    candidatos.sort(key=lambda c: c["nota"], reverse=True)
    lista, por_perfil = [], {}
    for c in candidatos:
        if por_perfil.get(c["perfil"], 0) >= cfg["max_por_perfil"]:
            continue
        por_perfil[c["perfil"]] = por_perfil.get(c["perfil"], 0) + 1
        lista.append(c)
        if len(lista) >= cfg["lista_tamanho"]:
            break
    for i, c in enumerate(lista):
        c["numero"] = i + 1
        c["horario_sugerido"] = cfg["horarios"][i] if i < len(cfg["horarios"]) else None
    return lista


def fmt(n) -> str:
    return "-" if n is None else f"{n:,}".replace(",", ".")


def escrever_lista(cfg: dict, dia: str, lista: list[dict], coleta: dict) -> Path:
    pasta = cfg["_pasta"] / "listas"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{dia}.json").write_text(json.dumps(lista, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lidos = [p["perfil"] for p in coleta["perfis"]]
    linhas = [f"# Vídeos do dia {date.fromisoformat(dia).strftime('%d/%m/%Y')} ({cfg['marca']})", "",
              f"Coleta às {coleta['quando']}, {len(lidos)} perfis lidos, janela de {cfg['janela_horas']}h"
              + (", modo lançamento" if cfg["em_lancamento"] else "") + ".", ""]
    if not lista:
        linhas.append("Nenhum vídeo passou da média dos perfis nesta janela.")
    for c in lista:
        sug = f" · sugestão {c['horario_sugerido']}" if c.get("horario_sugerido") else ""
        num = f"{fmt(c['views'])} views" if c["medida"] == "views" else f"{fmt(c['curtidas'])} curtidas"
        arq = "" if c["tem_arquivo"] else " · **sem arquivo pela API, baixar pelo link**"
        linhas += [f"{c['numero']}. **{c['jogo']}** · @{c['perfil']} · {num} ({c['vezes_media']}x a média) · {c['publicado']}{sug}{arq}",
                   f"   {c['link']}", f"   _{c['legenda']}_" if c["legenda"] else "", ""]
    if coleta.get("falhas"):
        linhas += ["", "Perfis que a API não leu (não são profissionais, mudaram de nome ou não existem):",
                   ", ".join("@" + f for f in coleta["falhas"])]
    arq = pasta / f"{dia}.md"
    arq.write_text("\n".join(l for l in linhas if l is not None) + "\n", encoding="utf-8")
    return arq


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------
def coletar(cfg: dict, forcar: bool = False) -> int:
    agora = datetime.now(TZ)
    if not forcar:
        # O GitHub atrasa os agendamentos: vale a coleta cujo horário passou há até 2h.
        horas = [datetime.combine(agora.date(), datetime.strptime(h, "%H:%M").time(), TZ) for h in cfg["coletas"]]
        if not any(h <= agora <= h + timedelta(hours=2) for h in horas):
            print(f"fora do horário de coleta ({', '.join(cfg['coletas'])}); nada a fazer")
            return 0
        feitas = cfg["_pasta"] / "coletas"
        hora = max(h for h in horas if h <= agora).strftime("%H%M")
        if (feitas / f"{agora.date().isoformat()}-{hora}.json").exists():
            print("a coleta deste horário já foi feita")
            return 0
        if not os.environ.get(cfg["segredo"], "").strip():
            print(f"o secret {cfg['segredo']} ainda não foi cadastrado; coleta pulada")
            return 0
    else:
        hora = agora.strftime("%H%M")
    token, ig_id = conta(cfg)
    coleta = {"quando": agora.strftime("%d/%m/%Y %H:%M"), "perfis": [], "falhas": []}
    for c in cfg["concorrentes"]:
        try:
            perf = ler_perfil(cfg, token, ig_id, c["perfil"])
            for p in perf["posts"]:  # o link do arquivo expira; guarda só se existia
                p["media_url"] = bool(p.get("media_url"))
                p.pop("thumbnail_url", None)
            coleta["perfis"].append(perf)
            print(f"@{c['perfil']}: {len(perf['posts'])} posts")
        except ApiError as e:
            coleta["falhas"].append(c["perfil"])
            print(f"@{c['perfil']}: falhou ({str(e)[:160]})")
        time.sleep(0.5)
    pasta = cfg["_pasta"] / "coletas"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"{agora.date().isoformat()}-{hora}.json").write_text(
        json.dumps(coleta, ensure_ascii=False) + "\n", encoding="utf-8")
    lista = analisar(cfg, coleta, agora)
    arq = escrever_lista(cfg, agora.date().isoformat(), lista, coleta)
    print(f"\n{len(lista)} vídeos na lista: {arq.relative_to(ROOT)}")
    return 0 if coleta["perfis"] else 1


def baixar(cfg: dict, dia: str, numeros: list[int]) -> int:
    lista = json.loads((cfg["_pasta"] / "listas" / f"{dia}.json").read_text(encoding="utf-8"))
    escolhidos = [c for c in lista if c["numero"] in numeros]
    if not escolhidos:
        print("nenhum dos números está na lista")
        return 1
    token, ig_id = conta(cfg)
    destino = cfg["_entrada"] / dia
    destino.mkdir(parents=True, exist_ok=True)
    ja = usados(cfg)
    erros = 0
    cache: dict[str, list] = {}
    for c in escolhidos:
        if c["perfil"] not in cache:
            cache[c["perfil"]] = ler_perfil(cfg, token, ig_id, c["perfil"])["posts"]
        post = next((p for p in cache[c["perfil"]] if p["id"] == c["id"]), None)
        url = post and post.get("media_url")
        if not url:
            print(f"{c['numero']}: sem arquivo pela API; baixar pelo link {c['link']}")
            erros += 1
            continue
        nome = destino / f"{c['numero']:02d}-{c['tema']}-{re.sub(r'[^a-z0-9]+', '-', c['perfil'].lower())}.mp4"
        with urllib.request.urlopen(url, timeout=120) as r:
            nome.write_bytes(r.read())
        info = {k: c[k] for k in ("numero", "perfil", "link", "jogo", "tema", "legenda", "horario_sugerido")}
        nome.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        ja.update({c["id"], c["link"]})
        print(f"{c['numero']}: baixado {nome.relative_to(ROOT)} ({nome.stat().st_size // 1024} KB)")
    (cfg["_pasta"] / "usados.json").write_text(json.dumps(sorted(ja), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 1 if erros == len(escolhidos) else 0


def teste(cfg: dict) -> int:
    token, ig_id = conta(cfg)
    print(f"chave ok: dá acesso ao @{cfg['conta']}")
    perfil = cfg["concorrentes"][0]["perfil"]
    perf = ler_perfil(cfg, token, ig_id, perfil)
    posts = perf["posts"]
    videos = [p for p in posts if eh_video(p)]
    print(f"@{perfil}: {fmt(perf['seguidores'])} seguidores, {len(posts)} posts lidos, {len(videos)} vídeos")
    print(f"  com views: {sum(1 for p in videos if p.get('view_count'))}, "
          f"com curtidas: {sum(1 for p in videos if p.get('like_count') is not None)}, "
          f"com arquivo: {sum(1 for p in videos if p.get('media_url'))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(CONFIG_PADRAO))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("teste")
    c = sub.add_parser("coletar")
    c.add_argument("--forcar", action="store_true", help="coleta agora, fora do horário")
    b = sub.add_parser("baixar")
    b.add_argument("data")
    b.add_argument("numeros", help="ex.: 1,4,7")
    l = sub.add_parser("lista")
    l.add_argument("data", nargs="?")
    a = sub.add_parser("analisar")
    a.add_argument("arquivo")
    args = ap.parse_args(argv)
    cfg = carregar_config(Path(args.config))
    try:
        if args.cmd == "teste":
            return teste(cfg)
        if args.cmd == "coletar":
            return coletar(cfg, args.forcar)
        if args.cmd == "baixar":
            nums = [int(n) for n in re.findall(r"\d+", args.numeros)]
            return baixar(cfg, args.data, nums)
        if args.cmd == "lista":
            dia = args.data or datetime.now(TZ).date().isoformat()
            print((cfg["_pasta"] / "listas" / f"{dia}.md").read_text(encoding="utf-8"))
            return 0
        if args.cmd == "analisar":
            coleta = json.loads(Path(args.arquivo).read_text(encoding="utf-8"))
            dia = Path(args.arquivo).name[:10]
            agora = datetime.fromisoformat(f"{dia}T12:00:00").replace(tzinfo=TZ)
            arq = escrever_lista(cfg, dia, analisar(cfg, coleta, agora), coleta)
            print(arq.read_text(encoding="utf-8"))
            return 0
    except ApiError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
