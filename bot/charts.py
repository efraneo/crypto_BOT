"""Gráficos Plotly: velas + flecha de predicción, curva de equity, histograma MC."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

UP, DOWN, GOLD = "#16c784", "#ea3943", "#f0b90b"
INK = "#0e1117"


def candle_fig(df, pred, titulo="", altura=680, ventana=160):
    d = df.tail(ventana)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.78, 0.22], vertical_spacing=0.02)

    fig.add_trace(go.Candlestick(
        x=d.index, open=d["open"], high=d["high"], low=d["low"], close=d["close"],
        name="Velas", increasing_line_color=UP, decreasing_line_color=DOWN,
        increasing_fillcolor=UP, decreasing_fillcolor=DOWN), row=1, col=1)

    for col, nombre, color in (("ema9", "EMA 9", GOLD), ("ema21", "EMA 21", "#7ea6ff"),
                               ("ema50", "EMA 50", "#c884fc")):
        fig.add_trace(go.Scatter(x=d.index, y=d[col], name=nombre,
                                 line=dict(width=1.2, color=color)), row=1, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["bb_up"], name="Bollinger sup",
                             line=dict(width=0.8, color="rgba(126,166,255,.35)"),
                             hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Scatter(x=d.index, y=d["bb_lo"], name="Bollinger inf",
                             line=dict(width=0.8, color="rgba(126,166,255,.35)"),
                             hoverinfo="skip"), row=1, col=1)

    vc = np.where(d["close"] >= d["open"], UP, DOWN)
    fig.add_trace(go.Bar(x=d.index, y=d["volume"], marker_color=vc, opacity=0.5,
                         name="Volumen"), row=2, col=1)

    # marcadores de patrones de velas recientes
    for p in pred.get("patrones", []):
        i = len(df) - 1 - p["hace"]
        if i < 0 or i < len(df) - ventana:
            continue
        row_ = df.iloc[i]
        y = row_["high"] * 1.0015 if p["dir"] >= 0 else row_["low"] * 0.9985
        sym = "triangle-up" if p["dir"] > 0 else ("triangle-down" if p["dir"] < 0 else "circle")
        color = UP if p["dir"] > 0 else (DOWN if p["dir"] < 0 else GOLD)
        fig.add_trace(go.Scatter(
            x=[df.index[i]], y=[y], mode="markers+text",
            marker=dict(symbol=sym, size=13, color=color),
            text=[p["nombre"]], textposition="top center" if p["dir"] >= 0 else "bottom center",
            textfont=dict(size=9, color="#e6e8ec"), showlegend=False, hoverinfo="text",
            hovertext=f"{p['nombre']} ({'alcista' if p['dir']>0 else 'bajista' if p['dir']<0 else 'neutral'})",
        ), row=1, col=1)

    # flecha de predicción + línea punteada al objetivo y al stop
    prob, obj, stp = pred["prob"], pred["objetivo"], pred["stop"]
    last = d.iloc[-1]
    lastx = d.index[-1]
    nx = d.index[-1] + (d.index[-1] - d.index[-2])
    if prob >= 0.5:
        col, ay = UP, 96
        txt = f"▲ SUBIR {prob*100:.0f}% → objetivo {obj:.6g}"
    else:
        col, ay = DOWN, -96
        txt = f"▼ BAJAR {prob*100:.0f}% → objetivo {obj:.6g}"
    fig.add_annotation(x=lastx, y=float(last["close"]), ax=0, ay=ay,
                       xref="x", yref="y", text=txt, showarrow=True, arrowhead=3,
                       arrowsize=1.3, arrowwidth=2.6, arrowcolor=col,
                       font=dict(color=INK, size=11.5), bgcolor=col, borderpad=4,
                       opacity=0.95, standoff=8)
    fig.add_trace(go.Scatter(x=[lastx, nx], y=[float(last["close"]), obj], mode="lines",
                             line=dict(dash="dot", width=2.2, color=col),
                             name="Objetivo", showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=[lastx, nx], y=[float(last["close"]), stp], mode="lines",
                             line=dict(dash="dash", width=1.5, color=GOLD),
                             name="Stop", showlegend=False), row=1, col=1)

    fig.update_layout(
        template="plotly_dark", height=altura, title=titulo,
        margin=dict(l=6, r=6, t=38, b=6),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        paper_bgcolor=INK, plot_bgcolor=INK,
    )
    fig.update_xaxes(tickformat="%d/%m %H:%M", nticks=10)
    fig.update_yaxes(title_text="Precio", row=1, col=1)
    fig.update_yaxes(title_text="Volumen", row=2, col=1)
    return fig


def equity_fig(curve, capital, altura=280, titulo="Curva de equity (capital compuesto)"):
    df = pd.DataFrame(curve)
    final = df["equity"].iloc[-1]
    col = UP if final >= capital else DOWN
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.iloc[:, 0], y=df["equity"], mode="lines",
                             line=dict(color=col, width=2), fill="tozeroy",
                             fillcolor=f"rgba({22 if final>=capital else 234},{196 if final>=capital else 57},{132 if final>=capital else 67},.12)"))
    fig.add_hline(y=capital, line_dash="dot", line_color="#888",
                  annotation_text=f"Capital inicial ${capital:.2f}")
    fig.update_layout(template="plotly_dark", height=altura, title=titulo,
                      margin=dict(l=6, r=6, t=34, b=6), paper_bgcolor=INK, plot_bgcolor=INK)
    fig.update_xaxes(tickformat="%H:%M" if hasattr(df.iloc[0, 0], "hour") else "")
    return fig


def mc_fig(equities, capital, altura=300):
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=equities, nbinsx=44, marker_color="#7ea6ff",
                               opacity=0.85, name="Escenarios"))
    fig.add_vline(x=capital, line_dash="dot", line_color="#e6e8ec",
                  annotation_text=f"$10 inicial")
    fig.add_vline(x=float(np.median(equities)), line_dash="dash", line_color=UP,
                  annotation_text="mediana")
    fig.update_layout(template="plotly_dark", height=altura,
                      title="Distribución de resultados Monte Carlo (equity final)",
                      margin=dict(l=6, r=6, t=34, b=6), paper_bgcolor=INK, plot_bgcolor=INK)
    fig.update_xaxes(title_text="Equity final (USDT)")
    fig.update_yaxes(title_text="Escenarios")
    return fig
