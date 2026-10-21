"""Cliente REST para Binance: endpoints públicos (datos de mercado) y firmados
(órdenes en Testnet o cuenta real). Solo usa `requests` + hmac, sin dependencias extra."""

import hashlib
import hmac
import time
from urllib.parse import urlencode

import requests

# Hosts públicos de datos de mercado (con failover automático)
PUBLIC_HOSTS = [
    "https://api.binance.com",
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api2.binance.com",
]
TRADE_HOST_TESTNET = "https://testnet.binance.vision"
TRADE_HOST_LIVE = "https://api.binance.com"

_HEADERS = {"User-Agent": "cryptobot-demo/1.0"}


class BinanceError(Exception):
    """Error devuelto por la API de Binance o de red."""


def _get(path, params=None, hosts=None, timeout=10):
    params = params or {}
    hosts = hosts or PUBLIC_HOSTS
    last = None
    for h in hosts:
        try:
            r = requests.get(h + path, params=params, timeout=timeout, headers=_HEADERS)
            if r.status_code == 200:
                return r.json()
            try:
                msg = r.json().get("msg", r.text[:150])
            except Exception:
                msg = r.text[:150]
            last = BinanceError(f"HTTP {r.status_code}: {msg}")
        except requests.RequestException as e:
            last = BinanceError(f"Sin conexión con {h}: {e}")
    raise last or BinanceError("Sin respuesta de Binance")


def ping():
    return _get("/api/v3/ping")


def klines(symbol, interval="15m", limit=500):
    """Devuelve un DataFrame OHLCV con índice temporal UTC."""
    import pandas as pd

    raw = _get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    df = pd.DataFrame(raw, columns=[
        "ot", "open", "high", "low", "close", "volume",
        "ct", "qv", "n", "tb", "tq", "ig",
    ])
    for c in ("open", "high", "low", "close", "volume", "qv"):
        df[c] = df[c].astype(float)
    df["ot"] = pd.to_datetime(df["ot"], unit="ms", utc=True)
    df["ct"] = pd.to_datetime(df["ct"], unit="ms", utc=True)
    return df[["ot", "open", "high", "low", "close", "volume", "qv", "ct"]].set_index("ot")


def tickers_24h():
    """Estadísticas de 24 h para todos los símbolos."""
    return _get("/api/v3/ticker/24hr")


def exchange_info():
    """Filtros por símbolo (lote mínimo, notional mínimo...)."""
    return _get("/api/v3/exchangeInfo")


# ---------------------------------------------------------------- órdenes firmadas

def signed_request(method, path, params, api_key, api_secret, testnet=True):
    """Petición firmada HMAC-SHA256 (Spot Testnet o producción)."""
    host = TRADE_HOST_TESTNET if testnet else TRADE_HOST_LIVE
    params = dict(params or {})
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 10000
    qs = urlencode(params)
    firma = hmac.new(api_secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
    url = f"{host}{path}?{qs}&signature={firma}"
    r = requests.request(method, url, headers={"X-MBX-APIKEY": api_key}, timeout=10)
    if r.status_code != 200:
        raise BinanceError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def account(api_key, api_secret, testnet=True):
    """Balances de la cuenta (verifica que las claves funcionan)."""
    return signed_request("GET", "/api/v3/account", {}, api_key, api_secret, testnet)


def new_order(symbol, side, quantity=None, quote_order_qty=None,
              api_key=None, api_secret=None, testnet=True, type_="MARKET"):
    """Coloca una orden MARKET. side: 'BUY' o 'SELL'."""
    p = {"symbol": symbol, "side": side, "type": type_}
    if quantity is not None:
        p["quantity"] = f"{quantity:.8f}".rstrip("0").rstrip(".")
    if quote_order_qty is not None:
        p["quoteOrderQty"] = f"{quote_order_qty:.8f}".rstrip("0").rstrip(".")
    return signed_request("POST", "/api/v3/order", p, api_key, api_secret, testnet)
