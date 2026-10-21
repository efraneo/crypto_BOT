"""Motor de paper trading (demo) con interés compuesto.

Simula compras/ventas Spot con capital ficticio:
  * Cada operación arriesga una fracción del equity (por defecto 100 % = compuesto).
  * Al cerrar, el resultado (ganancia o pérdida) queda dentro del balance y la
    siguiente operación se dimensiona sobre el nuevo total → interés compuesto.
  * TP/SL se revisan con la vela real (high/low), SL prioritario (conservador).
  * Opcional: espeja las órdenes en Binance Spot **Testnet** con claves del usuario.
"""

import json
import os
from datetime import datetime, timezone

from . import binance_api as B


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PaperEngine:

    def __init__(self, path, capital=10.0, fee=0.001):
        self.path = path
        self.fee = fee
        self.testnet = None  # {"key":..., "secret":..., "on": bool}
        self.w = self._load() or self._fresh(capital)

    @staticmethod
    def _fresh(capital):
        return {"balance": capital, "capital_inicial": capital, "posiciones": [],
                "historial": [], "equity": [], "log": []}

    def _load(self):
        try:
            with open(self.path) as f:
                return json.load(f)
        except Exception:
            return None

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.w, f, indent=2, default=str)

    def reset(self, capital):
        self.w = self._fresh(capital)
        self.log(f"♻️ Cartera reiniciada con ${capital:.2f}")
        self.save()

    def log(self, msg):
        self.w["log"].insert(0, {"ts": _now(), "msg": msg})
        self.w["log"] = self.w["log"][:200]

    # ------------------------------------------------------------- operaciones

    def abrir(self, symbol, precio, tp, sl, fraccion=1.0, espejar=False):
        size = self.w["balance"] * fraccion
        if size < 5.0:
            self.log(f"⚠️ {symbol}: ${size:.2f} es menor al mínimo de Binance (~$5). No se abre.")
            self.save()
            return False
        if len(self.w["posiciones"]) >= 8:
            self.log(f"⚠️ Máximo de posiciones alcanzado. {symbol} descartado.")
            self.save()
            return False
        qty = size / precio * (1 - self.fee)
        self.w["balance"] -= size
        self.w["posiciones"].append({
            "symbol": symbol, "entrada": precio, "qty": qty, "tp": tp, "sl": sl,
            "size": size, "ts": _now(),
        })
        self.log(f"🟢 COMPRA demo {symbol}: ${size:.2f} @ {precio:.6g} · "
                 f"TP {tp:.6g} · SL {sl:.6g}")
        if espejar and self.testnet and self.testnet.get("on"):
            try:
                B.new_order(symbol, "BUY", quote_order_qty=size,
                            api_key=self.testnet["key"], api_secret=self.testnet["secret"],
                            testnet=True)
                self.log(f"🛰️ Orden espejo BUY {symbol} enviada al Testnet.")
            except Exception as e:
                self.log(f"⚠️ Testnet BUY {symbol} falló: {e}")
        self.save()
        return True

    def cerrar(self, pos, precio, motivo):
        neto = pos["qty"] * precio * (1 - self.fee)
        pnl = neto - pos["size"]
        pnl_pct = pnl / pos["size"] * 100
        self.w["balance"] += neto
        self.w["posiciones"].remove(pos)
        self.w["historial"].insert(0, {
            "symbol": pos["symbol"], "entrada": pos["entrada"], "salida": precio,
            "pnl": round(pnl, 6), "pnl_pct": round(pnl_pct, 4), "motivo": motivo,
            "ts": _now(),
        })
        self.w["historial"] = self.w["historial"][:300]
        icono = "✅" if pnl >= 0 else "🔻"
        self.log(f"{icono} VENTA demo {pos['symbol']} @ {precio:.6g} · "
                 f"PnL ${pnl:+.4f} ({pnl_pct:+.2f}%) · {motivo}")
        if espejar_habilitada(self) and self.testnet.get("on"):
            try:
                B.new_order(pos["symbol"], "SELL", quantity=pos["qty"],
                            api_key=self.testnet["key"], api_secret=self.testnet["secret"],
                            testnet=True)
                self.log(f"🛰️ Orden espejo SELL {pos['symbol']} enviada al Testnet.")
            except Exception as e:
                self.log(f"⚠️ Testnet SELL {pos['symbol']} falló: {e}")
        self.save()
        return pnl

    def revisar(self, velas):
        """Revisa TP/SL de posiciones abiertas con la última vela (SL prioritario)."""
        for pos in list(self.w["posiciones"]):
            df = velas.get(pos["symbol"])
            if df is None or len(df) == 0:
                continue
            hi = float(df["high"].iloc[-1])
            lo = float(df["low"].iloc[-1])
            if lo <= pos["sl"]:
                self.cerrar(pos, pos["sl"], "Stop Loss")
            elif hi >= pos["tp"]:
                self.cerrar(pos, pos["tp"], "Take Profit")

    # ------------------------------------------------------------- métricas

    def equity(self, precios):
        eq = self.w["balance"]
        for p in self.w["posiciones"]:
            pr = precios.get(p["symbol"], p["entrada"])
            eq += p["qty"] * pr
        return eq

    def registrar_equity(self, eq):
        self.w["equity"].append([_now(), round(eq, 6)])
        self.w["equity"] = self.w["equity"][-1500:]
        self.save()

    def stats(self):
        h = self.w["historial"]
        wins = sum(1 for x in h if x["pnl"] >= 0)
        pnl_total = sum(x["pnl"] for x in h)
        return {"n": len(h), "winrate": (wins / len(h) * 100) if h else 0.0,
                "pnl_total": pnl_total}


def espejar_habilitada(engine):
    return bool(getattr(engine, "testnet", None) and engine.testnet.get("on"))


def ciclo(engine, cfg, analisis):
    """Un ciclo del bot: revisa salidas, abre entradas y registra equity.

    cfg: {symbols, max_pos, fraccion, umbral, tp_m, sl_m, espejar}
    analisis: función symbol -> dict de strategy.analyze (idealmente cacheada).
    Devuelve (equity, n_abiertas, n_cerradas).
    """
    abiertas_antes = len(engine.w["posiciones"])
    necesarios = set(cfg["symbols"]) | {p["symbol"] for p in engine.w["posiciones"]}
    A = {}
    for s in necesarios:
        try:
            A[s] = analisis(s)
        except Exception:
            continue

    # 1) salidas TP/SL con la vela más reciente
    velas = {s: a["df"] for s, a in A.items()
             if s in {p["symbol"] for p in engine.w["posiciones"]}}
    engine.revisar(velas)

    # 2) entradas nuevas (solo COMPRA, Spot = long only)
    cerradas = abiertas_antes - len(engine.w["posiciones"])
    nuevas = 0
    if len(engine.w["posiciones"]) < cfg["max_pos"]:
        cands = []
        for s in cfg["symbols"]:
            if any(p["symbol"] == s for p in engine.w["posiciones"]):
                continue
            a = A.get(s)
            if not a or a["señal"] != "COMPRA":
                continue
            cands.append(a)
        cands.sort(key=lambda a: a["pred"]["confianza"], reverse=True)
        for a in cands[: cfg["max_pos"] - len(engine.w["posiciones"])]:
            atrp = a["atr_pct"] / 100
            tp = a["precio"] * (1 + cfg["tp_m"] * atrp)
            sl = a["precio"] * (1 - cfg["sl_m"] * atrp)
            if engine.abrir(a["symbol"], a["precio"], tp, sl,
                            cfg["fraccion"], cfg.get("espejar", False)):
                nuevas += 1

    # 3) equity
    precios = {s: a["precio"] for s, a in A.items()}
    eq = engine.equity(precios)
    engine.registrar_equity(eq)
    return eq, nuevas, cerradas
