"""Rota da despedida no mapa de satélite do GTA V (coordenadas na miniatura 1233x1800 = master/6)."""
import math
# pontos de controle (mini px)
CTRL = [
    (560, 1375),  # Grove Street
    (600, 1335), (650, 1305), (720, 1280), (765, 1235), (790, 1170), (815, 1090), (850, 1000),
    (880, 920), (895, 850), (880, 790), (845, 735),  # rodovia norte
    (800, 690),  # Sandy Shores
    (850, 670), (905, 620), (940, 540), (950, 450), (915, 360), (860, 295), (780, 262), (680, 255), (600, 270),
    (545, 300),  # Paleto Bay
    (480, 360), (400, 420), (320, 500), (265, 570), (230, 660), (215, 760), (195, 850), (170, 950),
    (160, 1040),  # costa oeste
    (185, 1120), (235, 1180), (290, 1235),
    (335, 1290),  # Del Perro
    (380, 1350), (405, 1420), (400, 1490), (380, 1560),
    (365, 1610),  # Aeroporto
]
PARADAS = {"grove": 0, "sandy": 12, "paleto": 22, "costa": 31, "delperro": 35, "aeroporto": 40}
ROTULO = {"grove": "Grove Street", "sandy": "Sandy Shores", "paleto": "Paleto Bay", "costa": "Costa oeste",
          "delperro": "Del Perro", "aeroporto": "Aeroporto", "rodovia": "Rodovia norte"}


def catmull(pts, n=24):
    out = []
    p = [pts[0]] + pts + [pts[-1]]
    idx = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        idx.append(len(out))
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in range(2)))
    idx.append(len(out)); out.append(pts[-1])
    return out, idx


PONTOS, IDX = catmull(CTRL)
ACUM = [0.0]
for a, b in zip(PONTOS, PONTOS[1:]):
    ACUM.append(ACUM[-1] + math.dist(a, b))
TOTAL = ACUM[-1]


def frac_parada(nome):
    return ACUM[IDX[PARADAS[nome]]] / TOTAL


def ponto(f):
    """posição e ângulo na fração f da rota."""
    alvo = max(0.0, min(1.0, f)) * TOTAL
    lo, hi = 0, len(ACUM) - 1
    while lo < hi - 1:
        m = (lo + hi) // 2
        if ACUM[m] <= alvo: lo = m
        else: hi = m
    a, b = PONTOS[lo], PONTOS[hi]
    seg = (ACUM[hi] - ACUM[lo]) or 1
    t = (alvo - ACUM[lo]) / seg
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), math.atan2(b[1] - a[1], b[0] - a[0])


if __name__ == "__main__":
    print("km aprox", TOTAL * 7.9 / 1000)
    for k in PARADAS: print(k, round(frac_parada(k), 3))
