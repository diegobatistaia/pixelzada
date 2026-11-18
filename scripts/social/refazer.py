"""Refaz Reels já agendados na moldura simples branca (Diego, 18/11: todo Reel que não é
corte de streamer sai com moldura branca e o título escrito).

Baixa de novo o vídeo original pelo link da origem (yt-dlp), monta com o gerador no
estilo simples-branca, com o título tirado da legenda já revisada, e troca o arquivo
no mesmo horário da fila. Se o download ou a montagem falhar, o Reel fica como estava.

    python -m scripts.social.refazer todos          agendados não-streamer que não são Simples branca
    python -m scripts.social.refazer slug1,slug2    só estes
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from . import montagem as M
from . import reels as R
from .pesquisa import baixar_ytdlp

EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\uFE0F\u200D]+")


def titulo_da_legenda(legenda: str) -> str:
    linha = (legenda or "").split("\n")[0]
    primeira = EMOJI.split(linha)[0].strip()   # o título é a frase antes do 1º emoji
    linha = primeira if len(primeira) >= 15 else EMOJI.sub("", linha).strip()
    return re.sub(r"\s+", " ", linha).strip(" .")


def eh_streamer(item: dict) -> bool:
    return ((item.get("origem") or {}).get("perfil") or "").lower().startswith(("twitch/", "kick/"))


def escolher(fila: list[dict], alvo: str) -> list[dict]:
    agora = datetime.now(M.TZ)
    futuros = [i for i in fila if i["status"] == "agendado" and R.quando(i) > agora]
    if alvo == "todos":
        return [i for i in futuros if not eh_streamer(i) and i.get("estilo") != "Simples branca"
                and (i.get("origem") or {}).get("link")]
    slugs = {s.strip() for s in alvo.split(",") if s.strip()}
    return [i for i in futuros if i["slug"] in slugs]


def main(argv: list[str]) -> int:
    alvo = argv[0] if argv else "todos"
    fila = R.carregar()
    itens = escolher(fila, alvo)
    print(f"{len(itens)} Reel(s) para refazer em Simples branca")
    if not itens:
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pedido, por_saida = [], {}
        for n, item in enumerate(itens):
            bruto = tmp / f"{item['slug']}.mp4"
            if not baixar_ytdlp(item["origem"]["link"], bruto) or not bruto.exists():
                print(f"  {item['slug']}: não baixou ({item['origem']['link']}); fica como está")
                continue
            tema = (item.get("etiquetas") or {}).get("tema")
            tema = tema if tema in M.CTA else "gta6"
            saida = tmp / "saida" / item["slug"]
            pedido.append({"video": str(bruto), "saida": str(saida), "estilo": "simples-branca",
                           "cor": M.CORES[n % len(M.CORES)], "jogo": (item.get("etiquetas") or {}).get("jogo", ""),
                           "titulo": titulo_da_legenda(item.get("legenda", "")), "frase": M.CTA[tema], "max_seg": 40})
            por_saida[str(saida)] = item
        if not pedido:
            return 0
        ped, res = tmp / "pedido.json", tmp / "resultado.json"
        ped.write_text(json.dumps(pedido, ensure_ascii=False), encoding="utf-8")
        subprocess.run(["node", str(M.GERADOR), str(ped), str(res)], check=False)
        resultado = json.loads(res.read_text(encoding="utf-8")) if res.exists() else []
        feitos = 0
        for r in resultado:
            item = por_saida.get(r["saida"])
            if not item:
                continue
            if not r.get("ok"):
                print(f"  {item['slug']}: montagem falhou ({r.get('erro', '')[:120]}); fica como está")
                continue
            for ext in (".mp4", ".jpg"):
                novo = Path(r["saida"] + ext)
                if novo.exists():
                    (M.VIDEOS / f"{item['slug']}{ext}").write_bytes(novo.read_bytes())
            et = item.setdefault("etiquetas", {})
            et["estilo_antes"] = item.get("estilo")
            et["moldura"] = "simples-branca"
            item["estilo"] = "Simples branca"
            feitos += 1
            print(f"  {item['slug']}: refeito em Simples branca ({item['data']} {item['horario']})")
    R.salvar(fila)
    print(f"{feitos} de {len(itens)} refeito(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
