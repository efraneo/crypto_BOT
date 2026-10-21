"""Backtest long-only con interés compuesto + simulación Monte Carlo.

Reglas anti-trampa:
  * El modelo solo se entrena con el 70 % inicial de las velas.
  * La señal de la vela t ejecuta en la APERTURA de t+1 (sin lookahead).
  * Intrabar: si la vela toca SL y TP, se asume el PEOR caso (SL primero).
  * Comisiones reales de Binance (0.10 % por lado) en cada operación.
"""

import numpy as np
import pandas as pd

from . import indicators, predictor
from .config import INTERVAL_MIN, MAX_HOLD_VELAS


def run(df, capital=10.0, umbral=0.60, tp_mult=1.5, sl_mult=1.0, fee=0.001,
        train_frac=0.7, max_hold=MAX_HOLD_VELAS, interval="15m"):
    minutes = INTERVAL_MIN.get(interval, 15)
    d = predictor.build_features(indicators.add_all(df))
    X, y = predictor.make_dataset(d)
    if len(X) < 200:
        raise ValueError("Datos insuficientes para backtest (mínimo 200 velas útiles).")

    cut = max(100, int(len(X) * train_frac))
    model = predictor.LogisticModel().fit(X.iloc[:cut], y.iloc[:cut])
    pv = model.proba(X.iloc[cut:])
    acc_val = float(((pv >= 0.5).astype(float) == y.iloc[cut:]).mean())

    prob_s = pd.Series(model.proba(X), index=X.index, name="prob")
    d = d.join(prob_s)

    rows = d.loc[X.index[cut]:].reset_index()
    cash, pos = capital, None
    trades, curve = [], []

    for i in range(len(rows)):
        row = rows.iloc[i]
        # 1) gestionar posición abierta
        if pos is not None:
            exit_price = motivo = None
            if row["low"] <= pos["sl"]:
                exit_price, motivo = pos["sl"], "Stop Loss"
            elif row["high"] >= pos["tp"]:
                exit_price, motivo = pos["tp"], "Take Profit"
            elif (not np.isnan(row["prob"]) and row["prob"] <= 0.45
                  and row["close"] < row["ema21"]):
                exit_price, motivo = row["close"], "Señal contraria"
            elif i - pos["i_in"] >= max_hold:
                exit_price, motivo = row["close"], "Tiempo máximo"
            if exit_price is not None:
                cash = pos["qty"] * exit_price * (1 - fee)
                trades.append({
                    "t_in": pos["t_in"], "t_out": row["ot"],
                    "entrada": pos["entry"], "salida": exit_price,
                    "pnl": cash - pos["size"],
                    "pnl_pct": (cash / pos["size"] - 1) * 100,
                    "motivo": motivo, "prob": pos["prob"],
                })
                pos = None
        # 2) nueva entrada (señal de la vela t → compra en apertura de t+1)
        if pos is None and i < len(rows) - 1:
            p = row["prob"]
            if not np.isnan(p) and p >= umbral:
                nxt = rows.iloc[i + 1]
                entry = nxt["open"] * (1 + fee)
                ap = row["atr_pct"] / 100
                pos = {
                    "entry": entry, "qty": cash / entry, "size": cash,
                    "tp": entry * (1 + tp_mult * ap), "sl": entry * (1 - sl_mult * ap),
                    "i_in": i + 1, "prob": float(p), "t_in": nxt["ot"],
                }
        curve.append({"ot": row["ot"],
                      "equity": cash if pos is None else pos["qty"] * row["close"]})

    # cerrar posición abierta al final de la ventana
    if pos is not None:
        last = rows.iloc[-1]
        cash = pos["qty"] * last["close"] * (1 - fee)
        trades.append({"t_in": pos["t_in"], "t_out": last["ot"], "entrada": pos["entry"],
                       "salida": last["close"], "pnl": cash - pos["size"],
                       "pnl_pct": (cash / pos["size"] - 1) * 100,
                       "motivo": "Cierre fin de ventana", "prob": pos["prob"]})
        curve[-1]["equity"] = cash

    eq_arr = np.array([c["equity"] for c in curve])
    peak = np.maximum.accumulate(eq_arr)
    wins = [t for t in trades if t["pnl"] >= 0]
    losses = [t for t in trades if t["pnl"] < 0]
    final = float(eq_arr[-1])

    stats = {
        "capital": capital, "final": final, "pnl": final - capital,
        "pnl_pct": (final / capital - 1) * 100,
        "n_trades": len(trades),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0.0,
        "avg_win_pct": float(np.mean([t["pnl_pct"] for t in wins])) if wins else 0.0,
        "avg_loss_pct": float(np.mean([abs(t["pnl_pct"]) for t in losses])) if losses else 0.0,
        "max_dd_pct": float(((eq_arr / peak) - 1).min() * 100),
        "acc_val": acc_val,
        "horas": len(rows) * minutes / 60,
        "intervalo": interval,
    }
    return {"curve": curve, "trades": trades, "stats": stats}


def monte_carlo(win_rate, avg_win, avg_loss, n_trades, n_sims=3000, capital=10.0, seed=7):
    """Simula miles de días posibles.

    win_rate : probabilidad de acierto (0-1)
    avg_win  : % medio ganado por operación ganadora (neto de comisiones)
    avg_loss : % medio perdido por operación perdedora (neto de comisiones)
    """
    rng = np.random.default_rng(seed)
    hits = rng.random((n_sims, n_trades)) < win_rate
    rets = np.where(hits, avg_win / 100, -avg_loss / 100)
    eq = capital * np.prod(1 + rets, axis=1)
    p5, p25, p50, p75, p95 = np.percentile(eq, [5, 25, 50, 75, 95])
    return {
        "p5": float(p5), "p25": float(p25), "p50": float(p50),
        "p75": float(p75), "p95": float(p95),
        "prob_ganancia": float((eq > capital).mean() * 100),
        "esperado": float(eq.mean()),
        "equities": eq,
    }
