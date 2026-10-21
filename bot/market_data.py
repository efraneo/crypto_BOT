"""Datos de mercado con failover: Binance → OKX → Coinbase → sintético.

Si ninguna API externa responde, genera velas sintéticas deterministas para que
la interfaz siga funcionando (marcadas claramente como demostración).
"""

import hashlib

import numpy as np
import pandas as pd

from . import binance_api as B
from .config import LISTA_POPULAR

STATE = {"fuente": None}
_INTERVAL_OKX = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "1H"}
_INTERVAL_CB = {"5m": 300, "15m": 900, "30m": 1800, "1h": 3600}
_INTERVAL_TD = {"5m": 5, "15m": 15, "30m": 30, "1h": 60}


def _to_df(rows):
    """rows: lista de [ms, open, high, low, close, volume] (más antiguo primero)."""
    df = pd.DataFrame(rows, columns=["ot", "open", "high", "low", "close", "volume"])
    df["ot"] = pd.to_datetime(df["ot"], unit="ms", utc=True)
    df["qv"] = df["volume"] * df["close"]
    td = pd.Timedelta(minutes=_INTERVAL_TD.get("15m", 15))
    df["ct"] = df["ot"] + td
    return df.set_index("ot")


def _okx_klines(symbol, interval, limit):
    import requests

    inst = symbol.replace("USDT", "-USDT")
    r = requests.get("https://www.okx.com/api/v5/market/candles",
                     params={"instId": inst, "bar": _INTERVAL_OKX.get(interval, "15m"),
                             "limit": min(limit, 300)}, timeout=10)
    j = r.json()
    if j.get("code") != "0":
        raise RuntimeError(j.get("msg", "error OKX"))
    rows = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])]
            for x in j["data"]][::-1]
    return _to_df(rows)


def _cb_klines(symbol, interval, limit):
    import requests

    prod = symbol.replace("USDT", "-USD")
    r = requests.get(f"https://api.exchange.coinbase.com/products/{prod}/candles",
                     params={"granularity": _INTERVAL_CB.get(interval, 900)}, timeout=10)
    r.raise_for_status()
    raw = r.json()[: min(limit, 300)][::-1]  # [time, low, high, open, close, volume]
    rows = [[int(x[0]) * 1000, float(x[3]), float(x[2]), float(x[1]), float(x[4]), float(x[5])]
            for x in raw]
    return _to_df(rows)


def synthetic_klines(symbol, interval="15m", limit=500):
    """Random-walk determinista por símbolo (solo para demo sin conexión)."""
    minutes = _INTERVAL_TD.get(interval, 15)
    seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    base = 20 + seed % 500
    rets = rng.normal(0.0002, 0.004, limit)
    close = base * np.cumprod(1 + rets)
    open_ = np.r_[close[0] * (1 - rets[0]), close[:-1]]
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.0015, limit)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.0015, limit)))
    vol = np.abs(rng.normal(1500, 400, limit))
    df = pd.DataFrame({"open": open_, "high": high, "low": low,
                       "close": close, "volume": vol})
    idx = pd.date_range(end=pd.Timestamp.utcnow().floor("1min"),
                        periods=limit, freq=f"{minutes}min", tz="UTC")
    df.index = idx
    df.index.name = "ot"
    df["qv"] = df["volume"] * df["close"]
    df["ct"] = df.index + pd.Timedelta(minutes=minutes)
    return df[["open", "high", "low", "close", "volume", "qv", "ct"]]


def klines(symbol, interval="15m", limit=500):
    """Klines OHLCV con failover multi-fuente."""
    try:
        df = B.klines(symbol, interval, limit)
        STATE["fuente"] = "Binance"
        return df
    except Exception:
        pass
    try:
        df = _okx_klines(symbol, interval, limit)
        STATE["fuente"] = "OKX (respaldo)"
        return df
    except Exception:
        pass
    try:
        df = _cb_klines(symbol, interval, limit)
        STATE["fuente"] = "Coinbase (respaldo)"
        return df
    except Exception:
        pass
    STATE["fuente"] = "⚠️ Sintético (sin conexión)"
    return synthetic_klines(symbol, interval, limit)


def _norm_binance_tickers():
    out = []
    for t in B.tickers_24h():
        out.append({
            "symbol": t["symbol"], "last": float(t["lastPrice"]),
            "pct": float(t["priceChangePercent"]), "qvol": float(t["quoteVolume"]),
            "high": float(t["highPrice"]), "low": float(t["lowPrice"]),
        })
    return out


def _norm_okx_tickers():
    import requests

    r = requests.get("https://www.okx.com/api/v5/market/tickers",
                     params={"instType": "SPOT"}, timeout=10)
    j = r.json()
    if j.get("code") != "0":
        raise RuntimeError("error OKX tickers")
    out = []
    for t in j["data"]:
        if not t["instId"].endswith("-USDT"):
            continue
        last, open24 = float(t["last"]), float(t["open24h"])
        out.append({
            "symbol": t["instId"].replace("-", ""), "last": last,
            "pct": (last / open24 - 1) * 100 if open24 else 0.0,
            "qvol": float(t["volCcy24h"]) * last,
            "high": float(t["high24h"]), "low": float(t["low24h"]),
        })
    return out


def _synthetic_tickers():
    rng = np.random.default_rng(42)
    out = []
    for s in LISTA_POPULAR:
        seed = int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)
        r = np.random.default_rng(seed)
        last = 20 + seed % 500
        pct = float(r.normal(1.5, 5))
        out.append({"symbol": s, "last": last, "pct": pct,
                    "qvol": float(r.uniform(30e6, 2e9)),
                    "high": last * 1.05, "low": last * 0.94})
    return out


def tickers():
    """Estadísticas 24h de todos los pares, con failover."""
    try:
        out = _norm_binance_tickers()
        STATE["fuente"] = "Binance"
        return out
    except Exception:
        pass
    try:
        out = _norm_okx_tickers()
        STATE["fuente"] = "OKX (respaldo)"
        return out
    except Exception:
        pass
    STATE["fuente"] = "⚠️ Sintético (sin conexión)"
    return _synthetic_tickers()
