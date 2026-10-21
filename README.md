# 📈 CryptoBot Demo — Binance Spot · Python 3.12 · Streamlit

Bot de trading educativo con **paper trading (dinero ficticio)**, predictor de velas
con **flecha en el gráfico**, screener del **Top 5 de criptos**, y simulador de
**$10 en 24 horas con interés compuesto**.

> ⚠️ Herramienta educativa. No es asesoría financiera. Las criptos son volátiles:
> puedes perder todo tu capital.

---

## ✨ Funcionalidades

| Pestaña | Qué hace |
|---|---|
| 🏁 **Panel Top 5** | Escanea ~400 pares USDT, filtra por liquidez (> $20M/24h) y rankea los 5 mejores por señal + liquidez + volatilidad saludable. |
| 🔎 **Análisis y Predicción** | Gráfico de velas + EMAs + Bollinger + volumen, **flecha verde/roja con la predicción**, patrones de velas detectados (14 patrones: martillo, envolventes, estrella de la mañana, tres soldados...) y explicación en español de cada decisión. |
| 🤖 **Bot Demo** | Paper trading con interés compuesto: analiza el Top 5 cada 60 s, abre/cierra posiciones respetando TP/SL con la vela real y **reinvierte el resultado** en la siguiente operación. Opcional: espeja órdenes en Binance **Testnet**. |
| 🧮 **Simulador $10 / 24 h** | Backtest con velas reales (sin lookahead, SL prioritario, comisiones 0.10 %/lado) + **Monte Carlo con 3.000 escenarios** + la matemática honesta de comisiones y mínimos. |
| 📚 **Aprender** | Bots open-source de GitHub (freqtrade, hummingbot, jesse...), libros, modelos de bot y ruta de aprendizaje. |

## 🚀 Instalación y ejecución

Requiere **Python 3.12** (funciona con 3.10+).

```bash
cd crypto-bot
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Se abre en `http://localhost:8501`.

## 🧠 Cómo decide el bot

1. **Datos**: velas OHLCV de Binance (respaldo OKX → Coinbase → sintético).
2. **Indicadores**: EMA 9/21/50, RSI(14), MACD, Bandas de Bollinger, ATR, Estocástico, volumen relativo.
3. **Patrones de velas**: 14 patrones alcistas/bajistas/neutrales con fuerza y decaimiento temporal.
4. **Predictor (ensemble)**:
   - ML: regresión logística entrenada on-the-fly con las últimas ~1.000 velas (70 % train / 30 % validación).
   - Reglas TA: combinación ponderada de indicadores + patrón neto.
   - Probabilidad final = 0.55·ML + 0.45·Reglas → flecha ▲/▼, objetivo = ±1.5×ATR, stop = ∓1×ATR.
5. **Estrategia**: COMPRA si prob ≥ 0.60 · ESPERAR en zona neutral · EVITAR si sesgo bajista fuerte (Spot = solo largos).

## 🛰️ Modos

| Modo | Qué hace | Claves API |
|---|---|---|
| 🧪 **Demo** (default) | Todo simulado en tu máquina | No necesita |
| 🛰️ **Testnet** | Espeja las órdenes demo en `testnet.binance.vision` (saldo ficticio real de Binance) | Claves de testnet (GitHub login) |
| 💰 **Real** | **Solo lectura**: consulta balances y señales. El bot NO opera automático con dinero real por seguridad | Claves reales con permiso de lectura |

**Seguridad de claves**: crea claves con permisos mínimos, **nunca actives retiros**,
usa whitelist de IP y nunca compartas el Secret. Las claves se usan solo en tu
sesión local (no se guardan en disco).

## 📂 Estructura

```
crypto-bot/
├── app.py                  # Interfaz Streamlit (5 pestañas)
├── bot/
│   ├── binance_api.py      # REST pública + firmada (HMAC-SHA256)
│   ├── market_data.py      # Klines/tickers con failover multi-exchange
│   ├── indicators.py       # EMA, RSI, MACD, Bollinger, ATR, Estocástico
│   ├── patterns.py         # 14 patrones de velas japonesas
│   ├── predictor.py        # Regresión logística (numpy) + reglas TA
│   ├── screener.py         # Screener Top 5
│   ├── strategy.py         # Señal + plan de trade (entrada/TP/SL)
│   ├── paper.py            # Motor demo con interés compuesto
│   ├── backtest.py         # Backtest anti-trampa + Monte Carlo
│   ├── charts.py           # Velas + flecha de predicción (Plotly)
│   └── config.py           # Parámetros (comisión, TP/SL, umbral...)
├── data/paper_wallet.json  # Cartera demo (persistente)
└── .streamlit/config.toml  # Tema oscuro
```

## 🧮 La respuesta honesta a "¿cuánto genera $10 en 24 h?"

- Comisión 0.10 %/lado = **0.20 % por operación completa**; notional mínimo ~$5.
- Punto de equilibrio: con TP 1.5×ATR y SL 1×ATR necesitas **~56 % de aciertos** solo para no perder.
- Escenario típico del backtest: **entre −5 % y +5 % al día** (−$0.50 a +$0.50 con $10).
- Un día excepcional: +2 a +5 % ($10.20–$10.50). Nadie sostiene +5 %/día: +5 %/día en 30 días = $43, en 365 días = **$1.6 millones — no existe**.
- Estudios (FINRA, Barber & Odean): 72 % de day traders pierde; solo 1–3 % es consistente.
- **El valor de este bot es aprender el ciclo completo gratis (demo) antes de arriesgar un solo dólar.**

## 📚 Aprende más

Repos: [freqtrade](https://github.com/freqtrade/freqtrade) (+[FreqAI](https://www.freqtrade.io/en/stable/freqai/) y [freqtrade-strategies](https://github.com/freqtrade/freqtrade-strategies)), [hummingbot](https://github.com/hummingbot/hummingbot), [jesse](https://github.com/jesse-ai/jesse), [OctoBot](https://github.com/Drakkar-Software/OctoBot), [FinRL](https://github.com/AI4Finance-Foundation/FinRL), [ccxt](https://github.com/ccxt/ccxt).

Libros: Nison (*Velas japonesas*), Murphy (*Análisis técnico*), Bulkowski (*Patrones*), Chan (*Algorithmic Trading*), López de Prado (*ML financiero*), Douglas (*Psicología*).
