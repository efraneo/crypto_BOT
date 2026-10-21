"""Detección de patrones de velas japonesas (alcistas / bajistas / neutrales).

Cada patrón se devuelve como dict:
  nombre  : etiqueta en español
  dir     : +1 alcista, -1 bajista, 0 neutral
  fuerza  : 1 (débil) .. 3 (fuerte)
  hace    : velas hacia atrás (0 = la última vela cerrada)
  peso    : fuerza × decaimiento temporal
"""

import pandas as pd


def _body(o, c):
    return abs(c - o)


def _trend(df, i, look=5):
    """Contexto previo a la vela i: +1 alcista, -1 bajista, 0 lateral."""
    j = max(0, i - look)
    c0 = df["close"].iloc[j]
    c1 = df["close"].iloc[max(0, i - 1)]
    if not c0:
        return 0
    chg = (c1 / c0 - 1) * 100
    if chg > 0.15:
        return 1
    if chg < -0.15:
        return -1
    return 0


def detect_at(df, i):
    """Detecta patrones en la vela i (requiere i >= 2)."""
    o, c = df["open"].iloc[i], df["close"].iloc[i]
    h, l = df["high"].iloc[i], df["low"].iloc[i]
    po, pc = df["open"].iloc[i - 1], df["close"].iloc[i - 1]
    ph, pl = df["high"].iloc[i - 1], df["low"].iloc[i - 1]
    p2o, p2c = df["open"].iloc[i - 2], df["close"].iloc[i - 2]

    body = _body(o, c)
    rng = max(h - l, 1e-12)
    up_sh = h - max(o, c)
    lo_sh = min(o, c) - l
    body_p = _body(po, pc)
    trend = _trend(df, i)
    pats = []

    # Doji — indecisión
    if body <= 0.12 * rng:
        pats.append({"nombre": "Doji", "dir": 0, "fuerza": 1,
                     "desc": "Apertura y cierre casi iguales: indecisión del mercado"})

    # Martillo / Hombre colgado
    if body > 0 and lo_sh >= 2 * body and up_sh <= 0.35 * body:
        if trend <= 0:
            pats.append({"nombre": "Martillo", "dir": 1, "fuerza": 2,
                         "desc": "Mecha inferior larga tras caída: los compradores defendieron el precio"})
        else:
            pats.append({"nombre": "Hombre colgado", "dir": -1, "fuerza": 2,
                         "desc": "Mecha inferior larga tras subida: advertencia de techo"})

    # Estrella fugaz / Martillo invertido
    if body > 0 and up_sh >= 2 * body and lo_sh <= 0.35 * body:
        if trend >= 0:
            pats.append({"nombre": "Estrella fugaz", "dir": -1, "fuerza": 2,
                         "desc": "Mecha superior larga tras subida: rechazo de precios altos"})
        else:
            pats.append({"nombre": "Martillo invertido", "dir": 1, "fuerza": 1,
                         "desc": "Mecha superior larga tras caída: posible rebote"})

    # Envolventes
    if body_p > 0 and pc < po and c > o and c >= po and o <= pc:
        pats.append({"nombre": "Envolvente alcista", "dir": 1, "fuerza": 3,
                     "desc": "Vela verde envuelve por completo a la roja previa: presión compradora"})
    if body_p > 0 and pc > po and c < o and c <= po and o >= pc:
        pats.append({"nombre": "Envolvente bajista", "dir": -1, "fuerza": 3,
                     "desc": "Vela roja envuelve por completo a la verde previa: presión vendedora"})

    # Harami
    if body_p > 0 and pc < po and c > o and c < po and o > pc:
        pats.append({"nombre": "Harami alcista", "dir": 1, "fuerza": 1,
                     "desc": "Vela pequeña dentro de la roja previa: se agota la fuerza vendedora"})
    if body_p > 0 and pc > po and c < o and c > po and o < pc:
        pats.append({"nombre": "Harami bajista", "dir": -1, "fuerza": 1,
                     "desc": "Vela pequeña dentro de la verde previa: se agota la fuerza compradora"})

    # Penetrante / Cubierta oscura
    if pc < po and c > o and o < pl and c > (po + pc) / 2:
        pats.append({"nombre": "Línea penetrante", "dir": 1, "fuerza": 2,
                     "desc": "Cierra sobre el 50% del cuerpo rojo previo"})
    if pc > po and c < o and o > ph and c < (po + pc) / 2:
        pats.append({"nombre": "Cubierta oscura", "dir": -1, "fuerza": 2,
                     "desc": "Cierra bajo el 50% del cuerpo verde previo"})

    # Patrones de 3 velas
    b0, b1 = _body(p2o, p2c), _body(po, pc)
    if p2c < p2o and b0 > 0 and b1 <= 0.5 * b0 and c > o and c > (p2o + p2c) / 2 and pc < p2c:
        pats.append({"nombre": "Estrella de la mañana", "dir": 1, "fuerza": 3,
                     "desc": "3 velas: caída, indecisión y vuelta alcista — giro al alza"})
    if p2c > p2o and b0 > 0 and b1 <= 0.5 * b0 and c < o and c < (p2o + p2c) / 2 and pc > p2c:
        pats.append({"nombre": "Estrella de la tarde", "dir": -1, "fuerza": 3,
                     "desc": "3 velas: subida, indecisión y vuelta bajista — giro a la baja"})
    if c > o and pc > po and p2c > p2o and c > pc > p2c and trend <= 0:
        pats.append({"nombre": "Tres soldados blancos", "dir": 1, "fuerza": 3,
                     "desc": "Tres velas verdes consecutivas ascendentes: fuerza compradora"})
    if c < o and pc < po and p2c < p2o and c < pc < p2c and trend >= 0:
        pats.append({"nombre": "Tres cuervos negros", "dir": -1, "fuerza": 3,
                     "desc": "Tres velas rojas consecutivas descendentes: fuerza vendedora"})

    return pats


def recent_patterns(df, lookback=3):
    """Patrones en las últimas `lookback` velas, con decaimiento de peso."""
    res = []
    n = len(df)
    for age in range(lookback):
        i = n - 1 - age
        if i < 2:
            break
        for p in detect_at(df, i):
            p["hace"] = age
            p["peso"] = round(p["fuerza"] * (0.8 ** age), 2)
            res.append(p)
    return res


def net_score(pats):
    """Score neto: >0 sesgo alcista, <0 sesgo bajista."""
    return sum(p["dir"] * p["peso"] for p in pats)


def pattern_series(df):
    """Suma dirección×fuerza por vela (para features del modelo). Vector para todo el df."""
    import numpy as np

    arr = np.zeros(len(df))
    for i in range(2, len(df)):
        s = 0.0
        for p in detect_at(df, i):
            s += p["dir"] * p["fuerza"]
        arr[i] = s
    # suavizado con decaimiento sobre 3 velas
    w = np.zeros(len(df))
    for k, decay in ((0, 1.0), (1, 0.8), (2, 0.64)):
        if k == 0:
            w += arr
        else:
            w[k:] += decay * arr[:-k]
    return pd.Series(w / 9.0, index=df.index)
