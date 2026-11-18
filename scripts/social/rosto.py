"""Tira a câmera do streamer de um clipe de gameplay (regra do Diego, 10/11: só a imagem
do jogo, nunca o rosto do streamer).

Como funciona: olha ~16 quadros do vídeo com o detector de rostos do OpenCV. Rosto que
aparece PARADO no mesmo lugar em boa parte dos quadros é a câmera do streamer (rosto de
personagem do jogo muda de lugar). A área da câmera é o rosto aumentado. Depois escolhe o
maior pedaço da tela que não encosta na câmera (faixa da esquerda, direita, de cima ou de
baixo) e corta o vídeo nele com o ffmpeg. Se o pedaço limpo for pequeno demais, ou se o
rosto ocupa a tela (bate-papo), o clipe é descartado.

    python -m scripts.social.rosto ENTRADA.mp4 SAIDA.mp4     (precisa de opencv e ffmpeg)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

QUADROS = 16
PARADO = 0.35        # rosto no mesmo lugar em pelo menos 35% dos quadros = câmera
AUMENTO_X, AUMENTO_Y = 1.6, 1.9   # a câmera é maior que o rosto (ombros, moldura)
AREA_MINIMA = 0.55   # o pedaço limpo precisa ter pelo menos 55% da tela
ROSTO_GRANDE = 0.06  # rosto parado com mais de 6% da tela = bate-papo, não é jogo
MARGEM = 8           # pixels de folga entre o corte e a câmera


def rostos_parados(video: Path) -> tuple[int, int, list[tuple[int, int, int, int]], int]:
    """(largura, altura, caixas de rostos parados, quadros lidos)."""
    import cv2
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(video))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    achados, lidos = [], 0
    for k in range(QUADROS):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((k + 0.5) * total / QUADROS))
        ok, q = cap.read()
        if not ok:
            continue
        lidos += 1
        cinza = cv2.cvtColor(q, cv2.COLOR_BGR2GRAY)
        for (x, y, fw, fh) in det.detectMultiScale(cinza, scaleFactor=1.1, minNeighbors=6, minSize=(max(24, w // 40),) * 2):
            achados.append((int(x), int(y), int(fw), int(fh)))
    cap.release()
    # agrupa rostos cujo centro fica perto (mesmo lugar em quadros diferentes)
    grupos: list[list[tuple[int, int, int, int]]] = []
    for r in achados:
        cx, cy = r[0] + r[2] / 2, r[1] + r[3] / 2
        for g in grupos:
            gx, gy = g[0][0] + g[0][2] / 2, g[0][1] + g[0][3] / 2
            if abs(cx - gx) < g[0][2] * 0.6 and abs(cy - gy) < g[0][3] * 0.6:
                g.append(r)
                break
        else:
            grupos.append([r])
    parados = []
    for g in grupos:
        if lidos and len(g) / lidos >= PARADO:
            x0 = min(r[0] for r in g); y0 = min(r[1] for r in g)
            x1 = max(r[0] + r[2] for r in g); y1 = max(r[1] + r[3] for r in g)
            parados.append((x0, y0, x1 - x0, y1 - y0))
    return w, h, parados, lidos


def area_camera(caixa, w, h):
    x, y, fw, fh = caixa
    cx, cy = x + fw / 2, y + fh / 2
    lw, lh = fw * (1 + 2 * AUMENTO_X), fh * (1 + 2 * AUMENTO_Y)
    return (max(0, int(cx - lw / 2)), max(0, int(cy - lh / 2)), min(w, int(cx + lw / 2)), min(h, int(cy + lh / 2)))


def melhor_corte(w: int, h: int, cameras: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
    """Maior retângulo (x, y, largura, altura) da tela que não encosta em nenhuma câmera."""
    caixa = (0, 0, w, h)
    for (a0, b0, a1, b1) in cameras:
        x, y, cw, ch = caixa
        opcoes = [
            (x, y, max(0, min(cw, a0 - MARGEM - x)), ch),                       # à esquerda da câmera
            (max(x, a1 + MARGEM), y, max(0, x + cw - max(x, a1 + MARGEM)), ch),   # à direita
            (x, y, cw, max(0, min(ch, b0 - MARGEM - y))),                        # acima
            (x, max(y, b1 + MARGEM), cw, max(0, y + ch - max(y, b1 + MARGEM))),   # abaixo
        ]
        sem_encostar = [o for o in opcoes if o[0] + o[2] <= a0 or o[0] >= a1 or o[1] + o[3] <= b0 or o[1] >= b1]
        caixa = max(sem_encostar or [(0, 0, 0, 0)], key=lambda o: o[2] * o[3])
    x, y, cw, ch = caixa
    if cw * ch < AREA_MINIMA * w * h:
        return None
    return x, y, cw - cw % 2, ch - ch % 2


def limpar(entrada: Path, saida: Path) -> dict:
    """Corta a câmera do streamer. Devolve {"ok": bool, "motivo": str, "corte": [...]}."""
    w, h, parados, lidos = rostos_parados(entrada)
    if not lidos:
        return {"ok": False, "motivo": "não consegui ler o vídeo"}
    if any(fw * fh > ROSTO_GRANDE * w * h for (_, _, fw, fh) in parados):
        return {"ok": False, "motivo": "rosto grande na tela (bate-papo, não é jogo)"}
    if not parados:
        subprocess.run(["cp", str(entrada), str(saida)], check=True)
        return {"ok": True, "motivo": "sem câmera de streamer", "corte": None}
    corte = melhor_corte(w, h, [area_camera(c, w, h) for c in parados])
    if not corte:
        return {"ok": False, "motivo": "a câmera do streamer cobre jogo demais para cortar"}
    x, y, cw, ch = corte
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(entrada), "-vf", f"crop={cw}:{ch}:{x}:{y}",
                        "-c:a", "copy", str(saida)], capture_output=True, text=True)
    if r.returncode or not saida.exists():
        return {"ok": False, "motivo": f"ffmpeg falhou: {r.stderr.strip()[-200:]}"}
    # confere de novo: se ainda sobrou rosto parado, descarta
    _, _, sobrou, _ = rostos_parados(saida)
    if sobrou:
        saida.unlink(missing_ok=True)
        return {"ok": False, "motivo": "ainda aparece rosto depois do corte"}
    return {"ok": True, "motivo": "câmera cortada", "corte": [x, y, cw, ch]}


if __name__ == "__main__":
    print(json.dumps(limpar(Path(sys.argv[1]), Path(sys.argv[2])), ensure_ascii=False))
