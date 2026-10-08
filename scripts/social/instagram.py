"""Publicação automática do @pixelzada.br: carrossel + Story em horários fixos e um Reel por dia.

A redação (Routine do Claude) escreve as pautas em social/pautas/. Tudo o que vem
depois roda no GitHub Actions (.github/workflows/instagram.yml), que é quem tem
internet, a chave do Instagram e a chave da Hostinger:

    python -m scripts.social.instagram decidir    só diz se há post neste horário
    python -m scripts.social.instagram preparar   escolhe o post do horário e desenha
    (o workflow envia social/saida/<slug>/ para pixelzada.com.br/ig/<slug>/)
    python -m scripts.social.instagram publicar   chama a API do Instagram

Na sessão do Claude (sem chave, sem internet):

    python -m scripts.social.instagram check [slug ...]   confere as pautas
    python -m scripts.social.instagram fila               o que está esperando
    python -m scripts.social.instagram agenda             os horários de hoje

Pelo botão "Run workflow" do Actions:

    teste      confere se a chave funciona e é do @pixelzada.br
    conferir   lista os últimos posts da conta (só leitura)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from . import pauta as P

USUARIO = "pixelzada.br"
SECRET = "INSTAGRAM_TOKEN_PIXELZADA"
API = "https://graph.instagram.com/v23.0"
PEDIDO = P.SAIDA / "pedido.json"
RESULTADO = P.ROOT / "social" / "publicar" / "ultimo.json"

# Horários fixos (Brasília): 6 carrosséis por dia, 3 de GTA 6 e 3 de outros
# jogos. Um horário de GTA sem pauta de GTA pega outro jogo, e vice-versa. Cada
# carrossel leva um Story junto.
CARROSSEIS = [("08:00", "gta"), ("10:00", "outros"), ("12:00", "gta"), ("14:00", "outros"),
              ("18:00", "gta"), ("21:00", "outros")]
REEL = "18:00"
# O GitHub atrasa os agendamentos. Um horário fica aberto de 10 min antes até
# 2h30 depois; dentro da janela, cada tentativa vê se ele já foi preenchido.
ANTES, DEPOIS = timedelta(minutes=10), timedelta(minutes=150)


def agora() -> datetime:
    fixo = os.environ.get("PIXELZADA_AGORA")  # para testes
    return datetime.fromisoformat(fixo).astimezone(P.TZ) if fixo else datetime.now(P.TZ)


def _hora(dia: datetime, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return dia.replace(hour=h, minute=m, second=0, microsecond=0)


def _publicado_hoje(pautas: list[dict], hoje: str) -> list[dict]:
    return [p for p in pautas if (p.get("publicado") or {}).get("data") == hoje]


# ---------------------------------------------------------------------------
# Escolha do que sai agora
# ---------------------------------------------------------------------------
def imagem_chave(p: dict) -> str:
    """A mesma foto com outro recorte ou tamanho (?w=1200...) tem a mesma chave."""
    img = p.get("imagem") or {}
    return (img.get("url") or img.get("path") or "").split("?")[0].split("#")[0].strip().lower()


def candidatas(pautas: list[dict], t: datetime) -> list[dict]:
    """Fila de pautas prontas, a mais antiga primeiro. Nunca repete imagem: pauta
    cuja imagem já saiu em outro carrossel, ou que repete a de uma pauta mais
    antiga da fila, fica de fora até a redação trocar a imagem."""
    usadas = {imagem_chave(p) for p in pautas if p.get("status") == "publicado"}
    fila = []
    for p in sorted((p for p in pautas if p.get("status") == "pronto" and not P.vencida(p, t)), key=P.criado_em):
        k = imagem_chave(p)
        if k in usadas:
            continue
        usadas.add(k)
        fila.append(p)
    return fila


def escolher(t: datetime | None = None, pautas: list[dict] | None = None) -> dict | None:
    """O pedido deste momento: carrossel, Reel ou nada."""
    t = t or agora()
    pautas = pautas if pautas is not None else P.todas()
    hoje = t.date().isoformat()
    feitos = _publicado_hoje(pautas, hoje)
    ocupados = {p["publicado"]["horario"] for p in feitos}

    # Só o horário mais recente que já abriu conta: um horário perdido (o GitHub
    # atrasou demais) fica para trás, em vez de sair colado no seguinte.
    abertos = [(h, k) for h, k in CARROSSEIS if _hora(t, h) - ANTES <= t]
    for hhmm, tipo in abertos[-1:]:
        inicio = _hora(t, hhmm)
        if t > inicio + DEPOIS or hhmm in ocupados:
            continue
        fila = candidatas(pautas, t)
        gta = [p for p in fila if p["gta6"]]
        outros = [p for p in fila if not p["gta6"]]
        if tipo == "gta":
            escolhida = (gta or outros or [None])[0]
        else:
            # Pega GTA 6 só se sobrar mais do que os horários de GTA que faltam hoje.
            faltam = sum(1 for h, k in CARROSSEIS if k == "gta" and _hora(t, h) > inicio and h not in ocupados)
            escolhida = (outros or (gta if len(gta) > faltam else []) or [None])[0]
        if escolhida:
            return {"acao": "carrossel", "slug": escolhida["slug"], "horario": hhmm, "data": hoje}

    inicio = _hora(t, REEL)
    if inicio - ANTES <= t <= inicio + DEPOIS and not any(p.get("reel") for p in feitos):
        # O Reel do dia é o carrossel de hoje mais recente, GTA 6 primeiro.
        base = sorted(feitos, key=lambda p: (p["gta6"], p["publicado"]["em"]), reverse=True)
        if base:
            return {"acao": "reel", "slug": base[0]["slug"], "horario": REEL, "data": hoje}
    return None


def cmd_decidir(args) -> int:
    """Só a decisão, sem desenhar: o workflow pula a instalação pesada quando é 'nada'."""
    pedido = escolher()
    print(f"agora: {pedido['acao']} {pedido['slug']} ({pedido['horario']})" if pedido else "nada para publicar agora")
    _saida(acao=pedido["acao"] if pedido else "nada")
    return 0


def cmd_preparar(args) -> int:
    from . import arte

    P.SAIDA.mkdir(parents=True, exist_ok=True)
    PEDIDO.unlink(missing_ok=True)
    t = agora()
    for _ in range(4):  # se uma pauta reprova no desenho, tenta a próxima
        pedido = escolher(t)
        if not pedido:
            print("nada para publicar agora")
            _saida(acao="nada")
            return 0
        p = P.carregar(pedido["slug"])
        pasta = P.SAIDA / p["slug"]
        shutil.rmtree(pasta, ignore_errors=True)
        try:
            erros = P.conferir(p, str(P.caminho(p["slug"])))
            if erros:
                raise arte.ArteError("; ".join(erros))
            post = arte.desenhar_post(p, pasta)
            arquivos = [f.name for f in post["slides"]]
            pedido["slides"] = arquivos
            pedido["story"] = post["story"].name
            if pedido["acao"] == "reel":
                reel = arte.desenhar_reel(p, post["pngs"], pasta)
                pedido.update(video=reel["video"].name, capa=reel["capa"].name)
        except arte.ArteError as e:
            print(f"{p['slug']}: não deu para desenhar: {e}")
            if pedido["acao"] == "reel":
                p["reel"] = {"erro": str(e), "em": t.isoformat(timespec="seconds")}
            else:
                p.update(status="reprovado", motivo=str(e))
            P.salvar(p)
            continue
        # Só o que vai para o ar sobe para a Hostinger.
        for f in pasta.iterdir():
            if f.suffix not in (".jpg", ".mp4") or f.name == "foto.jpg":
                f.unlink()
        PEDIDO.write_text(json.dumps(pedido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"pedido: {pedido['acao']} {pedido['slug']} ({pedido['horario']})")
        _saida(acao=pedido["acao"], slug=pedido["slug"])
        return 0
    _saida(acao="nada")
    return 1


def _saida(**kv) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


# ---------------------------------------------------------------------------
# API do Instagram (login do Instagram, graph.instagram.com)
# ---------------------------------------------------------------------------
class ApiError(RuntimeError):
    pass


def call(method: str, path: str, token: str, **params) -> dict:
    params["access_token"] = token
    data = urllib.parse.urlencode(params).encode()
    url = path if path.startswith("http") else f"{API}/{path}"
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")
        # Nunca imprimir a chave: a URL do GET carrega o token, então só o corpo do erro sai.
        raise ApiError(f"HTTP {e.code} em {path.split('?')[0]}: {corpo[:500]}") from None
    except urllib.error.URLError as e:
        raise ApiError(f"sem resposta de {path.split('?')[0]}: {e.reason}") from None


def conta() -> tuple[str, str]:
    """Chave e id da conta. Recusa se a chave for de outra conta."""
    token = os.environ.get(SECRET, "").strip()
    if not token:
        raise ApiError(f"o secret {SECRET} não está cadastrado no GitHub")
    me = call("GET", "me", token, fields="user_id,username")
    if me.get("username") != USUARIO:
        raise ApiError(f"a chave {SECRET} é da conta @{me.get('username')}, não de @{USUARIO}")
    return token, me["user_id"]


def renovar(token: str) -> str:
    """Estica a validade da chave (60 dias a partir de agora)."""
    try:
        r = call("GET", "https://graph.instagram.com/refresh_access_token", token, grant_type="ig_refresh_token")
    except ApiError as e:
        return f"renovação da chave falhou: {e}"
    dias = int(r.get("expires_in", 0)) // 86400
    if r.get("access_token") and r["access_token"] != token:
        return f"a renovação devolveu uma chave nova (vale {dias} dias); a atual continua valendo até vencer"
    return f"chave renovada: vale mais {dias} dias"


def esperar(container: str, token: str, tentativas: int = 40, pausa: int = 6) -> None:
    for _ in range(tentativas):
        st = call("GET", container, token, fields="status_code,status").get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            info = call("GET", container, token, fields="status")
            raise ApiError(f"o Instagram recusou a mídia: {info.get('status')}")
        time.sleep(pausa)
    raise ApiError("o Instagram não terminou de processar a mídia a tempo")


def url_publica(slug: str, arquivo: str) -> str:
    import yaml
    base = yaml.safe_load((P.ROOT / "site.config.yaml").read_text(encoding="utf-8"))["site"]["base_url"].rstrip("/")
    return f"{base}/ig/{slug}/{arquivo}"


def conferir_urls(urls: list[str]) -> None:
    """O Instagram busca a mídia pela URL: ela tem que estar no ar antes."""
    for u in urls:
        for tentativa in range(5):
            try:
                req = urllib.request.Request(u, method="HEAD", headers={"User-Agent": "pixelzada-bot"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    if r.status == 200:
                        break
            except urllib.error.URLError:
                pass
            time.sleep(5 * (tentativa + 1))
        else:
            raise ApiError(f"a mídia não está no ar: {u}")


def publicar_carrossel(p: dict, pedido: dict, ig: str, token: str) -> dict:
    urls = [url_publica(p["slug"], f) for f in pedido["slides"]]
    conferir_urls(urls)
    filhos = []
    for i, url in enumerate(urls):
        params = {"image_url": url, "is_carousel_item": "true"}
        if i < len(p.get("alt", [])):
            params["alt_text"] = p["alt"][i]
        try:
            c = call("POST", f"{ig}/media", token, **params)
        except ApiError as e:
            if "alt_text" not in str(e):
                raise
            params.pop("alt_text")  # conta sem texto alternativo pela API: segue sem ele
            c = call("POST", f"{ig}/media", token, **params)
        filhos.append(c["id"])
    for c in filhos:
        esperar(c, token)
    car = call("POST", f"{ig}/media", token, media_type="CAROUSEL", children=",".join(filhos), caption=P.legenda(p))
    esperar(car["id"], token)
    pub = call("POST", f"{ig}/media_publish", token, creation_id=car["id"])
    info = call("GET", pub["id"], token, fields="permalink")
    return {"media_id": pub["id"], "permalink": info.get("permalink")}


def publicar_story(p: dict, pedido: dict, ig: str, token: str) -> dict:
    url = url_publica(p["slug"], pedido["story"])
    conferir_urls([url])
    c = call("POST", f"{ig}/media", token, media_type="STORIES", image_url=url)
    esperar(c["id"], token)
    pub = call("POST", f"{ig}/media_publish", token, creation_id=c["id"])
    return {"media_id": pub["id"]}


def publicar_reel(p: dict, pedido: dict, ig: str, token: str) -> dict:
    video, capa = url_publica(p["slug"], pedido["video"]), url_publica(p["slug"], pedido["capa"])
    conferir_urls([video, capa])
    c = call("POST", f"{ig}/media", token, media_type="REELS", video_url=video, cover_url=capa,
             caption=P.legenda(p), share_to_feed="true")
    esperar(c["id"], token, tentativas=60, pausa=10)
    pub = call("POST", f"{ig}/media_publish", token, creation_id=c["id"])
    info = call("GET", pub["id"], token, fields="permalink")
    return {"media_id": pub["id"], "permalink": info.get("permalink")}


def _gravar(resultado: dict) -> None:
    RESULTADO.parent.mkdir(parents=True, exist_ok=True)
    RESULTADO.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    resumo = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo:
        with open(resumo, "a", encoding="utf-8") as f:
            f.write("```json\n" + json.dumps(resultado, ensure_ascii=False, indent=2) + "\n```\n")


def cmd_publicar(args) -> int:
    pedido = json.loads(PEDIDO.read_text(encoding="utf-8"))
    p = P.carregar(pedido["slug"])
    t = agora().isoformat(timespec="seconds")
    resultado = {"pedido": pedido, "em": t}
    try:
        token, ig = conta()
        if pedido["acao"] == "carrossel":
            if p.get("status") != "pronto":
                raise ApiError(f"{p['slug']} está {p.get('status')}; nada publicado")
            out = publicar_carrossel(p, pedido, ig, token)
            p.update(status="publicado", publicado={"data": pedido["data"], "horario": pedido["horario"], "em": t, **out})
            P.salvar(p)  # grava já: se o Story falhar, o carrossel não sai de novo
            resultado.update(ok=True, **out)
            print(f"carrossel publicado: {out.get('permalink')}")
            try:
                p["story"] = {"em": agora().isoformat(timespec="seconds"), **publicar_story(p, pedido, ig, token)}
                print("story publicado")
            except ApiError as e:
                p["story"] = {"erro": str(e)}
                print(f"AVISO: o Story não saiu: {e}")
            resultado["story"] = p["story"]
        else:
            out = publicar_reel(p, pedido, ig, token)
            p["reel"] = {"em": t, **out}
            resultado.update(ok=True, **out)
            print(f"reel publicado: {out.get('permalink')}")
        P.salvar(p)
        resultado["chave"] = renovar(token)
    except ApiError as e:
        resultado.update(ok=False, erro=str(e))
        print(f"ERRO: {e}")
    _gravar(resultado)
    return 0 if resultado["ok"] else 1


def cmd_teste(args) -> int:
    resultado = {"pedido": {"acao": "teste"}, "em": agora().isoformat(timespec="seconds")}
    try:
        token, _ = conta()
        resultado.update(ok=True, conta=USUARIO, chave=renovar(token))
        print(f"teste ok: a chave funciona e é do @{USUARIO}")
    except ApiError as e:
        resultado.update(ok=False, erro=str(e))
        print(f"ERRO: {e}")
    _gravar(resultado)
    return 0 if resultado["ok"] else 1


def cmd_conferir(args) -> int:
    resultado = {"pedido": {"acao": "conferir"}, "em": agora().isoformat(timespec="seconds")}
    try:
        token, ig = conta()
        media = call("GET", f"{ig}/media", token, fields="caption,permalink,timestamp,media_type", limit=10).get("data", [])
        resultado.update(ok=True, ultimos=[{
            "quando": m.get("timestamp"), "tipo": m.get("media_type"), "link": m.get("permalink"),
            "inicio": (m.get("caption") or "").split("\n", 1)[0][:90]} for m in media])
    except ApiError as e:
        resultado.update(ok=False, erro=str(e))
        print(f"ERRO: {e}")
    _gravar(resultado)
    return 0 if resultado["ok"] else 1


# ---------------------------------------------------------------------------
# Sessão: conferência e fila
# ---------------------------------------------------------------------------
def cmd_check(args) -> int:
    arquivos = [P.caminho(s) for s in args.slugs] if args.slugs else sorted(P.PAUTAS.glob("*.json"))
    ruins = 0
    todas = P.todas()
    for f in arquivos:
        p = json.loads(f.read_text(encoding="utf-8"))
        if p.get("status") != "pronto":
            continue
        erros = P.conferir(p, str(f))
        k = imagem_chave(p)
        for o in todas:
            if o["slug"] != p["slug"] and o.get("status") in ("pronto", "publicado") and imagem_chave(o) == k \
                    and (o.get("status") == "publicado" or P.criado_em(o) < P.criado_em(p)):
                erros.append(f"imagem repetida: a mesma de {o['slug']}; escolha outra imagem oficial")
                break
        for e in erros:
            print(f"{f.stem}: ERRO: {e}")
        ruins += bool(erros)
        if not erros:
            print(f"{f.stem}: ok")
    return 1 if ruins else 0


def cmd_imagens(args) -> int:
    """Imagem de cada pauta publicada ou na fila: a redação confere antes de escolher a nova."""
    for p in sorted(P.todas(), key=P.criado_em):
        if p.get("status") in ("pronto", "publicado"):
            print(f"{p['status']:<9} {p['slug'][:48]:<48} {imagem_chave(p)}")
    return 0


def cmd_fila(args) -> int:
    t = agora()
    pautas = P.todas()
    for p in candidatas(pautas, t):
        print(f"pronto    {'GTA 6' if p['gta6'] else 'outros':<6}  {P.criado_em(p):%d/%m %H:%M}  {p['slug']}")
    for p in pautas:
        if p.get("status") == "pronto" and P.vencida(p, t):
            print(f"vencida   {'GTA 6' if p['gta6'] else 'outros':<6}  {P.criado_em(p):%d/%m %H:%M}  {p['slug']}")
        elif p.get("status") == "reprovado":
            print(f"reprovado {p['slug']}: {p.get('motivo', '')[:100]}")
    return 0


def cmd_agenda(args) -> int:
    t = agora()
    hoje = t.date().isoformat()
    feitos = {p["publicado"]["horario"]: p for p in _publicado_hoje(P.todas(), hoje)}
    for hhmm, tipo in CARROSSEIS:
        p = feitos.get(hhmm)
        print(f"{hhmm}  carrossel {tipo:<6}  {p['slug'] if p else '-'}")
    reel = next((p for p in feitos.values() if p.get("reel", {}).get("media_id")), None)
    print(f"{REEL}  reel              {reel['slug'] if reel else '-'}")
    gta = sum(1 for p in P.todas() if p.get("status") == "pronto" and p["gta6"] and not P.vencida(p, t))
    outros = sum(1 for p in P.todas() if p.get("status") == "pronto" and not p["gta6"] and not P.vencida(p, t))
    print(f"\nna fila: {gta} de GTA 6 e {outros} de outros jogos")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("decidir", "preparar", "publicar", "teste", "conferir", "fila", "agenda", "imagens"):
        sub.add_parser(nome)
    p = sub.add_parser("check")
    p.add_argument("slugs", nargs="*")
    args = ap.parse_args(argv)
    return {"decidir": cmd_decidir, "preparar": cmd_preparar, "publicar": cmd_publicar, "teste": cmd_teste, "conferir": cmd_conferir,
            "check": cmd_check, "fila": cmd_fila, "agenda": cmd_agenda, "imagens": cmd_imagens}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
