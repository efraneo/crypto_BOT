"""Screener: selecciona el Top 5 de criptos con mejor señal para operar.

Pipeline:
  1. Filtra pares USDT por liquidez (volumen real > $20M/24h) y descarta
     stables y tokens apalancados (UP/DOWN/BULL/BEAR).
  2. Pre-score: liquidez 40% + volatilidad 'saludable' 30% + momentum 30%.
  3. Para los ~35 mejores, descarga velas y calcula la predicción del bot.
  4. Score final: fuerza de señal 50% + liquidez 25% + volatilidad ideal 25%.
"""

import math

import numpy as np

from . import indicators, market_data, predictor
from .config import STABLES


def candidatos(tickers, min_qvol=20e6):
    out = []
    for t in tickers:
        s = t["symbol"]
        if not s.endswith("USDT"):
            continue
        if s in STABLES:
            continue
        if any(s.endswith(x) for x in ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")):
            continue
        if t["qvol"] < min_qvol or t["last"] <= 0:
            continue
        out.append(t)
    return out


def _norm(a, lo, hi):
    a = np.asarray(a, float)
    return np.clip((a - lo) / (hi - lo), 0, 1)


def prescore(cs):
    for t in cs:
        t["rango_pct"] = (t["high"] - t["low"]) / t["low"] * 100 if t["low"] > 0 else 0.0
    vols = [math.log10(max(t["qvol"], 1)) for t in cs]
    rngs = [min(t["rango_pct"], 15) for t in cs]
    moms = [min(abs(t["pct"]), 20) for t in cs]
    nv, nr, nm = _norm(vols, 7, 9.5), _norm(rngs, 1.5, 8), _norm(moms, 2, 12)
    for t, a, b, c in zip(cs, nv, nr, nm):
        t["prescore"] = 0.4 * a + 0.3 * b + 0.3 * c
    cs.sort(key=lambda t: t["prescore"], reverse=True)
    return cs


def top5(tickers, interval="15m", klimit=300, n_final=5, pre=35):
    """Devuelve la lista de los mejores pares, ordenada por score final."""
    cs = prescore(candidatos(tickers))[:pre]
    for t in cs:
        try:
            df = market_data.klines(t["symbol"], interval, klimit)
            dfi = indicators.add_all(df)
            pred, _ = predictor.predict(dfi)
            t["prob"] = pred["prob"]
            t["conf"] = pred["confianza"]
            t["dir"] = pred["dir"]
            t["patron"] = ", ".join(p["nombre"] for p in pred["patrones"][:2]) or "—"
            t["atr_pct"] = float(dfi["atr_pct"].iloc[-1])
            t["senal"] = max(0.0, pred["confianza"] / 100)
        except Exception:
            t.update({"prob": 0.5, "conf": 0.0, "dir": "—", "patron": "—",
                      "atr_pct": 0.0, "senal": 0.0})
    liq = _norm([math.log10(max(t["qvol"], 1)) for t in cs], 7, 9.5)
    for t, l in zip(cs, liq):
        vol_ideal = 1 - min(abs(t["atr_pct"] - 3.75) / 3.75, 1.0) if t["atr_pct"] else 0
        t["score_final"] = 0.5 * t["senal"] + 0.25 * l + 0.25 * vol_ideal
    cs.sort(key=lambda t: t["score_final"], reverse=True)
    return cs[:n_final]
