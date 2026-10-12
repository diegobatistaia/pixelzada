"""Acha os rostos de uma imagem para o recorte não cortar a cabeça de ninguém.

Usado nas capas do site (recorte 16:9 em images.py) e nas artes do Instagram
(object-position da foto em scripts/social/arte.py). Usa o detector YuNet do
OpenCV (modelo em modelos/, licença MIT, do opencv_zoo), que acha rosto de
personagem de jogo, desenho e até rosto de lado ou com bandana. Sem OpenCV
instalado, devolve lista vazia e quem chamou segue com o enquadramento padrão.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

MODELO = Path(__file__).parent / "modelos" / "face_detection_yunet_2023mar.onnx"
LADO_ANALISE = 1280         # a detecção roda numa cópia com no máximo este lado
CONFIANCA = 0.75            # abaixo disso aparecem "rostos" em logo, controle, textura


def rostos(im: Image.Image) -> list[tuple[int, int, int, int]]:
    """Caixas (x, y, largura, altura) dos rostos, nas coordenadas de `im`."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    if not MODELO.exists():
        return []
    escala = min(1.0, LADO_ANALISE / max(im.size))
    peq = im.convert("RGB").resize((max(1, round(im.width * escala)), max(1, round(im.height * escala))))
    bgr = cv2.cvtColor(np.array(peq), cv2.COLOR_RGB2BGR)
    detector = cv2.FaceDetectorYN.create(str(MODELO), "", (bgr.shape[1], bgr.shape[0]), CONFIANCA, 0.3, 5000)
    _, achados = detector.detect(bgr)
    if achados is None:
        return []
    caixas = [tuple(int(v) for v in a[:4]) for a in achados]
    # descarta rostinhos perdidos no fundo quando há um rosto principal grande
    minimo = max(min(peq.size) * 0.04, max(c[3] for c in caixas) * 0.4)
    caixas = [c for c in caixas if c[3] >= minimo]
    return [tuple(round(v / escala) for v in c) for c in caixas]


def area_das_cabecas(caixas, justa: bool = False) -> tuple[int, int, int, int] | None:
    """Retângulo (esq, topo, dir, base) que cobre as cabeças inteiras: o rosto
    detectado mais testa/cabelo em cima e queixo/pescoço embaixo. `justa` usa
    folga mínima (só o rosto, da testa ao queixo)."""
    if not caixas:
        return None
    lado, cima, baixo = (0.05, 0.12, 1.05) if justa else (0.25, 0.4, 1.25)
    esq = min(x - lado * w for x, y, w, h in caixas)
    dir_ = max(x + (1 + lado) * w for x, y, w, h in caixas)
    topo = min(y - cima * h for x, y, w, h in caixas)
    base = max(y + baixo * h for x, y, w, h in caixas)
    return round(esq), round(topo), round(dir_), round(base)


def foco(im: Image.Image) -> str | None:
    """Ponto da imagem (em %, formato CSS object-position) que deve ficar à vista
    quando a foto for recortada em outra proporção: o centro das cabeças.
    None quando não acha rosto."""
    area = area_das_cabecas(rostos(im))
    if not area:
        return None
    esq, topo, dir_, base = area
    cx = min(100, max(0, round(100 * (esq + dir_) / 2 / im.width)))
    cy = min(100, max(0, round(100 * (topo + base) / 2 / im.height)))
    return f"{cx}% {cy}%"
