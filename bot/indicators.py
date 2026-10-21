"""Indicadores técnicos calculados con pandas/numpy (sin TA-Lib)."""

import numpy as np
import pandas as pd


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(close, n=14):
    """RSI de Wilder."""
    d = close.diff()
    up = d.clip(lower=0)
    dn = -d.clip(upper=0)
    ru = up.ewm(alpha=1 / n, adjust=False).mean()
    rd = dn.ewm(alpha=1 / n, adjust=False).mean()
    rs = ru / rd.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def macd(close, fast=12, slow=26, sig=9):
    m = ema(close, fast) - ema(close, slow)
    s = m.ewm(span=sig, adjust=False).mean()
    return m, s, m - s


def bollinger(close, n=20, k=2):
    mid = close.rolling(n).mean()
    sd = close.rolling(n).std()
    up = mid + k * sd
    lo = mid - k * sd
    pctb = (close - lo) / (up - lo).replace(0, np.nan)
    return mid, up, lo, pctb


def atr(df, n=14):
    """ATR de Wilder (Average True Range)."""
    pc = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def stochastic(df, n=14, d=3):
    ll = df["low"].rolling(n).min()
    hh = df["high"].rolling(n).max()
    k = 100 * (df["close"] - ll) / (hh - ll).replace(0, np.nan)
    k = k.fillna(50)
    return k, k.rolling(d).mean().fillna(50)


def add_all(df):
    """Añade todas las columnas de indicadores al DataFrame OHLCV."""
    out = df.copy()
    out["ema9"] = ema(out["close"], 9)
    out["ema21"] = ema(out["close"], 21)
    out["ema50"] = ema(out["close"], 50)
    out["rsi"] = rsi(out["close"], 14)
    m, s, h = macd(out["close"])
    out["macd"], out["macd_sig"], out["macd_hist"] = m, s, h
    mid, up, lo, pb = bollinger(out["close"])
    out["bb_mid"], out["bb_up"], out["bb_lo"], out["bb_pctb"] = mid, up, lo, pb
    out["atr"] = atr(out, 14)
    out["atr_pct"] = out["atr"] / out["close"] * 100
    k, d = stochastic(out)
    out["stoch_k"], out["stoch_d"] = k, d
    out["vol_ratio"] = out["volume"] / out["volume"].rolling(20).mean()
    out["ret1"] = out["close"].pct_change()
    out["ret3"] = out["close"].pct_change(3)
    return out
