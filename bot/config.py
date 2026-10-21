"""Configuración global del bot."""

# --- Comisiones y capital ---
FEE = 0.001          # 0.10 % por lado en Binance Spot (0.075 % pagando con BNB)
DEFAULT_CAPITAL = 10.0
MIN_NOTIONAL_DEFAULT = 5.0   # mínimo por orden en la mayoría de pares USDT

# --- Estrategia por defecto ---
DEFAULT_INTERVAL = "15m"
TP_MULT = 1.5        # Take Profit = 1.5 × ATR
SL_MULT = 1.0        # Stop Loss   = 1.0 × ATR
UMBRAL = 0.60        # probabilidad mínima para abrir posición
MAX_POS = 3
MAX_HOLD_VELAS = 16  # salida por tiempo (16 velas de 15m = 4 h)

QUOTE = "USDT"
TZ_NAME = "America/Bogota"
INTERVALS = ["5m", "15m", "30m", "1h"]
INTERVAL_MIN = {"5m": 5, "15m": 15, "30m": 30, "1h": 60}

# Pares estables / no deseados para el screener
STABLES = {
    "USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "BUSDUSDT", "DAIUSDT", "EURUSDT",
    "USDPUSDT", "AEURUSDT", "XUSDUSDT", "USD1USDT", "EURUSDT", "GBPUSDT",
    "TRYUSDT", "BRLUSDT", "ARSUSDT", "JPYUSDT", "USDTUSDT",
}

LISTA_POPULAR = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "TONUSDT", "TRXUSDT", "DOTUSDT",
    "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT", "PEPEUSDT",
    "SHIBUSDT", "LTCUSDT", "ATOMUSDT", "FILUSDT", "INJUSDT", "SEIUSDT",
    "TIAUSDT", "RUNEUSDT", "AAVEUSDT", "UNIUSDT", "RENDERUSDT", "WIFUSDT",
]
