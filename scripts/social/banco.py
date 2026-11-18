"""Banco de cortes de GTA 6 tirados das lives gravadas (VODs) da Twitch.

Diego, 18/11/2026: deixar cortes de gameplay já prontos e guardados, de vários streamers
brasileiros (não só o Alanzoka), para os vídeos longos do YouTube e para os Reels.

Para cada live gravada do dia, o robô pega trechos espaçados ao longo da live, a IA
(camera_ia.perguntar) descarta menu, loading, cutscene, outro jogo e câmera tomando a tela,
e cada corte bom fica guardado em duas versões:
  - <id>-jogo.mp4: só o jogo, 1280x720, câmera recortada fora (vídeos longos do YouTube);
  - <id>-live.mp4: o trecho como estava na live, com a câmera (Reels no formato dividido).
Os vídeos vão como arquivos da release "banco-gta6" do GitHub (fora do repositório); a lista
fica em social/banco/indice.json e a miniatura em social/banco/mini/<id>.jpg.

Uso:
  python -m scripts.social.banco coletar <login> [--desde AAAA-MM-DD] [--max N] [--saida DIR]
  python -m scripts.social.banco juntar DIR...   (junta os pedaços de índice no indice.json)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from . import camera_ia
from . import rosto
from .lives import TZ, Falha, Twitch

RAIZ = Path(__file__).resolve().parents[2]
BANCO = RAIZ / "social" / "banco"
INDICE = BANCO / "indice.json"
RELEASE = "banco-gta6"
DUR = 40          # segundos por corte
INICIO = 8 * 60   # pula os primeiros minutos da live (abertura, chat, loading)
PASSO_MIN = 4 * 60
DESVIOS = (0, 150, 330)  # cutscene/menu: tenta 2,5 e 5,5 min depois
PARALELO = 3


def _seg(d: str) -> int:
    t = 0
    for n, u in re.findall(r"(\d+)([hms])", d or ""):
        t += int(n) * {"h": 3600, "m": 60, "s": 1}[u]
    return t


def lives_gravadas(tw: Twitch, login: str, desde: datetime) -> list[dict]:
    u = tw.get("users", login=login).get("data") or []
    if not u:
        raise Falha(f"canal {login} não existe")
    vids = tw.get("videos", user_id=u[0]["id"], type="archive", first=10).get("data", [])
    saida = []
    for v in vids:
        ini = datetime.fromisoformat(v["created_at"].replace("Z", "+00:00")).astimezone(TZ)
        if ini + timedelta(seconds=_seg(v["duration"])) >= desde:
            saida.append({"id": v["id"], "url": v["url"], "inicio": ini.isoformat(timespec="minutes"),
                          "duracao": _seg(v["duration"]), "titulo": v.get("title", ""), "canal": u[0]["display_name"]})
    return saida


def pontos(dur: int, n: int) -> list[int]:
    """n instantes espalhados pela live (no máximo 1 a cada PASSO_MIN)."""
    util = dur - INICIO - DUR - 60
    if util <= 0:
        return []
    n = max(1, min(n, util // PASSO_MIN + 1))
    passo = util / n
    return [int(INICIO + passo * (i + 0.5)) for i in range(n)]


def baixar_trecho(url: str, t: int, saida: Path) -> bool:
    cmd = ["yt-dlp", "-q", "--no-warnings", "-f", "best[height<=720]/best", "--download-sections",
           f"*{t}-{t + DUR}", "--force-keyframes-at-cuts", "-o", str(saida), url]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:
        return False
    return saida.exists() and saida.stat().st_size > 100_000


def versao_jogo(bruto: Path, caixas: list, saida: Path) -> tuple[bool, str]:
    """1280x720 só com o jogo: recorta a câmera fora e confere de novo com a IA."""
    w, h = camera_ia._tamanho(bruto)
    filtro = "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720"
    if caixas:
        F = camera_ia.FOLGA
        cams = [(max(0, int((x0 - F) * w / 1000)), max(0, int((y0 - F) * h / 1000)),
                 min(w, int((x1 + F) * w / 1000)), min(h, int((y1 + F) * h / 1000))) for (y0, x0, y1, x1) in caixas]
        corte = rosto.melhor_corte(w, h, cams)
        if not corte or corte[2] * corte[3] < 0.35 * w * h:
            return False, "câmera tira jogo demais para a versão sem câmera"
        x, y, cw, ch = corte
        filtro = f"crop={cw}:{ch}:{x}:{y}," + filtro
    f = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(bruto), "-vf", filtro + ",fps=30,format=yuv420p",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-b:a", "128k",
                        "-movflags", "+faststart", str(saida)], capture_output=True, text=True)
    if f.returncode or not saida.exists():
        return False, f"ffmpeg: {f.stderr.strip()[-120:]}"
    if caixas:
        r = camera_ia.perguntar(saida)
        if r["pessoa_real"] is not False:
            return False, f"ainda há pessoa real depois do corte ({r['motivo']})"
    return True, "ok"


def reduzir(bruto: Path, saida: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(bruto), "-vf", "scale=-2:720,fps=30,format=yuv420p",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", str(saida)], capture_output=True)


def miniatura(video: Path, saida: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "15", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=480:-2", "-q:v", "5", str(saida)], capture_output=True)


def ja_no_banco() -> set[str]:
    if not INDICE.exists():
        return set()
    return {c["id"] for c in json.loads(INDICE.read_text(encoding="utf-8")).get("cortes", [])}


def processar(login: str, v: dict, t0: int, saida: Path) -> tuple[dict | None, list[str]]:
    """Um ponto da live: se cair em cutscene/menu, tenta um pouco mais para frente (DESVIOS)."""
    motivos = []
    for d in DESVIOS:
        t = t0 + d
        if t + DUR > v["duracao"] - 30:
            break
        cid = f"{login.lower()}-{v['id']}-{t0:05d}"
        with tempfile.TemporaryDirectory() as tmp:
            bruto = Path(tmp) / "bruto.mp4"
            if not baixar_trecho(v["url"], t, bruto):
                motivos.append("download falhou")
                print(f"  {cid} (+{d}s): download falhou")
                continue
            r = camera_ia.perguntar(bruto)
            motivo = None
            if r["pessoa_real"] is None:
                motivo = "IA indisponível"
            elif r.get("conteudo") in ("cutscene", "menu"):
                motivo = r["conteudo"]
            elif not r.get("gta", True):
                motivo = "não é GTA"
            elif r["pessoa_real"] and r["caixas"]:
                c = max(r["caixas"], key=lambda c: (c[2] - c[0]) * (c[3] - c[1]))
                if (c[2] - c[0]) * (c[3] - c[1]) > 600_000:
                    motivo = "câmera ocupa a tela"
            elif r["pessoa_real"]:
                motivo = "pessoa real sem posição"
            if motivo:
                motivos.append(motivo)
                (saida / "descartes").mkdir(exist_ok=True)
                miniatura(bruto, saida / "descartes" / f"{cid}-{d}-{motivo.split()[0]}.jpg")
                print(f"  {cid} (+{d}s): descartado ({motivo}: {r['motivo'][:80]})")
                continue
            jogo = saida / f"{cid}-jogo.mp4"
            ok, m = versao_jogo(bruto, r["caixas"] if r["pessoa_real"] else [], jogo)
            live = saida / f"{cid}-live.mp4"
            reduzir(bruto, live)
            if not live.exists():
                motivos.append("ffmpeg falhou")
                continue
            miniatura(jogo if ok else live, saida / "mini" / f"{cid}.jpg")
            if not ok and jogo.exists():
                jogo.unlink()
            hh, mm = divmod(t // 60, 60)
            print(f"  {cid} (+{d}s): OK ({r.get('cena') or r['motivo']}){'' if ok else ' [só versão live: ' + m + ']'}")
            return {
                "id": cid, "canal": v["canal"], "login": login.lower(), "vod": v["id"],
                "live": v["inicio"], "titulo_live": v["titulo"][:120], "t": t, "dur": DUR,
                "link": f"{v['url']}?t={hh}h{mm}m{t % 60}s", "cena": r.get("cena", ""),
                "camera": [max(r["caixas"], key=lambda c: (c[2] - c[0]) * (c[3] - c[1]))] if r["pessoa_real"] else [],
                "jogo": jogo.name if ok else None, "sem_jogo_motivo": None if ok else m,
                "live_mp4": live.name, "motivo_ia": r["motivo"],
            }, motivos
    return None, motivos


def coletar(login: str, desde: datetime, maximo: int, saida: Path) -> int:
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "mini").mkdir(exist_ok=True)
    tw = Twitch()
    vods = lives_gravadas(tw, login, desde)
    if not vods:
        print(f"{login}: nenhuma live gravada desde {desde:%d/%m %H:%M} (ou o canal não guarda as lives)")
        return 0
    total = sum(v["duracao"] for v in vods)
    print(f"{login}: {len(vods)} live(s) gravada(s), {total / 3600:.1f} h")
    ja = ja_no_banco()
    tarefas = []
    for v in vods:
        n = max(1, round(maximo * v["duracao"] / total)) if total else maximo
        tarefas += [(v, t) for t in pontos(v["duracao"], n) if f"{login.lower()}-{v['id']}-{t:05d}" not in ja]
    cortes, descartes = [], {}
    with ThreadPoolExecutor(max_workers=PARALELO) as ex:
        for corte, motivos in ex.map(lambda vt: processar(login, vt[0], vt[1], saida), tarefas):
            for m in motivos:
                descartes[m] = descartes.get(m, 0) + 1
            if corte:
                cortes.append(corte)
    (saida / f"indice-{login.lower()}.json").write_text(json.dumps({"cortes": cortes, "descartes": descartes},
                                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{login}: {len(cortes)} corte(s) no banco; descartes: {descartes}")
    return len(cortes)


def juntar(pastas: list[Path]) -> int:
    BANCO.mkdir(parents=True, exist_ok=True)
    (BANCO / "mini").mkdir(exist_ok=True)
    dado = json.loads(INDICE.read_text(encoding="utf-8")) if INDICE.exists() else {"cortes": []}
    ids = {c["id"] for c in dado["cortes"]}
    novos = 0
    for p in pastas:
        for f in sorted(p.rglob("indice-*.json")):
            for c in json.loads(f.read_text(encoding="utf-8"))["cortes"]:
                if c["id"] in ids:
                    continue
                c["url_jogo"] = f"https://github.com/diegobatistaia/pixelzada/releases/download/{RELEASE}/{c['jogo']}" if c["jogo"] else None
                c["url_live"] = f"https://github.com/diegobatistaia/pixelzada/releases/download/{RELEASE}/{c['live_mp4']}"
                dado["cortes"].append(c)
                ids.add(c["id"])
                novos += 1
                m = f.parent / "mini" / f"{c['id']}.jpg"
                if m.exists():
                    shutil.copy(m, BANCO / "mini" / m.name)
    dado["cortes"].sort(key=lambda c: (c["login"], c["vod"], c["t"]))
    dado["atualizado"] = datetime.now(TZ).isoformat(timespec="minutes")
    INDICE.write_text(json.dumps(dado, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    por = {}
    for c in dado["cortes"]:
        por[c["canal"]] = por.get(c["canal"], 0) + 1
    print(f"{novos} corte(s) novo(s); banco com {len(dado['cortes'])}: {por}")
    return novos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="banco")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("coletar")
    c.add_argument("login")
    c.add_argument("--desde", default="")
    c.add_argument("--max", type=int, default=30)
    c.add_argument("--saida", default="banco-saida")
    j = sub.add_parser("juntar")
    j.add_argument("pastas", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "coletar":
        desde = (datetime.fromisoformat(a.desde).replace(tzinfo=TZ) if a.desde
                 else datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=6))
        try:
            coletar(a.login, desde, a.max, Path(a.saida))
        except Falha as e:
            print(f"{a.login}: {e}")
        return 0
    juntar([Path(p) for p in a.pastas])
    return 0


if __name__ == "__main__":
    sys.exit(main())
