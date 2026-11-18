"""Painel das marcas: grava o estado da Pixelzada num arquivo padronizado.

O painel (pixelzada.com.br/painel/) lê um estado.json por marca, direto do
repositório público de cada uma. Este script monta o da Pixelzada; o molde das
marcas novas usa o mesmo formato (campo "formato": "painel-marca/1").

    python -m scripts.social.painel                 monta e imprime o resumo
    python -m scripts.social.painel --saida DIR     grava DIR/estado.json e DIR/historico.json

Roda no GitHub Actions (.github/workflows/painel.yml), que tem a chave do
Instagram (seguidores, alcance, views) e o GITHUB_TOKEN (falhas dos workflows).
Sem as chaves, a parte local (fila, carrosséis, site, pesquisa) sai igual e a
parte que falta fica marcada como "sem chave".
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import instagram as IG, pauta as P, reels as R

FORMATO = "painel-marca/1"
MARCA = {"nome": "Pixelzada", "slug": "pixelzada", "instagram": IG.USUARIO,
         "site": "https://pixelzada.com.br", "repo": "diegobatistaia/pixelzada"}
CARROSSEIS_DIA = len(IG.CARROSSEIS)
FOLGA = timedelta(minutes=30)   # um post só conta como atrasado 30 min depois do horário
DIAS = 7


def _dt(texto: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return (d if d.tzinfo else d.replace(tzinfo=P.TZ)).astimezone(P.TZ)


def _hora(dia: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(dia.year, dia.month, dia.day, h, m, tzinfo=P.TZ)


# ---------------------------------------------------------------------------
# Parte local: arquivos do repositório
# ---------------------------------------------------------------------------
def reels_publicados_por_dia(fila: list[dict]) -> dict[str, int]:
    conta: dict[str, int] = {}
    for item in fila:
        em = _dt((item.get("publicado") or {}).get("em", ""))
        if item.get("status") == "publicado" and em:
            conta[em.date().isoformat()] = conta.get(em.date().isoformat(), 0) + 1
    return conta


def reels_hoje(fila: list[dict], agora: datetime) -> dict:
    hoje = agora.date()
    grade = R.horarios(hoje)
    publicados = reels_publicados_por_dia(fila).get(hoje.isoformat(), 0)
    passados = [h for h in grade if _hora(hoje, h) + FOLGA <= agora]
    atrasados = sorted(i["horario"] for i in fila
                       if i.get("data") == hoje.isoformat() and i.get("status") != "publicado"
                       and _hora(hoje, i["horario"]) + FOLGA <= agora)
    na_fila = {i["horario"] for i in fila if i.get("data") == hoje.isoformat()}
    buracos = [h for h in grade if h not in na_fila and _hora(hoje, h) > agora]
    return {"meta": len(grade), "publicados": publicados, "deviam_ter_saido": len(passados),
            "atrasados": atrasados, "horarios_vazios_hoje": buracos}


def reserva_reels(fila: list[dict], agora: datetime) -> dict:
    futuros = [i for i in fila if i.get("status") == "agendado" and _hora(date.fromisoformat(i["data"]), i["horario"]) > agora]
    por_dia: dict[str, int] = {}
    for i in futuros:
        por_dia[i["data"]] = por_dia.get(i["data"], 0) + 1
    # Até que dia a grade está toda preenchida, contando de amanhã.
    coberto_ate, dia = None, agora.date() + timedelta(days=1)
    while por_dia.get(dia.isoformat(), 0) >= len(R.horarios(dia)):
        coberto_ate, dia = dia.isoformat(), dia + timedelta(days=1)
    meta_amanha = len(R.horarios(agora.date() + timedelta(days=1)))
    return {
        "agendados": len(futuros),
        "meta_por_dia": meta_amanha,
        "dias_de_reserva": round(len(futuros) / meta_amanha, 1) if meta_amanha else None,
        "grade_cheia_ate": coberto_ate,
        "sem_revisao": sum(1 for i in futuros if (i.get("origem") or {}).get("revisado") is False),
        "por_dia": [{"data": d, "agendados": n, "meta": len(R.horarios(date.fromisoformat(d)))}
                    for d, n in sorted(por_dia.items())],
    }


def carrosseis(pautas: list[dict], agora: datetime) -> tuple[dict, dict[str, int]]:
    por_dia: dict[str, int] = {}
    hoje_feitos = set()
    for p in pautas:
        pub = p.get("publicado") or {}
        if p.get("status") == "publicado" and pub.get("data"):
            por_dia[pub["data"]] = por_dia.get(pub["data"], 0) + 1
            if pub["data"] == agora.date().isoformat():
                hoje_feitos.add(pub.get("horario"))
    passados = [h for h, _ in IG.CARROSSEIS if _hora(agora.date(), h) + FOLGA <= agora]
    esperando = sum(1 for p in pautas if p.get("status") not in ("publicado", "descartada", "vencida")
                    and not P.vencida(p, agora))
    hoje = {"meta": CARROSSEIS_DIA, "publicados": len(hoje_feitos), "deviam_ter_saido": len(passados),
            "atrasados": [h for h in passados if h not in hoje_feitos], "pautas_esperando": esperando}
    return hoje, por_dia


def materias(agora: datetime) -> tuple[dict, dict[str, int]]:
    arq = P.ROOT / "data" / "published.json"
    lista = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else []
    por_dia: dict[str, int] = {}
    ultima = None
    for m in lista:
        em = _dt(m.get("published_at", ""))
        if not em:
            continue
        por_dia[em.date().isoformat()] = por_dia.get(em.date().isoformat(), 0) + 1
        if not ultima or em > ultima[0]:
            ultima = (em, m)
    resumo = {"total": len(lista), "hoje": por_dia.get(agora.date().isoformat(), 0), "meta_dia": 8}
    if ultima:
        em, m = ultima
        resumo["ultima"] = {"titulo": m.get("title"), "url": MARCA["site"] + m.get("url", "/"), "em": em.isoformat()}
    return resumo, por_dia


def pesquisa() -> dict:
    pasta = P.ROOT / "social" / "pesquisa" / "coletas"
    arqs = sorted(pasta.glob("*.json")) if pasta.exists() else []
    if not arqs:
        return {}
    d = json.loads(arqs[-1].read_text(encoding="utf-8"))
    return {"ultima_coleta": d.get("quando"), "perfis_lidos": len(d.get("perfis") or []),
            "perfis_com_falha": len(d.get("falhas") or [])}


# ---------------------------------------------------------------------------
# Instagram (precisa da chave)
# ---------------------------------------------------------------------------
def _valor(resp: dict) -> int | None:
    for m in resp.get("data") or []:
        tv = m.get("total_value") or {}
        if "value" in tv:
            return tv["value"]
    return None


def instagram(agora: datetime) -> dict:
    token = os.environ.get(IG.SECRET, "").strip()
    if not token:
        return {"erro": "sem chave"}
    try:
        token, ig = IG.conta()
        perfil = IG.call("GET", ig, token, fields="username,followers_count,follows_count,media_count")
        desde = int((agora - timedelta(days=DIAS)).timestamp())
        ate = int(agora.timestamp())
        conta = {}
        for metrica in ("reach", "views"):
            try:
                r = IG.call("GET", f"{ig}/insights", token, metric=metrica, period="day",
                            metric_type="total_value", since=desde, until=ate)
                conta[metrica] = _valor(r)
            except IG.ApiError as e:
                conta[metrica] = None
                print(f"aviso: insights da conta ({metrica}): {e}", file=sys.stderr)

        # Reels dos últimos 7 dias, com views e alcance de cada um.
        reels, url = [], f"{ig}/media"
        params = {"fields": "id,media_product_type,timestamp,permalink,caption,like_count,comments_count", "limit": 100}
        for _ in range(4):
            r = IG.call("GET", url, token, **params)
            antigos = False
            for m in r.get("data") or []:
                em = _dt(m.get("timestamp", ""))
                if not em or em < agora - timedelta(days=DIAS):
                    antigos = True
                    continue
                if m.get("media_product_type") == "REELS":
                    reels.append(m | {"em": em})
            proxima = (r.get("paging") or {}).get("next")
            if antigos or not proxima:
                break
            url, params = proxima, {}
        for m in reels[:150]:
            try:
                ins = IG.call("GET", f"{m['id']}/insights", token, metric="views,reach")
                for item in ins.get("data") or []:
                    m[item["name"]] = (item.get("values") or [{}])[0].get("value")
            except IG.ApiError:
                pass
        views = [m["views"] for m in reels if isinstance(m.get("views"), int)]
        por_dia: dict[str, int] = {}
        for m in reels:
            if isinstance(m.get("views"), int):
                d = m["em"].date().isoformat()
                por_dia[d] = por_dia.get(d, 0) + m["views"]
        top = sorted((m for m in reels if isinstance(m.get("views"), int)), key=lambda m: -m["views"])[:5]
        return {
            "usuario": perfil.get("username"),
            "seguidores": perfil.get("followers_count"),
            "seguindo": perfil.get("follows_count"),
            "posts": perfil.get("media_count"),
            "alcance_7d": conta.get("reach"),
            "views_7d": conta.get("views"),
            "reels_7d": {
                "quantidade": len(reels),
                "views_total": sum(views) if views else 0,
                "views_mediana": int(statistics.median(views)) if views else None,
                "acima_de_1000": sum(1 for v in views if v >= 1000),
                "views_por_dia": por_dia,
                "melhores": [{"legenda": (m.get("caption") or "").split("\n")[0][:90], "views": m["views"],
                              "alcance": m.get("reach"), "curtidas": m.get("like_count"),
                              "link": m.get("permalink"), "em": m["em"].isoformat()} for m in top],
            },
        }
    except IG.ApiError as e:
        return {"erro": str(e)[:300]}


# ---------------------------------------------------------------------------
# Falhas dos workflows (GitHub, precisa do GITHUB_TOKEN)
# ---------------------------------------------------------------------------
def falhas(agora: datetime) -> dict:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", MARCA["repo"])
    if not token:
        return {"erro": "sem chave"}
    desde = (agora - timedelta(hours=24)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=100&created=%3E%3D{desde}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            runs = json.loads(r.read()).get("workflow_runs") or []
    except (urllib.error.URLError, ValueError) as e:
        return {"erro": f"GitHub não respondeu: {e}"[:200]}
    runs.sort(key=lambda r: r.get("created_at", ""))
    ultimo_ok: dict[str, str] = {}
    for r in runs:
        if r.get("conclusion") == "success":
            ultimo_ok[r["name"]] = r["created_at"]
    lista = []
    for r in runs:
        if r.get("conclusion") not in ("failure", "timed_out", "startup_failure"):
            continue
        lista.append({"workflow": r["name"], "em": _dt(r["created_at"]).isoformat(), "link": r.get("html_url"),
                      "resolvido": ultimo_ok.get(r["name"], "") > r["created_at"]})
    return {"rodadas_24h": len(runs), "falhas_24h": len(lista),
            "sem_resolver": sum(1 for f in lista if not f["resolvido"]), "lista": lista[-15:][::-1]}


def buffer_uso(fila: list[dict], agora: datetime) -> dict:
    """Pedidos ao Buffer no mês (limite grátis: 1.000 por rede) e envios com erro hoje."""
    cfg_p = R.PASTA / "buffer.json"
    cfg = json.loads(cfg_p.read_text(encoding="utf-8")) if cfg_p.exists() else {}
    uso = cfg.get("uso") or {}
    if uso.get("mes") != agora.strftime("%Y-%m"):
        uso = {}
    hoje = agora.date().isoformat()
    erros = sum(1 for i in fila if i.get("data") == hoje for r in (i.get("redes") or {}).values() if r.get("erro"))
    return {"ativo": bool(cfg.get("ativo")), "uso": uso, "erros_hoje": erros}


# ---------------------------------------------------------------------------
def alertas(e: dict) -> list[dict]:
    a = []
    rh, ch, res = e["hoje"]["reels"], e["hoje"]["carrosseis"], e["fila_reels"]
    if rh["atrasados"]:
        a.append({"nivel": "vermelho", "texto": f"{len(rh['atrasados'])} Reel(s) de hoje atrasado(s): {', '.join(rh['atrasados'][:5])}"})
    if ch["atrasados"]:
        a.append({"nivel": "vermelho", "texto": f"Carrossel atrasado hoje: {', '.join(ch['atrasados'])}"})
    if rh["horarios_vazios_hoje"]:
        a.append({"nivel": "amarelo", "texto": f"{len(rh['horarios_vazios_hoje'])} horário(s) de Reel ainda sem vídeo hoje"})
    dias = res.get("dias_de_reserva") or 0
    if dias < 1:
        a.append({"nivel": "vermelho", "texto": f"Fila de Reels com menos de 1 dia de reserva ({res['agendados']} vídeos)"})
    elif dias < 2:
        a.append({"nivel": "amarelo", "texto": f"Fila de Reels com só {str(dias).replace('.', ',')} dia(s) de reserva"})
    f = e.get("falhas") or {}
    if f.get("sem_resolver"):
        a.append({"nivel": "vermelho", "texto": f"{f['sem_resolver']} falha(s) no GitHub ainda sem resolver"})
    ig = e.get("instagram") or {}
    if ig.get("erro") and ig["erro"] != "sem chave":
        a.append({"nivel": "amarelo", "texto": "Não consegui ler o Instagram nesta rodada"})
    for rede, n in (e.get("buffer") or {}).get("uso", {}).items():
        if rede != "mes" and n >= 800:
            a.append({"nivel": "vermelho" if n >= 950 else "amarelo",
                      "texto": f"Buffer: {n} de 1.000 pedidos do mês usados no {rede} (plano grátis)"})
    if (e.get("buffer") or {}).get("erros_hoje"):
        a.append({"nivel": "amarelo", "texto": f"Buffer: {e['buffer']['erros_hoje']} envio(s) para TikTok/YouTube com erro hoje"})
    if e["site"]["hoje"] == 0 and datetime.fromisoformat(e["atualizado"]).hour >= 12:
        a.append({"nivel": "amarelo", "texto": "Nenhuma matéria nova no site hoje"})
    return a


def montar(agora: datetime | None = None, historico: dict | None = None) -> tuple[dict, dict]:
    agora = agora or IG.agora()
    fila = R.carregar()
    pautas = P.todas()
    car_hoje, car_dia = carrosseis(pautas, agora)
    site, mat_dia = materias(agora)
    reel_dia = reels_publicados_por_dia(fila)
    estado = {
        "formato": FORMATO,
        "marca": MARCA,
        "atualizado": agora.isoformat(timespec="minutes"),
        "hoje": {"data": agora.date().isoformat(), "reels": reels_hoje(fila, agora), "carrosseis": car_hoje},
        "fila_reels": reserva_reels(fila, agora),
        "site": site,
        "pesquisa": pesquisa(),
        "instagram": instagram(agora),
        "falhas": falhas(agora),
        "buffer": buffer_uso(fila, agora),
    }
    ig = estado["instagram"]
    views_dia = ((ig.get("reels_7d") or {}).get("views_por_dia")) or {}
    dias = []
    for n in range(DIAS - 1, -1, -1):
        d = agora.date() - timedelta(days=n)
        k = d.isoformat()
        dias.append({"data": k, "reels": reel_dia.get(k, 0), "reels_meta": len(R.horarios(d)),
                     "carrosseis": car_dia.get(k, 0), "carrosseis_meta": CARROSSEIS_DIA,
                     "materias": mat_dia.get(k, 0), "views_reels": views_dia.get(k)})
    estado["ultimos_dias"] = dias

    # Histórico: um ponto por dia (o último da noite fica valendo).
    historico = historico or {"formato": FORMATO, "dias": {}}
    if isinstance(ig.get("seguidores"), int):
        historico["dias"][agora.date().isoformat()] = {"seguidores": ig["seguidores"], "posts": ig.get("posts"),
                                                      "alcance_7d": ig.get("alcance_7d"), "views_7d": ig.get("views_7d")}
    estado["seguidores_por_dia"] = [{"data": k, "seguidores": v["seguidores"]}
                                    for k, v in sorted(historico["dias"].items())][-60:]
    estado["alertas"] = alertas(estado)
    return estado, historico


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", type=Path)
    args = ap.parse_args(argv)
    hist = None
    if args.saida and (args.saida / "historico.json").exists():
        hist = json.loads((args.saida / "historico.json").read_text(encoding="utf-8"))
    estado, hist = montar(historico=hist)
    if args.saida:
        args.saida.mkdir(parents=True, exist_ok=True)
        (args.saida / "estado.json").write_text(json.dumps(estado, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (args.saida / "historico.json").write_text(json.dumps(hist, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    h = estado["hoje"]
    print(f"{estado['marca']['nome']} {estado['atualizado']}: Reels {h['reels']['publicados']}/{h['reels']['meta']}, "
          f"carrosséis {h['carrosseis']['publicados']}/{h['carrosseis']['meta']}, "
          f"fila {estado['fila_reels']['agendados']} ({estado['fila_reels']['dias_de_reserva']} dias), "
          f"matérias hoje {estado['site']['hoje']}, alertas {len(estado['alertas'])}")
    for a in estado["alertas"]:
        print(f"  [{a['nivel']}] {a['texto']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
