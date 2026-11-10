"""Reels de vídeo do @pixelzada.br: vídeos prontos (já na identidade visual) em horários fixos.

Os vídeos ficam em social/reels/videos/ e a fila em social/reels/fila.json. O
Claude monta o vídeo e põe na fila com data e horário; o workflow Reels
(.github/workflows/reels.yml) publica sozinho, na hora, sem ninguém aprovar.

    python -m scripts.social.reels decidir    só diz se há Reel neste horário
    python -m scripts.social.reels preparar   separa o vídeo e a capa em social/saida/reel-<slug>/
    (o workflow envia a pasta para pixelzada.com.br/ig/reel-<slug>/)
    python -m scripts.social.reels publicar   chama a API do Instagram

Na sessão do Claude (sem chave, sem internet):

    python -m scripts.social.reels gaveta     quantos vídeos há na fila e até que dia ela cobre
    python -m scripts.social.reels check      confere os arquivos e os horários da fila
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date, datetime, timedelta

from . import instagram as IG, pauta as P

PASTA = P.ROOT / "social" / "reels"
FILA = PASTA / "fila.json"
PEDIDO = P.SAIDA / "pedido-reel.json"
# Horários fixos (Brasília): 6 por dia nas horas pares, entre os carrosséis
# (9h, 11h, 13h, 15h, 17h, 19h e 21h).
HORARIOS = ["10:00", "12:00", "14:00", "16:00", "18:00", "20:00"]  # grade antiga (até 09/11)

# Aquecimento para o GTA 6 (Diego, 09/11): 15 Reels/dia de 10 a 15/11 e 25/dia a partir
# de 16/11. Sem carrosséis (pausados em 10/11), o Diego quer tudo SÓ entre 7h e 21h
# (10/11), até ele liberar mais horários: 15/dia de hora em hora (7h, 8h ... 21h) e
# 25/dia de 35 em 35 minutos (7h00, 7h35, 8h10 ... 21h00).
JANELA = ("07:00", "21:00")
GRADE_15 = [f"{h:02d}:00" for h in range(7, 22)]                                    # 07:00 .. 21:00
GRADE_25 = [f"{(420 + 35 * i) // 60:02d}:{(420 + 35 * i) % 60:02d}" for i in range(25)]  # 07:00 .. 21:00


def horarios(dia: date | str) -> list[str]:
    dia = date.fromisoformat(dia) if isinstance(dia, str) else dia
    if dia >= date(2026, 11, 16):
        return GRADE_25
    if dia >= date(2026, 11, 10):
        return GRADE_15
    return HORARIOS


POR_DIA = len(HORARIOS)
# Mesma janela dos carrosséis (1h50): o GitHub atrasa os agendamentos, e a
# janela fecha antes do Reel seguinte.
ANTES, DEPOIS = timedelta(minutes=2), timedelta(minutes=110)
# Com 15 a 25 Reels por dia o GitHub atrasa mais que o intervalo entre eles. Então a
# fila anda em ordem: cada rodada (de 10 em 10 min) publica o Reel agendado mais antigo
# que já passou da hora, desde que o último tenha saído há pelo menos INTERVALO_MIN.
INTERVALO_MIN = timedelta(minutes=20)
ATRASO_MAX = timedelta(hours=6)   # passou disso sem sair: vai para o próximo horário livre
TENTATIVAS = 3


def carregar() -> list[dict]:
    return json.loads(FILA.read_text(encoding="utf-8")) if FILA.exists() else []


def salvar(fila: list[dict]) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    fila.sort(key=lambda i: (i["data"], i["horario"]))
    FILA.write_text(json.dumps(fila, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def quando(item: dict) -> datetime:
    return datetime.fromisoformat(f"{item['data']}T{item['horario']}:00").replace(tzinfo=P.TZ)


def reagendar(fila: list[dict], t: datetime) -> list[str]:
    """Reel cuja janela passou sem sair vai para o próximo horário livre (nunca se perde)."""
    avisos = []
    for item in [i for i in fila if i["status"] == "agendado" and t > quando(i) + ATRASO_MAX]:
        ocupados = {(i["data"], i["horario"]) for i in fila if i is not item and i["status"] in ("agendado", "publicado")}
        dia = t.date()
        while True:
            livre = next((h for h in horarios(dia) if (dia.isoformat(), h) not in ocupados
                          and datetime.fromisoformat(f"{dia.isoformat()}T{h}:00").replace(tzinfo=P.TZ) > t), None)
            if livre:
                break
            dia += timedelta(days=1)
        avisos.append(f"{item['slug']}: {item['data']} {item['horario']} passou; vai para {dia.isoformat()} {livre}")
        item.update(data=dia.isoformat(), horario=livre, tentativas=0)
        item.pop("erro", None)
    return avisos


def escolher(t: datetime | None = None, fila: list[dict] | None = None) -> dict | None:
    t = t or IG.agora()
    fila = fila if fila is not None else carregar()
    abertos = [i for i in fila if i["status"] == "agendado" and i.get("tentativas", 0) < TENTATIVAS
               and quando(i) - ANTES <= t <= quando(i) + ATRASO_MAX]
    if not abertos:
        return None
    ultimos = [datetime.fromisoformat(i["publicado"]["em"]) for i in fila
               if i.get("status") == "publicado" and (i.get("publicado") or {}).get("em")]
    if ultimos and t - max(ultimos) < INTERVALO_MIN:
        return None  # saiu um há pouco; o próximo espera a rodada seguinte
    return min(abertos, key=quando)  # o mais antigo primeiro: a fila anda em ordem


def pasta_saida(item: dict):
    return P.SAIDA / f"reel-{item['slug']}"


def cmd_decidir(args) -> int:
    t = IG.agora()
    fila = carregar()
    for a in reagendar(fila, t):
        print("reagendado:", a)
        salvar(fila)
    item = escolher(t, fila)
    print(f"agora: reel {item['slug']} ({item['horario']})" if item else "nenhum Reel neste horário")
    IG._saida(acao="reel" if item else "nada")
    return 0


def cmd_preparar(args) -> int:
    P.SAIDA.mkdir(parents=True, exist_ok=True)
    PEDIDO.unlink(missing_ok=True)
    item = escolher()
    if not item:
        IG._saida(acao="nada")
        return 0
    pasta = pasta_saida(item)
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir(parents=True)
    shutil.copy(PASTA / "videos" / f"{item['slug']}.mp4", pasta / "video.mp4")
    shutil.copy(PASTA / "videos" / f"{item['slug']}.jpg", pasta / "capa.jpg")
    PEDIDO.write_text(json.dumps({"acao": "reel", "slug": item["slug"], "pasta": pasta.name, "horario": item["horario"],
                                  "data": item["data"]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"pedido: reel {item['slug']} ({item['horario']})")
    IG._saida(acao="reel", slug=pasta.name)
    return 0


def cmd_publicar(args) -> int:
    pedido = json.loads(PEDIDO.read_text(encoding="utf-8"))
    fila = carregar()
    item = next(i for i in fila if i["slug"] == pedido["slug"])
    t = IG.agora().isoformat(timespec="seconds")
    resultado = {"pedido": pedido, "em": t}
    try:
        if item["status"] != "agendado":
            raise IG.ApiError(f"{item['slug']} está {item['status']}; nada publicado")
        token, ig = IG.conta()
        video, capa = IG.url_publica(pedido["pasta"], "video.mp4"), IG.url_publica(pedido["pasta"], "capa.jpg")
        IG.conferir_urls([video, capa])
        c = IG.call("POST", f"{ig}/media", token, media_type="REELS", video_url=video, cover_url=capa,
                    caption=item["legenda"], share_to_feed="true")
        IG.esperar(c["id"], token, tentativas=60, pausa=10)
        permalink = None
        try:
            pub = IG.call("POST", f"{ig}/media_publish", token, creation_id=c["id"])
        except IG.ApiError as e:
            # O Instagram às vezes devolve 403 (2207051) e publica mesmo assim: antes de dar por
            # falho (e tentar de novo, duplicando o Reel), procura o post pela legenda.
            achado = IG._ja_publicado(item["legenda"], ig, token)
            if not achado:
                raise
            print(f"AVISO: media_publish deu erro, mas o Reel já está no ar: {achado['permalink']} ({e})")
            pub, permalink = {"id": achado["id"]}, achado.get("permalink")
        # Grava já: se o resto falhar, o Reel não sai de novo.
        item.update(status="publicado", publicado={"em": t, "media_id": pub["id"]})
        salvar(fila)
        try:
            item["publicado"]["permalink"] = permalink or IG.call("GET", pub["id"], token, fields="permalink").get("permalink")
        except IG.ApiError as e:
            print(f"AVISO: sem o link do Reel: {e}")
        salvar(fila)
        resultado.update(ok=True, **item["publicado"])
        print(f"reel publicado: {item['publicado'].get('permalink')}")
        resultado["chave"] = IG.renovar(token)
    except IG.ApiError as e:
        item["tentativas"] = item.get("tentativas", 0) + 1
        item["erro"] = str(e)
        salvar(fila)
        resultado.update(ok=False, erro=str(e))
        print(f"ERRO: {e}")
    IG._gravar(resultado)
    return 0 if resultado["ok"] else 1


def cmd_gaveta(args) -> int:
    fila = carregar()
    pend = [i for i in fila if i["status"] == "agendado"]
    for i in fila:
        print(f"{i['data']} {i['horario']}  {i['status']:<10} {i['slug']}")
    print(f"\nna gaveta: {len(pend)} vídeo(s) agendado(s)")
    if pend:
        print(f"cobre até {max(i['data'] for i in pend)} ({POR_DIA} por dia; faltam {max(0, 7 * POR_DIA - len(pend))} para fechar uma semana)")
        if len(pend) < 2 * POR_DIA:
            print(f"GAVETA BAIXA: menos de 2 dias de vídeos ({len(pend)} de {2 * POR_DIA})")
    return 0


def cmd_check(args) -> int:
    erros = []
    vistos = set()
    for i in carregar():
        for k in ("slug", "data", "horario", "legenda", "status"):
            if not i.get(k):
                erros.append(f"{i.get('slug', '?')}: falta {k}")
        if i.get("status") != "publicado" and i.get("horario") not in horarios(i["data"]):  # publicados ficam como saíram
            erros.append(f"{i['slug']}: horário {i.get('horario')} não é da grade de {i['data']}")
        if (i["data"], i["horario"]) in vistos:
            erros.append(f"{i['slug']}: horário repetido {i['data']} {i['horario']}")
        vistos.add((i["data"], i["horario"]))
        for ext in ("mp4", "jpg"):
            if i["status"] == "agendado" and not (PASTA / "videos" / f"{i['slug']}.{ext}").exists():
                erros.append(f"{i['slug']}: falta social/reels/videos/{i['slug']}.{ext}")
        if len(i.get("legenda", "")) > 2200:
            erros.append(f"{i['slug']}: legenda passa de 2200 caracteres")
    for e in erros:
        print("ERRO:", e)
    print("fila ok" if not erros else f"{len(erros)} problema(s)")
    return 1 if erros else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("decidir", "preparar", "publicar", "gaveta", "check"):
        sub.add_parser(nome)
    args = ap.parse_args(argv)
    return {"decidir": cmd_decidir, "preparar": cmd_preparar, "publicar": cmd_publicar,
            "gaveta": cmd_gaveta, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
