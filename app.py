"""CryptoBot Demo — Binance Spot · Python 3.12 · Streamlit
Ejecutar:  streamlit run app.py
"""

import os
import sys
import warnings

warnings.filterwarnings("ignore")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

from bot import backtest, binance_api, charts, market_data, paper, predictor, strategy
from bot.config import (DEFAULT_INTERVAL, INTERVAL_MIN, MAX_POS, SL_MULT, TP_MULT,
                        UMBRAL)
from bot import screener

TZ = ZoneInfo("America/Bogota")

st.set_page_config(page_title="CryptoBot Demo · Binance", page_icon="📈",
                   layout="wide", initial_sidebar_state="expanded")
ss = st.session_state
ss.setdefault("top5", None)
ss.setdefault("last_scan", None)
ss.setdefault("bot_on", False)
ss.setdefault("cfg", {})


# ------------------------------------------------------------------ cachés
@st.cache_data(ttl=90, show_spinner=False)
def _klines_c(symbol, interval, limit):
    return market_data.klines(symbol, interval, limit)


@st.cache_data(ttl=75, show_spinner=False)
def _analizar(symbol, interval, umbral):
    return strategy.analyze(symbol, interval, 400, umbral)


@st.cache_data(ttl=300, show_spinner=False)
def _tickers_c():
    return market_data.tickers()


@st.cache_data(ttl=300, show_spinner=True)
def _top5_c(interval):
    return screener.top5(_tickers_c(), interval)


def _engine():
    if "engine" not in ss:
        ss.engine = paper.PaperEngine(
            os.path.join(BASE_DIR, "data", "paper_wallet.json"), capital=10.0)
    return ss.engine


def _bog(iso):
    try:
        return datetime.fromisoformat(iso).astimezone(TZ).strftime("%d/%m %H:%M:%S")
    except Exception:
        return str(iso)


# ------------------------------------------------------------------ ciclo del bot
def _ejecutar_ciclo():
    eng = _engine()
    cfg = ss.get("cfg") or {}
    if not cfg.get("symbols"):
        st.toast("Primero escanea el mercado en el Panel", icon="⚠️")
        return

    def _a(s):
        return _analizar(s, cfg["intervalo"], cfg["umbral"])

    try:
        eq, nuevas, cerradas = paper.ciclo(eng, cfg, _a)
        st.toast(f"⚡ Ciclo ejecutado · equity ${eq:.2f} · +{nuevas} apertura(s) · "
                 f"{cerradas} cierre(s)", icon="🤖")
    except Exception as e:
        st.toast(f"Error en el ciclo: {e}", icon="🚨")


def _render_panel():
    eng = _engine()
    cfg = ss.get("cfg") or {}
    intervalo = cfg.get("intervalo", DEFAULT_INTERVAL)
    precios = {}
    for p in eng.w["posiciones"]:
        try:
            precios[p["symbol"]] = float(
                _klines_c(p["symbol"], intervalo, 2)["close"].iloc[-1])
        except Exception:
            precios[p["symbol"]] = p["entrada"]
    eq = eng.equity(precios)
    stt = eng.stats()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("💰 Equity total", f"${eq:,.2f}",
              f"{(eq / eng.w['capital_inicial'] - 1) * 100:+.2f}%")
    m2.metric("🪙 Balance libre", f"${eng.w['balance']:,.2f}")
    m3.metric("📈 PnL acumulado", f"${eq - eng.w['capital_inicial']:+,.4f}")
    m4.metric("🔁 Operaciones cerradas", stt["n"])
    m5.metric("🎯 Win rate", f"{stt['winrate']:.0f}%")

    st.subheader("🔓 Posiciones abiertas")
    if eng.w["posiciones"]:
        filas = []
        for p in eng.w["posiciones"]:
            act = precios.get(p["symbol"], p["entrada"])
            filas.append({
                "Par": p["symbol"], "Entrada": round(p["entrada"], 6),
                "Actual": round(act, 6), "Cantidad": round(p["qty"], 8),
                "Valor $": round(p["qty"] * act, 4),
                "PnL %": round((p["qty"] * act / p["size"] - 1) * 100, 3),
                "TP": round(p["tp"], 6), "SL": round(p["sl"], 6),
                "Abierta": _bog(p["ts"]),
            })
        st.dataframe(pd.DataFrame(filas), width="stretch", hide_index=True)
        st.caption("Cada operación usa el equity completo (interés compuesto). "
                   "El bot cierra automáticamente al tocar TP o SL.")
    else:
        st.caption("Sin posiciones abiertas. El bot abrirá operaciones cuando la "
                   "confianza de la señal supere el umbral configurado.")

    if len(eng.w["equity"]) > 2:
        st.plotly_chart(charts.equity_fig(eng.w["equity"], eng.w["capital_inicial"],
                                          altura=260), width="stretch")

    colh, coll = st.columns([3, 2])
    with colh:
        st.subheader("📜 Historial")
        if eng.w["historial"]:
            h = pd.DataFrame(eng.w["historial"][:25])
            h = h.rename(columns={"symbol": "Par", "entrada": "Entrada", "salida": "Salida",
                                  "pnl": "PnL $", "pnl_pct": "PnL %", "motivo": "Motivo",
                                  "ts": "Hora"})
            h["Hora"] = h["Hora"].map(_bog)
            st.dataframe(h, width="stretch", hide_index=True)
        else:
            st.caption("Aún no hay operaciones cerradas.")
    with coll:
        st.subheader("🧾 Log de decisiones")
        for l in eng.w["log"][:12]:
            st.caption(f"`{_bog(l['ts'])}` — {l['msg']}")


if hasattr(st, "fragment"):
    @st.fragment(run_every="60s")
    def _bot_panel_auto():
        _ejecutar_ciclo()
        _render_panel()
else:  # versiones antiguas de Streamlit
    def _bot_panel_auto():
        _render_panel()


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("📈 CryptoBot Demo")
    st.caption("Binance Spot · Python 3.12 · Streamlit · Paper trading")
    modo = st.radio("Modo de operación",
                    ["🧪 Demo (paper, sin API)", "🛰️ Testnet (API de prueba)",
                     "💰 Real (solo lectura)"], index=0)
    keys_ok, ak, sk, espejar = False, "", "", False
    if modo != "🧪 Demo (paper, sin API)":
        ak = st.text_input("API Key", type="password")
        sk = st.text_input("API Secret", type="password")
        st.caption("🔒 Crea claves SOLO con permiso de lectura (+Spot en testnet), "
                   "**sin retiros** y con whitelist de IP. Nunca compartas el Secret.")
        test = st.button("🔌 Probar conexión")
        if test and ak and sk:
            try:
                acc = binance_api.account(ak, sk, testnet=modo.startswith("🛰️"))
                n = sum(1 for b in acc.get("balances", []) if float(b["free"]) > 0)
                st.success(f"Conexión OK · {n} activos con saldo")
            except Exception as e:
                st.error(f"Fallo de conexión: {e}")
        keys_ok = bool(ak and sk)
        if modo.startswith("💰"):
            st.error("Modo real = solo consulta. Este bot NO opera con dinero real.")
    st.divider()
    intervalo = st.select_slider("Timeframe de análisis", ["5m", "15m", "30m", "1h"],
                                 value=DEFAULT_INTERVAL)
    umbral = st.slider("Confianza mínima para operar", 0.55, 0.80, UMBRAL, 0.01,
                       format="%.2f")
    tp_m = st.slider("Take Profit (× ATR)", 0.8, 3.0, TP_MULT, 0.1)
    sl_m = st.slider("Stop Loss (× ATR)", 0.5, 2.0, SL_MULT, 0.1)
    max_pos = st.slider("Máx. posiciones simultáneas", 1, 5, MAX_POS)
    fraccion = st.slider("% del equity por operación (compuesto)", 0.25, 1.0, 1.0, 0.05,
                         format="%.0f%%")
    auto = st.toggle("Ciclo automático cada 60 s", value=True)
    if modo.startswith("🛰️") and keys_ok:
        espejar = st.checkbox("🛰️ Espejar órdenes demo en Testnet", value=False)
    st.divider()
    st.caption(f"Datos: {market_data.STATE.get('fuente') or '—'} · "
               f"Bogotá: {datetime.now(TZ):%H:%M:%S}")

# configuración para el ciclo (snapshot del estado actual)
if espejar and keys_ok:
    _engine().testnet = {"key": ak, "secret": sk, "on": True}
ss["cfg"] = {
    "symbols": [t["symbol"] for t in (ss.get("top5") or [])][: max_pos + 2]
    or ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    "max_pos": max_pos, "fraccion": fraccion, "umbral": umbral,
    "tp_m": tp_m, "sl_m": sl_m, "espejar": espejar and keys_ok,
    "intervalo": intervalo,
}

if modo.startswith("🧪"):
    st.info("🧪 **MODO DEMO** — 100 % simulado. No se necesitan claves API y no se "
            "envía ninguna orden a Binance. Ideal para aprender y probar.")
elif modo.startswith("🛰️"):
    st.info("🛰️ **MODO TESTNET** — puedes espejar las órdenes del paper trading en el "
            "entorno de pruebas real de Binance con saldo ficticio "
            "(testnet.binance.vision).")
else:
    st.error("💰 **MODO REAL (solo lectura)** — consulta balances y señales con tus "
             "claves, pero el bot NO ejecuta órdenes automáticas con dinero real.")

# ------------------------------------------------------------------ tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏁 Panel Top 5", "🔎 Análisis y Predicción", "🤖 Bot Demo",
    "🧮 Simulador $10 / 24 h", "📚 Aprender"])

# ============================== TAB 1 — PANEL ==============================
with tab1:
    st.markdown("#### 🏆 Top 5 mejores criptos para operar ahora")
    if st.button("🔄 Escanear mercado ahora", type="primary"):
        ss.top5 = _top5_c(intervalo)
        ss.last_scan = datetime.now(TZ)
        st.toast("Escaneo completado", icon="✅")
    if ss.top5 is None:
        with st.spinner("Escaneando mercado (~15 s, luego cache 5 min)…"):
            ss.top5 = _top5_c(intervalo)
            ss.last_scan = datetime.now(TZ)

    try:
        btc = _analizar("BTCUSDT", intervalo, umbral)
        p = btc["pred"]["prob"]
        sent = "🟢 ALCISTA" if p >= 0.55 else ("🔴 BAJISTA" if p <= 0.45 else "🟡 NEUTRAL")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("BTC precio", f"${btc['precio']:,.2f}")
        m2.metric("Sentimiento del mercado (BTC)", sent, f"prob. subida {p * 100:.0f}%")
        m3.metric("BTC RSI(14)", f"{btc['rsi']:.1f}")
        m4.metric("Último escaneo (Bogotá)",
                  ss.last_scan.strftime("%d/%m %H:%M") if ss.last_scan else "—")
    except Exception as e:
        st.warning(f"Sentimiento BTC no disponible: {e}")

    filas = []
    for i, t in enumerate(ss.top5, 1):
        if t["prob"] >= umbral:
            estado = "✔️ COMPRA"
        elif t["prob"] <= 1 - umbral:
            estado = "⛔ EVITAR"
        else:
            estado = "⏳ ESPERAR"
        filas.append({
            "#": i, "Par": t["symbol"], "Precio": f"${t['last']:,.6g}",
            "24h %": f"{t['pct']:+.2f}%", "Vol 24h (M$)": f"{t['qvol'] / 1e6:,.0f}",
            "ATR %": f"{t['atr_pct']:.2f}%", "Estado": estado,
            "Prob subida": round(t["prob"] * 100, 1),
            "Confianza": round(t["conf"], 1),
            "Patrones detectados": t["patron"],
        })
    df5 = pd.DataFrame(filas)
    st.dataframe(
        df5, width="stretch", hide_index=True,
        column_config={
            "Prob subida": st.column_config.ProgressColumn(
                "Prob. de subida", min_value=0, max_value=100, format="%d%%"),
            "Confianza": st.column_config.ProgressColumn(
                "Confianza", min_value=0, max_value=100, format="%d%%"),
        })
    st.caption("El Top 5 combina: **fuerza de la señal** (ML + patrones de velas) 50 % · "
               "**liquidez** 25 % · **volatilidad saludable** 25 %. Descarta pares con "
               "volumen < $20M/24h y tokens apalancados. Confianza ≥ umbral = operable.")

# ============================== TAB 2 — ANÁLISIS ==============================
with tab2:
    st.markdown("#### 🔎 Análisis técnico + predicción con flecha")
    syms = [t["symbol"] for t in (ss.top5 or [])] + \
           ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
    sym = st.selectbox("Par", list(dict.fromkeys(syms)))
    try:
        a = _analizar(sym, intervalo, umbral)
    except Exception as e:
        st.error(f"No se pudo analizar {sym}: {e}")
        a = None
    if a:
        pred = a["pred"]
        st.plotly_chart(
            charts.candle_fig(a["df"], pred,
                              f"{sym} · {intervalo} · predicción para la próxima vela"),
            width="stretch")
        c1, c2, c3, c4, c5 = st.columns(5)
        color_señal = {"COMPRA": "🟢", "EVITAR": "🔴", "ESPERAR": "🟡"}.get(a["señal"], "")
        c1.metric("Señal del bot", f"{color_señal} {a['señal']}")
        c2.metric("Prob. de subida", f"{pred['prob'] * 100:.1f}%")
        c3.metric("Confianza", f"{pred['confianza']:.0f}%")
        c4.metric("Objetivo (TP)", f"{a['tp']:.6g}",
                  f"{(a['tp'] / a['precio'] - 1) * 100:+.2f}%")
        c5.metric("Stop (SL)", f"{a['sl']:.6g}",
                  f"{(a['sl'] / a['precio'] - 1) * 100:+.2f}%")

        colL, colR = st.columns(2)
        with colL:
            st.markdown("##### 🧠 Por qué el bot lo ve así")
            for r in pred["razonamiento"]:
                st.markdown(f"- {r}")
            acc = pred.get("acc_val")
            st.caption(f"Modelo: **{pred['modelo']}** · datos: {market_data.STATE['fuente']}"
                       + (f" · acierto histórico validado: {acc * 100:.0f} %" if acc else ""))
        with colR:
            st.markdown("##### 🕯️ Patrones de velas detectados (últimas 3)")
            if pred["patrones"]:
                for pp in pred["patrones"]:
                    icono = "🟢" if pp["dir"] > 0 else ("🔴" if pp["dir"] < 0 else "🟡")
                    hace = "última vela" if pp["hace"] == 0 else f"hace {pp['hace'] + 1} velas"
                    st.markdown(f"**{icono} {pp['nombre']}** · {hace} · fuerza {pp['fuerza']}/3  \n"
                                f"<small>{pp['desc']}</small>", unsafe_allow_html=True)
            else:
                st.caption("Sin patrones relevantes en las últimas 3 velas.")

        st.markdown("##### 📊 Indicadores actuales")
        last = a["df"].iloc[-1]
        st.dataframe(pd.DataFrame([{
            "RSI(14)": round(last["rsi"], 1),
            "MACD hist": round(last["macd_hist"], 6),
            "EMA 9": round(last["ema9"], 6), "EMA 21": round(last["ema21"], 6),
            "EMA 50": round(last["ema50"], 6),
            "ATR %": f"{last['atr_pct']:.2f}%",
            "Bollinger %B": round(last["bb_pctb"], 2),
            "Stoch %K": round(last["stoch_k"], 1),
            "Vol × prom.": round(last["vol_ratio"], 2) if last["vol_ratio"] == last["vol_ratio"] else 1.0,
        }]), width="stretch", hide_index=True)

# ============================== TAB 3 — BOT DEMO ==============================
with tab3:
    st.markdown("#### 🤖 Bot de paper trading con interés compuesto")
    st.caption("El bot analiza el Top 5, abre operaciones demo cuando la señal supera el "
               "umbral, respeta TP/SL y **reinvierte el resultado** en la siguiente "
               "operación (interés compuesto). Nada de esto usa dinero real.")
    cap_col, b1, b2, b3, b4 = st.columns([1.2, 1, 1, 1, 1.4])
    capital0 = cap_col.number_input("Capital demo (USDT)", 1.0, 10000.0, 10.0, 1.0)
    if b1.button("▶️ Iniciar", type="primary"):
        ss.bot_on = True
    if b2.button("⏸️ Pausar"):
        ss.bot_on = False
    if b3.button("♻️ Reiniciar cartera"):
        _engine().reset(capital0)
        st.toast("Cartera reiniciada", icon="♻️")
    if b4.button("⚡ Ejecutar 1 ciclo ahora"):
        _ejecutar_ciclo()

    if ss.bot_on:
        if auto:
            st.caption("🟢 **Bot activo** — ciclo automático cada 60 s. "
                       "Mantén esta pestaña abierta.")
            _bot_panel_auto()
        else:
            st.caption("🟢 Bot activo (auto apagado). Usa ⚡ para ciclos manuales.")
            _render_panel()
    else:
        st.caption("⏸️ Bot en pausa. Pulsa ▶️ Iniciar para que opere automáticamente.")
        _render_panel()

# ============================== TAB 4 — SIMULADOR ==============================
with tab4:
    st.markdown("### 🧮 ¿Cuánto puede generar **$10 en 24 horas**?")
    st.caption("Backtest con **velas reales** ejecutando la misma estrategia del bot "
               "(ML + patrones, interés compuesto, comisiones 0.10 % por lado, SL "
               "prioritario intrabar) y **Monte Carlo** con 3.000 escenarios posibles.")

    syms_sim = [t["symbol"] for t in (ss.top5 or [])][:3] + \
               ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    c1, c2, c3 = st.columns(3)
    sym_bt = c1.selectbox("Símbolo", list(dict.fromkeys(syms_sim)))
    horas_bt = c2.select_slider("Ventana a simular (horas)", [12, 24, 48, 72], value=24)
    cap_bt = c3.number_input("Capital inicial (USDT)", 1.0, 1000.0, 10.0, 1.0,
                             key="cap_bt")
    if st.button("🧪 Ejecutar backtest con datos reales", type="primary"):
        minutes = INTERVAL_MIN[intervalo]
        limit = min(990, int(horas_bt * 60 / minutes / 0.30) + 60)
        try:
            with st.spinner(f"Simulando {horas_bt} h con velas reales de {sym_bt}…"):
                res = backtest.run(_klines_c(sym_bt, intervalo, limit).copy(),
                                   cap_bt, umbral, tp_m, sl_m, interval=intervalo)
            ss["bt"] = res
        except Exception as e:
            st.error(f"Backtest falló: {e}")

    if "bt" in ss:
        res = ss["bt"]
        s = res["stats"]
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Equity final", f"${s['final']:,.2f}", f"{s['pnl_pct']:+.2f}%")
        m2.metric("Operaciones", s["n_trades"])
        m3.metric("Win rate", f"{s['win_rate']:.0f}%")
        m4.metric("Ganancia media / op.", f"{s['avg_win_pct']:+.2f}%")
        m5.metric("Máx. caída (drawdown)", f"{s['max_dd_pct']:.2f}%")
        st.plotly_chart(charts.equity_fig(res["curve"], cap_bt, altura=300,
                                          titulo=f"Equity simulado {sym_bt} · "
                                                 f"{s['horas']:.0f} h reales · "
                                                 f"modelo acierta {s['acc_val'] * 100:.0f}% "
                                                 f"en validación"),
                        width="stretch")
        if res["trades"]:
            tdf = pd.DataFrame(res["trades"])
            tdf = tdf[["t_in", "entrada", "salida", "pnl", "pnl_pct", "motivo", "prob"]]
            tdf.columns = ["Entrada", "Precio entrada", "Precio salida", "PnL $",
                           "PnL %", "Motivo salida", "Prob señal"]
            tdf["Entrada"] = pd.to_datetime(tdf["Entrada"]).dt.tz_convert(TZ).dt.strftime("%d/%m %H:%M")
            st.dataframe(tdf, width="stretch", hide_index=True)
        if s["pnl"] >= 0:
            st.info(f"✅ En esta ventana la estrategia **habría ganado ${s['pnl']:.4f}** "
                    f"({s['pnl_pct']:+.2f} %) con {s['n_trades']} operaciones. "
                    f"Recuerda: una ventana buena NO garantiza la próxima — pruébalo en "
                    f"varios símbolos y ventanas antes de concluir nada.")
        else:
            st.warning(f"🔻 En esta ventana la estrategia **habría perdido "
                       f"${abs(s['pnl']):.4f}** ({s['pnl_pct']:+.2f} %). Esto es normal: "
                       f"ningún bot gana siempre. Sube el umbral de confianza o cambia "
                       f"el timeframe y vuelve a probar.")

    st.divider()
    st.markdown("### 🎲 Monte Carlo — 3.000 futuros posibles")
    prev = ss.get("bt", {}).get("stats", {})
    c1, c2, c3, c4 = st.columns(4)
    wr = c1.slider("Win rate asumido (%)", 30, 70, int(prev.get("win_rate") or 50), 1)
    aw = c2.slider("Ganancia media por acierto (%)", 0.2, 3.0,
                   round(prev.get("avg_win_pct") or 0.7, 1), 0.1)
    al = c3.slider("Pérdida media por fallo (%)", 0.2, 3.0,
                   round(prev.get("avg_loss_pct") or 0.6, 1), 0.1)
    nt = c4.slider("Operaciones en 24 h", 2, 16, max(2, int(prev.get("n_trades") or 8)), 1)
    if st.button("🎲 Simular 3.000 días posibles"):
        ss["mc"] = backtest.monte_carlo(wr / 100, aw, al, nt, 3000, cap_bt)
    if "mc" in ss:
        mc = ss["mc"]
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Peor 5 %", f"${mc['p5']:,.2f}")
        m2.metric("Escenario malo", f"${mc['p25']:,.2f}")
        m3.metric("Mediana", f"${mc['p50']:,.2f}")
        m4.metric("Escenario bueno", f"${mc['p75']:,.2f}")
        m5.metric("Mejor 5 %", f"${mc['p95']:,.2f}")
        m6.metric("Prob. de terminar ganando", f"{mc['prob_ganancia']:.0f}%")
        st.plotly_chart(charts.mc_fig(mc["equities"], cap_bt), width="stretch")
        st.markdown(
            f"**Lectura honesta:** con un win rate de **{wr} %**, ganancia media "
            f"**+{aw} %** y pérdida media **−{al} %** por operación (netos de "
            f"comisiones), tras **{nt} operaciones** en 24 h con interés compuesto: "
            f"la mitad de los días terminan por debajo de **${mc['p50']:.2f}** y solo "
            f"el {mc['prob_ganancia']:.0f} % de los días termina ganando. El interés "
            f"compuesto amplifica lo bueno **y también lo malo**.")

    st.divider()
    st.markdown("### 📉 La realidad en números (léelo antes de invertir)")
    e1, e2 = st.columns(2)
    with e1:
        st.markdown("""
**Comisiones y mínimos de Binance Spot**
- Comisión: **0.10 % por lado** → 0.20 % ida y vuelta (0.075 % con BNB).
- Notional mínimo: **~$5–10 por orden** → con $10 cabe una sola operación.
- Con $10, cada operación paga ~$0.02 de comisiones: un 0.2 % de tu capital.
- El *spread* (diferencia compra/venta) también se come una fracción de cada trade.
""")
        st.markdown("""
**Punto de equilibrio (breakeven)**

Con TP = +1.5×ATR y SL = −1×ATR y comisión 0.2 % por operación completa,
con un ATR típico de 0.5 % en velas de 15 m:
- Ganancia neta por acierto ≈ **+0.55 %**  ·  Pérdida neta por fallo ≈ **−0.70 %**
- Win rate mínimo para no perder ≈ **0.70 / (0.55 + 0.70) ≈ 56 %**

Por eso el umbral por defecto del bot es 60 %: por debajo de ~56 % de aciertos,
**las comisiones solas te hacen perder dinero** aunque aciertes la mitad.
""")
    with e2:
        st.markdown("""
**Lo que dicen los estudios (no lo digo yo)**
- **72 %** de los day traders termina el año con pérdidas (FINRA).
- Solo **1–3 %** de los day traders es rentable de forma consistente (Barber & Odean; Bookmap).
- **80 %** abandona el day trading en los primeros 2 años (Brazil/Taiwan studies).
- Los traders activos rinden **6.5 % anual peor** que el índice en promedio.
""")
        tasas = [0.5, 1.0, 2.0, 3.0, 5.0]
        comp = pd.DataFrame({
            "Ganancia diaria": [f"{t} %/día" for t in tasas],
            "Tras 7 días": [f"${10 * (1 + t / 100) ** 7:,.2f}" for t in tasas],
            "Tras 30 días": [f"${10 * (1 + t / 100) ** 30:,.2f}" for t in tasas],
            "¿Realista?": ["✅ posible", "⚠️ muy bueno", "⚠️ excepcional",
                           "🚨 raro", "🚨 casi imposible sostener"],
        })
        st.markdown("**El interés compuesto sobre $10**")
        st.dataframe(comp, width="stretch", hide_index=True)
        st.caption("Referencias: tradeciety.com, quantifiedstrategies.com, bookmap.com "
                   "(estudios de Barber & Odean y FINRA).")

# ============================== TAB 5 — APRENDER ==============================
with tab5:
    st.markdown("### 📚 Recursos para aprender trading algorítmico")
    st.caption("Selección basada en investigación web (octubre 2026): frameworks "
               "open-source, libros clásicos y modelos que usan los bots profesionales.")

    colA, colB = st.columns(2)
    with colA:
        st.markdown("##### 💻 Bots open-source en GitHub")
        st.markdown("""
| Repositorio | Qué aprenderás |
|---|---|
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) ⭐55k | El bot Python más completo: backtesting, hyperopt y **FreqAI** (ML adaptativo). |
| [freqtrade/freqtrade-strategies](https://github.com/freqtrade/freqtrade-strategies) | Cientos de estrategias reales listas para estudiar. |
| [hummingbot/hummingbot](https://github.com/hummingbot/hummingbot) ⭐20k | Market making y arbitraje institucional. |
| [jesse-ai/jesse](https://github.com/jesse-ai/jesse) ⭐8k | Framework limpio para investigar estrategias con 300+ indicadores. |
| [Drakkar-Software/OctoBot](https://github.com/Drakkar-Software/OctoBot) | Bot modular con web UI y estrategias IA/DCA/GRID. |
| [enigmampc/catalyst](https://github.com/enigmampc/catalyst) · [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL) ⭐12k | Reinforcement Learning aplicado a trading. |
| [ccxt/ccxt](https://github.com/ccxt/ccxt) | La librería estándar para hablar con 100+ exchanges. |
| [python-binance](https://github.com/python-binance/python-binance) | Cliente Python oficial-comunitario de Binance. |
""")
        st.markdown("##### 🤖 Modelos que usan los bots")
        st.markdown("""
- **Momentum / tendencia**: operar a favor de EMA/MACD (lo que hace este bot).
- **Reversión a la media**: RSI/Bollinger extremos → rebotes.
- **Grid y DCA**: órdenes escalonadas sin predicción (Passivbot).
- **Market making**: comprar bid / vender ask capturando el spread (Hummingbot).
- **ML supervisado**: regresión logística, gradient boosting, LSTM (FreqAI).
- **Reinforcement Learning**: agentes que aprenden política de trading (FinRL).
""")
    with colB:
        st.markdown("##### 📚 Libros recomendados")
        st.markdown("""
1. **Steve Nison — *Japanese Candlestick Charting Techniques*** → la biblia de las velas japonesas.
2. **John J. Murphy — *Technical Analysis of the Financial Markets*** → todas las bases del análisis técnico.
3. **Thomas Bulkowski — *Encyclopedia of Chart Patterns*** → estadísticas reales de cada patrón.
4. **Ernest Chan — *Algorithmic Trading: Winning Strategies and Their Rationale*** → cómo construir y validar bots.
5. **Marcos López de Prado — *Advances in Financial Machine Learning*** → ML financiero serio (evita el overfitting).
6. **Mark Douglas — *The Disciplined Trader*** → psicología: el 90 % del juego.
""")
        st.markdown("##### 🛰️ Cómo probar con la API de Binance (gratis)")
        st.markdown("""
1. Entra en **testnet.binance.vision** con tu cuenta de GitHub.
2. Genera una clave **HMAC_SHA256** (saldo ficticio incluido).
3. Pega la clave en la barra lateral → modo **🛰️ Testnet**.
4. Activa *Espejar órdenes* y el bot enviará tus operaciones demo al testnet real.

Cuando pases a real: claves con **solo lectura**, luego solo Spot sin retiros,
**whitelist de IP** y montos que puedas perder. Nunca compartas tu Secret.
""")
        st.markdown("##### 🧭 Ruta sugerida")
        st.markdown("""
1. **Semana 1-2**: juega con este bot en Demo; entiende cada indicador (pestaña Análisis).
2. **Semana 3-4**: lee Nison y Murphy; identifica patrones a mano y compara con el bot.
3. **Mes 2**: estudia `freqtrade-strategies`, corre backtests largos, aprende de tus métricas.
4. **Mes 3+**: testnet con claves → y solo entonces, dinero que puedas perder.
""")

st.divider()
st.caption("⚠️ **Aviso:** esto es una herramienta educativa de paper trading, no asesoría "
           "financiera. Las criptomonedas son extremadamente volátiles y puedes perder "
           "todo tu capital. El rendimiento pasado no garantiza rendimientos futuros. "
           "Datos: Binance (respaldo OKX/Coinbase) · Zona horaria: America/Bogota.")
