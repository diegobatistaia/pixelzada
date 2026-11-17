"""Som dos vídeos longos (Diego, 17/11/2026): trilha própria e efeitos sonoros, tudo gerado aqui.

- trilha(): synthwave "Pixelzada Vice" sintetizada (pad, baixo, arpejo e bateria), sem direito
  de terceiros, no tamanho exato do vídeo;
- efeitos(): whoosh, impacto, pop, subida (riser), glitch e blip, também sintetizados;
- linha_de_efeitos(): põe os efeitos nos momentos do vídeo (troca de cena, destaques, mapa, vinheta).

Sem dependência além do numpy. Grava WAV 44,1 kHz estéreo.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
RNG = np.random.default_rng(7)


def gravar(x: np.ndarray, arq: Path) -> Path:
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    x = np.clip(x, -1, 1)
    with wave.open(str(arq), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return arq


def _lp(x: np.ndarray, corte: float | np.ndarray) -> np.ndarray:
    """Passa-baixa de um polo (corte fixo ou variando amostra a amostra)."""
    a = np.exp(-2 * np.pi * np.asarray(corte, dtype=float) / SR)
    if a.ndim == 0:
        a = float(a)
        m = 1 << int(np.ceil(np.log2(len(x) + SR)))
        w = 2 * np.pi * np.fft.rfftfreq(m)
        h = (1 - a) / (1 - a * np.exp(-1j * w))
        return np.fft.irfft(np.fft.rfft(x, m) * h, m)[:len(x)]
    y = np.empty_like(x)
    s = 0.0
    for i in range(len(x)):
        s = (1 - a[i]) * x[i] + a[i] * s
        y[i] = s
    return y


def _saw(f: float, n: int, fase: float = 0.0) -> np.ndarray:
    t = np.arange(n) / SR
    return 2 * ((t * f + fase) % 1) - 1


def _env(n: int, ataque: float, queda: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(1, t / max(ataque, 1e-4)) * np.exp(-t / max(queda, 1e-4))


def _hz(nota: int) -> float:
    return 440.0 * 2 ** ((nota - 69) / 12)


def _eco(x: np.ndarray, atraso: float, ganho: float, vezes: int = 4) -> np.ndarray:
    y = x.copy()
    d = int(atraso * SR)
    for k in range(1, vezes + 1):
        if d * k < len(x):
            y[d * k:] += x[:-d * k] * ganho ** k
    return y


# ---------------------------------------------------------------------------
# trilha
# ---------------------------------------------------------------------------
BPM = 96
ACORDES = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]  # Lá m, Fá, Dó, Sol


def _compasso(acorde, bat: float, com_bateria: bool, com_arpejo: bool) -> tuple[np.ndarray, np.ndarray]:
    n = int(4 * bat * SR)
    pad = np.zeros(n)
    for nota in acorde:
        for det in (-0.12, 0.0, 0.11):
            pad += _saw(_hz(nota) * 2 ** (det / 12), n, RNG.random())
    pad = _lp(pad / 9, 900) * np.minimum(1, np.arange(n) / (0.4 * SR))
    baixo = np.zeros(n)
    passo = int(bat / 2 * SR)
    for k in range(8):
        f = _hz(acorde[0] - 24 + (12 if k % 2 else 0))
        seg = _saw(f, passo) * _env(passo, 0.004, 0.18)
        baixo[k * passo:(k + 1) * passo] += seg
    baixo = _lp(baixo, 420) * 0.9
    arp = np.zeros(n)
    if com_arpejo:
        p16 = int(bat / 4 * SR)
        notas = [acorde[0] + 12, acorde[1] + 12, acorde[2] + 12, acorde[1] + 24]
        for k in range(16):
            f = _hz(notas[k % 4])
            seg = np.sign(np.sin(2 * np.pi * f * np.arange(p16) / SR)) * _env(p16, 0.002, 0.07)
            arp[k * p16:(k + 1) * p16] += seg
        arp = _eco(_lp(arp, 2600), bat * 0.75, 0.35, 3) * 0.16
    bat_ = np.zeros(n)
    if com_bateria:
        pb = int(bat * SR)
        tb = np.arange(pb) / SR
        bumbo = np.sin(2 * np.pi * np.cumsum(50 + 110 * np.exp(-tb * 30)) / SR) * np.exp(-tb * 7)
        caixa = (_lp(RNG.standard_normal(pb), 5000) * 0.6 + np.sin(2 * np.pi * 190 * tb) * 0.3) * np.exp(-tb * 9)
        chimbal = (RNG.standard_normal(pb // 4) - _lp(RNG.standard_normal(pb // 4), 6000)) * _env(pb // 4, 0.001, 0.025)
        for b in range(4):
            i = b * pb
            bat_[i:i + pb] += bumbo * 0.9
            if b in (1, 3):
                bat_[i:i + pb] += _eco(caixa, 0.05, 0.4, 3) * 0.55
            for h in (0, pb // 2):
                bat_[i + h:i + h + len(chimbal)] += chimbal * 0.25
    esq = pad * 0.30 + baixo * 0.45 + arp * 1.0 + bat_ * 0.55
    dir_ = pad * 0.30 + baixo * 0.45 + np.roll(arp, int(0.012 * SR)) * 1.0 + bat_ * 0.55
    return esq, dir_


def trilha(dur: float, arq: Path) -> Path:
    """Trilha no tamanho exato: intro só com pad/baixo, depois bateria e arpejo alternando."""
    bat = 60 / BPM
    partes = {}
    for chave in ((False, False), (True, False), (True, True), (False, True)):
        e, d = [], []
        for ac in ACORDES:
            a, b = _compasso(ac, bat, *chave)
            e.append(a)
            d.append(b)
        partes[chave] = np.stack([np.concatenate(e), np.concatenate(d)], 1)
    ordem = [(False, False), (False, True), (True, True), (True, True), (True, False), (True, True),
             (False, True), (True, True)]
    n = int(dur * SR) + SR
    blocos, tot, k = [], 0, 0
    while tot < n:
        b = partes[ordem[min(k, len(ordem) - 1) if k < len(ordem) else 2 + (k % (len(ordem) - 2))]]
        blocos.append(b)
        tot += len(b)
        k += 1
    x = np.concatenate(blocos)[:int(dur * SR)]
    fade = int(3 * SR)
    x[-fade:] *= np.linspace(1, 0, fade)[:, None]
    x[:int(1.5 * SR)] *= np.linspace(0, 1, int(1.5 * SR))[:, None]
    x /= np.max(np.abs(x)) + 1e-9
    return gravar(x * 0.8, arq)


# ---------------------------------------------------------------------------
# efeitos
# ---------------------------------------------------------------------------
def efeitos() -> dict[str, np.ndarray]:
    fx = {}
    n = int(0.7 * SR)
    t = np.arange(n) / SR
    corte = 300 + 5000 * np.sin(np.pi * t / t[-1]) ** 2
    fx["whoosh"] = _lp(RNG.standard_normal(n), corte) * np.sin(np.pi * t / t[-1]) ** 1.5 * 0.9
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    grave = np.sin(2 * np.pi * np.cumsum(38 + 90 * np.exp(-t * 18)) / SR) * np.exp(-t * 3.2)
    estalo = _lp(RNG.standard_normal(n), 2500) * np.exp(-t * 22)
    fx["impacto"] = _eco(grave * 0.9 + estalo * 0.6, 0.09, 0.3, 3)
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    fx["pop"] = np.sin(2 * np.pi * np.cumsum(600 + 900 * t / t[-1]) / SR) * np.exp(-t * 28) * 0.7
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    fx["blip"] = np.sign(np.sin(2 * np.pi * 1320 * t)) * np.exp(-t * 35) * 0.25
    n = int(1.8 * SR)
    t = np.arange(n) / SR
    sobe = np.sin(2 * np.pi * np.cumsum(200 + 1400 * (t / t[-1]) ** 2) / SR) * 0.25
    fx["riser"] = (_lp(RNG.standard_normal(n), 400 + 7000 * (t / t[-1]) ** 2) * 0.6 + sobe) * (t / t[-1]) ** 2
    n = int(0.35 * SR)
    g = RNG.standard_normal(n)
    g = np.repeat(g[::40], 40)[:n] * (RNG.random(n // 2205 + 1).repeat(2205)[:n] > 0.4)
    fx["glitch"] = g * 0.35
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    fx["swoosh"] = _lp(RNG.standard_normal(n), 800 + 6000 * t / t[-1]) * np.sin(np.pi * t / t[-1]) * 0.55
    return fx


def linha_de_efeitos(eventos: list[tuple[float, str, float]], dur: float, arq: Path) -> Path:
    """eventos = (segundo, nome do efeito, ganho)."""
    fx = efeitos()
    x = np.zeros(int(dur * SR) + 2 * SR)
    for t, nome, ganho in eventos:
        s = fx[nome]
        i = max(0, int(t * SR))
        j = min(len(x), i + len(s))
        x[i:j] += s[:j - i] * ganho
    x = x[:int(dur * SR)]
    return gravar(x * 0.9, arq)


if __name__ == "__main__":
    import sys
    pasta = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    trilha(40, pasta / "teste-trilha.wav")
    linha_de_efeitos([(0.5, "riser", 1), (2.3, "impacto", 1), (3.5, "whoosh", 1), (4.5, "pop", 1),
                      (4.8, "pop", 1), (5.5, "swoosh", 1), (6.2, "glitch", 1), (7, "blip", 1)], 9,
                     pasta / "teste-efeitos.wav")
