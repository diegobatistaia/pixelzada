"""Barreira de tela quebrada nos Reels (Diego, 18/11).

Em 18/11 saiu um Reel com a tela roxa da Twitch "Commercial break in progress"
(gravação do canal gta6news caiu no intervalo comercial). Esta checagem olha 20
quadros do vídeo final e recusa o Reel quando aparece a tela de intervalo da
Twitch: faixa lisa de lado a lado em degradê do azul ao magenta (18/11: a 1ª versão
barrava mapa roxo e cena de neon por engano).

    python -m scripts.social.qualidade varrer          # tira da fila os agendados com tela ruim
    python -m scripts.social.qualidade testar A.mp4    # nota de cada quadro
"""
from __future__ import annotations

import sys
from pathlib import Path

QUADROS = 20


def _quadro(f) -> float:
    """Faixa da tela de intervalo da Twitch: linhas inteiras de cor lisa azul->magenta.

    Devolve a fração da altura nessa faixa quando o degradê vai do azul (esquerda) ao
    magenta (direita); 0 se não. Mapa roxo, neon e céu não têm esse degradê de lado a lado.
    """
    import cv2
    import numpy as np
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    liso = np.abs(cv2.Laplacian(cv2.GaussianBlur(g, (5, 5), 0), cv2.CV_32F)) < 2
    h = hsv[..., 0].astype(int)
    cor = (h > 95) & (h < 165) & (hsv[..., 1] > 90) & (hsv[..., 2] > 40) & liso
    faixa = cor.mean(axis=1) > 0.9
    if faixa.mean() < 0.06:
        return 0.0
    linhas = h[faixa]
    w = linhas.shape[1]
    degrade = linhas[:, -w // 10:].mean() - linhas[:, :w // 10].mean()
    return float(faixa.mean()) if degrade >= 15 else 0.0


def notas(mp4: Path) -> list[float]:
    import cv2
    cap = cv2.VideoCapture(str(mp4))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    out = []
    for k in range(QUADROS):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (k + 0.5) / QUADROS))
        ok, f = cap.read()
        if ok:
            out.append(_quadro(f))
    cap.release()
    return out


def tela_ruim(mp4: Path) -> str | None:
    """Motivo, se o vídeo tem tela de intervalo da Twitch; None se está ok."""
    try:
        v = notas(mp4)
    except Exception as e:  # sem opencv: não bloqueia a montagem
        print(f"  checagem de tela pulada ({e})")
        return None
    ruins = sum(1 for x in v if x > 0)
    if ruins >= 2:  # 1 quadro sozinho pode ser coincidência
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
            print(a, "RUIM" if sum(1 for x in v if x > 0) >= 2 else "ok", [round(x, 3) for x in v])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
