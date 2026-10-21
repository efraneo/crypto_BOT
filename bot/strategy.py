"""Estrategia: convierte la predicción en una decisión operable con plan de trade."""

from . import indicators, market_data, predictor


def analyze(symbol, interval="15m", limit=400, umbral=0.60):
    """Analiza un par y devuelve señal + plan de trade (entrada/TP/SL).

    Señales:
      COMPRA     → prob >= umbral (solo largos, es Spot)
      ESPERAR    → zona neutral
      EVITAR     → sesgo bajista fuerte (prob <= 1-umbral); si tienes la posición,
                   considera salir.
    """
    df = market_data.klines(symbol, interval, limit)
    dfi = indicators.add_all(df)
    pred, dfi = predictor.predict(dfi)
    last = dfi.iloc[-1]
    prob = pred["prob"]

    if prob >= umbral:
        senal = "COMPRA"
    elif prob <= 1 - umbral:
        senal = "EVITAR"
    else:
        senal = "ESPERAR"

    return {
        "symbol": symbol,
        "df": dfi,
        "pred": pred,
        "señal": senal,
        "precio": float(last["close"]),
        "tp": pred["objetivo"],
        "sl": pred["stop"],
        "atr_pct": float(last["atr_pct"]),
        "rsi": float(last["rsi"]),
        "vol_ratio": float(last["vol_ratio"]) if not last["vol_ratio"] != last["vol_ratio"] else 1.0,
        "fuente": market_data.STATE["fuente"],
        "hora_vela": dfi.index[-1],
    }
