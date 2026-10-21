"""Predictor de dirección de la próxima vela.

Combina dos enfoques:
  1. ML: regresión logística (numpy puro) entrenada on-the-fly con ~1000 velas.
  2. Reglas TA: EMA, RSI, MACD, Bollinger, Stochastic, volumen y patrones de velas.

Salida: probabilidad de subida [0..1], confianza %, objetivo (TP) y stop (SL)
basados en ATR, y una lista de razones en español para el usuario.
"""

import numpy as np
import pandas as pd

from . import patterns as P

FEATURES = ["f_trend", "f_ema50", "f_rsi", "f_macd", "f_bb",
            "f_atr", "f_vol", "f_ret3", "f_pat", "f_stoch"]


def build_features(dfi):
    """Construye la matriz de features a partir del df con indicadores."""
    d = dfi.copy()
    d["f_trend"] = (d["ema9"] - d["ema21"]) / d["close"]
    d["f_ema50"] = (d["close"] - d["ema50"]) / d["close"]
    d["f_rsi"] = d["rsi"] / 100 - 0.5
    d["f_macd"] = d["macd_hist"] / d["close"]
    d["f_bb"] = d["bb_pctb"].fillna(0.5) - 0.5
    d["f_atr"] = d["atr_pct"].fillna(0.5) / 100
    d["f_vol"] = d["vol_ratio"].fillna(1) - 1
    d["f_ret3"] = d["ret3"].fillna(0)
    d["f_pat"] = P.pattern_series(d)
    d["f_stoch"] = d["stoch_k"] / 100 - 0.5
    return d


def make_dataset(d):
    """X e y: y = 1 si la vela siguiente cierra por encima de la actual."""
    y = (d["close"].shift(-1) > d["close"]).astype(float)
    X = d[FEATURES].astype(float)
    m = np.isfinite(X.to_numpy()).all(axis=1) & np.isfinite(y.to_numpy())
    return X[m], y[m]


class LogisticModel:
    """Regresión logística con gradiente descendente (numpy puro)."""

    def __init__(self, lr=0.25, epochs=500, l2=1e-3):
        self.lr, self.epochs, self.l2 = lr, epochs, l2

    @staticmethod
    def _sig(z):
        return 1 / (1 + np.exp(-np.clip(z, -30, 30)))

    def fit(self, X, y):
        X = np.asarray(X, float)
        y = np.asarray(y, float)
        self.mu = X.mean(axis=0)
        self.sd = X.std(axis=0)
        self.sd[self.sd == 0] = 1.0
        Z = np.c_[np.ones(len(X)), (X - self.mu) / self.sd]
        self.w = np.zeros(Z.shape[1])
        for _ in range(self.epochs):
            p = self._sig(Z @ self.w)
            g = Z.T @ (p - y) / len(y) + self.l2 * self.w
            g[0] -= self.l2 * self.w[0]  # no regulariza el sesgo
            self.w -= self.lr * g
        return self

    def proba(self, X):
        X = np.asarray(X, float)
        Z = np.c_[np.ones(len(X)), (X - self.mu) / self.sd]
        return self._sig(Z @ self.w)


def rule_score(d):
    """Score de reglas TA en [-1, 1] para la última vela."""
    last = d.iloc[-1]
    s = 0.0
    s += 1.0 if last["ema9"] > last["ema21"] else -1.0
    s += 1.0 if last["close"] > last["ema50"] else -1.0
    r = last["rsi"]
    s += 1.0 if r < 32 else (-1.0 if r > 68 else 0.0)
    s += 0.5 if last["macd_hist"] > 0 else -0.5
    pb = 0.5 if pd.isna(last["bb_pctb"]) else last["bb_pctb"]
    s += -0.5 if pb > 0.95 else (0.5 if pb < 0.05 else 0.0)
    vr = 1.0 if pd.isna(last["vol_ratio"]) else last["vol_ratio"]
    if vr > 1.5:
        s += 0.5 if last["close"] > last["open"] else -0.5
    s += max(-1.0, min(1.0, (last["stoch_k"] - 50) / 30))
    return max(-1.0, min(1.0, s / 5.5))


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


def _reasons(d, pats, prob, modelo):
    last = d.iloc[-1]
    r = []
    e9, e21, e50 = last["ema9"], last["ema21"], last["ema50"]
    sesgo = "alcista" if (e9 > e21 and last["close"] > e50) else \
            ("bajista" if (e9 < e21 and last["close"] < e50) else "mixto")
    r.append(f"Tendencia: EMA9 {'>' if e9 > e21 else '<'} EMA21 y precio "
             f"{'sobre' if last['close'] > e50 else 'bajo'} EMA50 → sesgo **{sesgo}**.")
    rsi_v = last["rsi"]
    if rsi_v >= 70:
        r.append(f"RSI {rsi_v:.0f} (sobrecompra): riesgo de corrección a corto plazo.")
    elif rsi_v <= 30:
        r.append(f"RSI {rsi_v:.0f} (sobreventa): zona de posible rebote.")
    else:
        r.append(f"RSI {rsi_v:.0f}: momentum {'positivo' if rsi_v > 50 else 'débil'}.")
    r.append(f"MACD: histograma {'positivo (impulso comprador)' if last['macd_hist'] > 0 else 'negativo (impulso vendedor)'}.")
    pb = last["bb_pctb"]
    if not pd.isna(pb):
        if pb > 0.9:
            r.append(f"Precio pegado a la banda superior de Bollinger ({pb * 100:.0f}%): extendido al alza.")
        elif pb < 0.1:
            r.append(f"Precio en la banda inferior de Bollinger ({pb * 100:.0f}%): muy castigado.")
    vr = last["vol_ratio"]
    if not pd.isna(vr) and vr > 1.5:
        r.append(f"Volumen {vr:.1f}× el promedio de 20 velas: movimiento con participación real.")
    if pats:
        for p in pats[:3]:
            icono = "🟢" if p["dir"] > 0 else ("🔴" if p["dir"] < 0 else "🟡")
            hace = "ahora" if p["hace"] == 0 else f"hace {p['hace'] + 1} velas"
            r.append(f"Patrón {icono} **{p['nombre']}** ({hace}): {p['desc']}.")
    else:
        r.append("Sin patrones de velas relevantes en las últimas 3 velas.")
    r.append(f"Modelo ({modelo}): **{prob * 100:.0f}% de probabilidad de subida** "
             f"→ {'ALCISTA ▲' if prob >= 0.5 else 'BAJISTA ▼'} en la próxima vela.")
    return r


def predict(dfi, train_frac=0.7):
    """Predicción para la última vela cerrada. Devuelve (pred, df_con_features)."""
    d = build_features(dfi)
    pred = {"prob_ml": None, "prob_reglas": None, "modelo": "Reglas TA"}

    X, y = make_dataset(d.iloc[:-1])
    if len(X) >= 150:
        cut = max(50, int(len(X) * train_frac))
        model = LogisticModel().fit(X.iloc[:cut], y.iloc[:cut])
        if len(X) - cut >= 30:
            pv = model.proba(X.iloc[cut:])
            pred["acc_val"] = float(((pv >= 0.5).astype(float) == y.iloc[cut:]).mean())
        pred["prob_ml"] = float(model.proba(X.iloc[[-1]])[0])

    pats = P.recent_patterns(d, 3)
    ns = P.net_score(pats)
    s_rule = rule_score(d) * 0.75 + max(-0.5, min(0.5, ns * 0.12))
    p_rule = float(_sigmoid(2.0 * s_rule))
    pred["prob_reglas"] = p_rule

    if pred["prob_ml"] is not None and len(X) >= 300:
        pred["prob"] = 0.55 * pred["prob_ml"] + 0.45 * p_rule
        pred["modelo"] = "ML (Regresión Logística) + Reglas TA"
    elif pred["prob_ml"] is not None:
        pred["prob"] = 0.35 * pred["prob_ml"] + 0.65 * p_rule
        pred["modelo"] = "ML + Reglas TA (datos limitados)"
    else:
        pred["prob"] = p_rule
        pred["modelo"] = "Reglas TA"

    prob = pred["prob"]
    pred["dir"] = "ALCISTA" if prob >= 0.5 else "BAJISTA"
    pred["confianza"] = abs(prob - 0.5) * 2 * 100
    pred["patrones"] = pats
    pred["patron_neto"] = ns

    last = d.iloc[-1]
    atrp = last["atr_pct"] / 100
    if prob >= 0.5:
        pred["objetivo"] = float(last["close"] * (1 + 1.5 * atrp))
        pred["stop"] = float(last["close"] * (1 - 1.0 * atrp))
    else:
        pred["objetivo"] = float(last["close"] * (1 - 1.5 * atrp))
        pred["stop"] = float(last["close"] * (1 + 1.0 * atrp))

    pred["razonamiento"] = _reasons(d, pats, prob, pred["modelo"])
    return pred, d
