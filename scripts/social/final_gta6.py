"""Busca o FINAL do GTA 6 nas lives da Twitch (clipes mais vistos + fim da live gravada).

Diego, 21/11/2026: Reels do final do GTA 6 (pode ser streamer gringo, ex.: IShowSpeed, que
zerou em ~52h e transmitiu também na Twitch). O robô só junta o material bruto; a escolha
dos trechos, o recorte sem câmera e a montagem são feitos à mão na thread.

Uso:
  python -m scripts.social.final_gta6 <login>... [--desde AAAA-MM-DD] [--clipes N] [--fim MIN] [--saida DIR]
Saída: DIR/<login>-clipes.json (lista), DIR/<login>-clipe-NN-<slug>.mp4, DIR/<login>-vod-<id>-fim.mp4
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .banco import _seg
from .lives import Falha, Twitch


def baixar(url: str, saida: Path, secao: str | None = None, timeout: int = 1200) -> str:
    cmd = ["yt-dlp", "-q", "--no-warnings", "-f", "best[height<=720]/best", "-o", str(saida)]
    if secao:
        cmd += ["--download-sections", secao]
    try:
        r = subprocess.run(cmd + [url], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "tempo esgotado"
    if saida.exists() and saida.stat().st_size > 100_000:
        return "ok"
    return ((r.stderr or r.stdout or "sem arquivo").strip().splitlines() or ["sem arquivo"])[-1][:200]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("logins", nargs="+")
    ap.add_argument("--desde", default="2026-11-18")
    ap.add_argument("--clipes", type=int, default=12)
    ap.add_argument("--fim", type=int, default=30, help="minutos finais de cada live gravada (0 = não baixa)")
    ap.add_argument("--saida", default="saida")
    ap.add_argument("--vod", help="só baixa pedaços de 5 min desta live gravada (id), de --de até --ate segundos")
    ap.add_argument("--de", type=int, default=0)
    ap.add_argument("--ate", type=int, default=0)
    a = ap.parse_args()
    out = Path(a.saida)
    out.mkdir(parents=True, exist_ok=True)
    if a.vod:
        from concurrent.futures import ThreadPoolExecutor
        url = f"https://www.twitch.tv/videos/{a.vod}"
        pedacos = list(range(a.de, a.ate, 300))
        def um(t: int) -> str:
            return f"{t}: " + baixar(url, out / f"vod-{a.vod}-{t:06d}.mp4", f"*{t}-{min(t + 300, a.ate)}", timeout=1500)
        with ThreadPoolExecutor(4) as ex:
            for r in ex.map(um, pedacos):
                print(r)
        return
    tw = Twitch()
    ini = datetime.fromisoformat(a.desde).replace(tzinfo=timezone.utc)
    for login in a.logins:
        rel: dict = {"login": login, "clipes": [], "vods": []}
        try:
            u = (tw.get("users", login=login).get("data") or [None])[0]
            if not u:
                raise Falha("canal não existe")
            fim = datetime.now(timezone.utc)
            clipes = []
            t = ini
            while t < fim:  # a API devolve os mais vistos de cada janela; junta janelas de 1 dia
                d = tw.get("clips", broadcaster_id=u["id"], first=50,
                           started_at=t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           ended_at=min(fim, t + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
                clipes += d.get("data", [])
                t += timedelta(days=1)
            clipes.sort(key=lambda c: -c.get("view_count", 0))
            for c in clipes:
                rel["clipes"].append({k: c.get(k) for k in ("id", "url", "title", "view_count", "created_at", "duration", "video_id", "vod_offset")})
            for n, c in enumerate(clipes[: a.clipes], 1):
                arq = out / f"{login}-clipe-{n:02d}-{c['id'][:40]}.mp4"
                rel["clipes"][n - 1]["arquivo"] = arq.name
                rel["clipes"][n - 1]["baixou"] = baixar(c["url"], arq, timeout=300)
            vids = tw.get("videos", user_id=u["id"], type="archive", first=20).get("data", [])
            for v in vids:
                comeco = datetime.fromisoformat(v["created_at"].replace("Z", "+00:00"))
                dur = _seg(v["duration"])
                if comeco + timedelta(seconds=dur) < ini:
                    continue
                item = {"id": v["id"], "url": v["url"], "titulo": v.get("title"), "inicio": v["created_at"], "duracao_s": dur}
                if a.fim and dur > 60:
                    arq = out / f"{login}-vod-{v['id']}-fim.mp4"
                    item["arquivo"] = arq.name
                    item["baixou"] = baixar(v["url"], arq, f"*{max(0, dur - a.fim * 60)}-{dur}")
                rel["vods"].append(item)
        except Exception as e:  # noqa: BLE001 - registra e segue para o próximo canal
            rel["erro"] = str(e)[:300]
        (out / f"{login}-clipes.json").write_text(json.dumps(rel, ensure_ascii=False, indent=1))
        print(login, "clipes:", len(rel["clipes"]), "vods:", len(rel["vods"]), rel.get("erro", ""))


if __name__ == "__main__":
    main()
