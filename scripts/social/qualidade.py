"""Barreira de tela quebrada nos Reels (Diego, 18/11).

Em 18/11 saiu um Reel com a tela roxa da Twitch "Commercial break in progress"
(gravação do canal gta6news caiu no intervalo comercial). Esta checagem olha 20
quadros do vídeo final e recusa o Reel quando aparece a tela de intervalo da
Twitch: um degradê roxo/magenta liso, sem detalhe, que nenhum jogo tem.

    python -m scripts.social.qualidade varrer          # tira da fila os agendados com tela ruim
    python -m scripts.social.qualidade testar A.mp4    # nota de cada quadro
"""
from __future__ import annotations

import sys
from pathlib import Path

LIMITE = 0.05      # fração do quadro em roxo liso; a tela de intervalo dá ~0.11, mapa/menu do jogo 0.0
QUADROS = 20


def notas(mp4: Path) -> list[float]:
    import cv2
    import numpy as np
    cap = cv2.VideoCapture(str(mp4))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    out = []
    for k in range(QUADROS):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (k + 0.5) / QUADROS))
        ok, f = cap.read()
        if not ok:
            continue
        hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        liso = np.abs(cv2.Laplacian(cv2.GaussianBlur(g, (5, 5), 0), cv2.CV_32F)) < 2
        roxo = (hsv[..., 0] > 125) & (hsv[..., 0] < 165) & (hsv[..., 1] > 120) & (hsv[..., 2] > 60)
        out.append(float((roxo & liso).mean()))
    cap.release()
    return out


def tela_ruim(mp4: Path) -> str | None:
    """Motivo, se o vídeo tem tela de intervalo da Twitch; None se está ok."""
    try:
        v = notas(mp4)
    except Exception as e:  # sem opencv: não bloqueia a montagem
        print(f"  checagem de tela pulada ({e})")
        return None
    ruins = sum(1 for x in v if x > LIMITE)
    if ruins:
        return f"tela de intervalo da Twitch em {ruins} de {len(v)} quadros"
    return None


def varrer() -> int:
    from datetime import datetime
    from . import reels as R, seguranca as SEG
    from .pauta import TZ
    fila = R.carregar()
    agora = datetime.now(TZ)
    tirados = []
    for item in list(fila):
        if item.get("status") != "agendado" or R.quando(item) <= agora:
            continue
        mp4 = R.PASTA / "videos" / f"{item['slug']}.mp4"
        if not mp4.exists():
            continue
        motivo = tela_ruim(mp4)
        if motivo:
            SEG.tirar_da_fila(fila, item, {"risco": "tela", "motivo": motivo, "por": "qualidade",
                                           "em": agora.isoformat(timespec="seconds")})
            tirados.append(item["slug"])
            print(f"  {item['slug']} ({item['data']} {item['horario']}): {motivo}; saiu da fila")
    if tirados:
        R.salvar(fila)
    print(f"{len(tirados)} Reel(s) barrado(s) por tela quebrada")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["varrer"]:
        return varrer()
    if argv[:1] == ["testar"]:
        for a in argv[1:]:
            v = notas(Path(a))
            print(a, "RUIM" if any(x > LIMITE for x in v) else "ok", [round(x, 3) for x in v])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
