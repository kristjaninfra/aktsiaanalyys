"""Aktsiaanalüüs – Streamliti rakendus. Käivita: ./start.command"""
from __future__ import annotations

import datetime as dt
import html
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
from plotly.subplots import make_subplots

import analysis as A

try:
    from streamlit_searchbox import st_searchbox
except ImportError:  # varulahendus: tavaline tekstikast
    st_searchbox = None

st.set_page_config(page_title="Aktsiaanalüüs", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")
st.markdown(f"<style>{(Path(__file__).parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

# Värvid (valideeritud kategooriline palett) + staatusvärvid
BLUE, ORANGE, AQUA, VIOLET, YELLOW = "#3b82f6", "#f97316", "#10b981", "#8b5cf6", "#f59e0b"
UP, DOWN, NEUTRAL = "#10b981", "#f43f5e", "#94a3b8"
SIG_TONE = {"OST": "up", "KERGE OST": "up", "HOIA": "flat", "KERGE MÜÜK": "down", "MÜÜ": "down"}
TONE_COLOR = {"up": "#059669", "down": "#e11d48", "flat": "#64748b"}
TONE_TINT = {"up": "#ecfdf5", "down": "#fff1f3", "flat": "#f5f8fd"}
SIGNAL_ICON = {"OST": "▲▲", "KERGE OST": "▲", "HOIA": "■", "KERGE MÜÜK": "▼", "MÜÜ": "▼▼"}

# Ühtne graafikute stiil
pio.templates["moodne"] = go.layout.Template(layout=dict(
    font=dict(family="Inter, -apple-system, Segoe UI, sans-serif", size=12, color="#475569"),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(showgrid=False, linecolor="#e5e9f2", zeroline=False, ticks=""),
    yaxis=dict(gridcolor="#eef2f7", zeroline=False, ticks="", linecolor="rgba(0,0,0,0)"),
    hoverlabel=dict(bgcolor="white", bordercolor="#e5e9f2", font=dict(color="#0f172a", family="Inter, sans-serif")),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=12)),
    colorway=[BLUE, ORANGE, AQUA, YELLOW, VIOLET],
))
pio.templates.default = "plotly_white+moodne"


def show(fig):
    st.plotly_chart(fig, use_container_width=True, theme=None, config={"displayModeBar": False})


# Päeva ideede skaneeritav valim: USA suurettevõtted eri sektoritest
UNIVERSE = ("AAPL MSFT NVDA GOOGL AMZN META TSLA AVGO ORCL ADBE CRM AMD INTC QCOM CSCO NFLX "
            "JPM BAC GS V MA UNH LLY JNJ PFE MRK ABBV XOM CVX PG KO PEP COST WMT HD MCD NKE DIS BA CAT T VZ").split()
QUICK = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "TSLA", "META", "LHV1T.TL"]


@st.cache_data(ttl=3600, show_spinner=False)
def _search(q: str):
    return A.search(q)


def search_cached(q: str):
    return _search(q.strip().lower()) if q and q.strip() else []


@st.cache_data(ttl=900, show_spinner=False)
def get_data(ticker: str):
    return A.fetch(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def get_bench():
    try:
        return A.fetch_benchmark()
    except Exception:
        return None


def run(ticker: str):
    data = get_data(ticker)
    res = A.analyze(data, get_bench())
    return data, res


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def daily_ideas(day: str, n: int = 3):
    """Skaneerib valimi ja tagastab parimad. `day` teeb vahemälu päevapõhiseks."""
    bench = get_bench()

    def one(tk):
        try:
            data = A.fetch(tk)
            res = A.analyze(data, bench)
            v12, v26 = res["views"]["12 nädalat"], res["views"]["26 nädalat"]
            info = data["info"]
            facs = sorted(res["factors"], key=lambda f: f[2], reverse=True)
            soon = data["earnings_date"] is not None and 0 <= (data["earnings_date"] - pd.Timestamp.today().normalize()).days <= 7
            return {
                "ticker": tk, "name": info.get("shortName") or tk, "sector": info.get("sector") or "",
                "price": res["price"], "score": (v12["score"] + v26["score"]) / 2,
                "v12": v12, "v26": v26, "groups": res["groups"],
                "pros": [f[3] for f in facs if f[2] > 0.05][:3],
                "con": next((f[3] for f in facs[::-1] if f[2] < -0.05), None),
                "upside": (info["targetMeanPrice"] / res["price"] - 1) if info.get("targetMeanPrice") else None,
                "earnings_soon": soon,
            }
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = [r for r in ex.map(one, UNIVERSE) if r]
    rows.sort(key=lambda r: r["score"], reverse=True)
    # Hajutus: maksimaalselt üks idee sektori kohta
    picks, seen = [], set()
    for r in rows:
        if r["sector"] in seen:
            continue
        picks.append(r)
        seen.add(r["sector"])
        if len(picks) == n:
            break
    return picks, len(rows)


# ---------------------------------------------------------------- vormindus

def esc(x):
    return html.escape(str(x))


def money(x, cur="USD"):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    sym = "$" if cur == "USD" else ("€" if cur == "EUR" else "")
    return f"{sym}{x:,.2f}".replace(",", " ")


def big(x):
    if not x:
        return "–"
    for div, s in ((1e12, " tr"), (1e9, " mld"), (1e6, " mln")):
        if abs(x) >= div:
            return f"{x / div:.2f}{s}"
    return f"{x:,.0f}"


def pct(x, sign=True):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    return f"{x * 100:+.1f}%" if sign else f"{x * 100:.1f}%"


def tone(x):
    return "up" if x > 0.0005 else "down" if x < -0.0005 else "flat"


def sig_pill(signal):
    return f"<span class='pill {SIG_TONE[signal]}'>{SIGNAL_ICON[signal]} {signal}</span>"


def sig_card(label, v, price, cur):
    t = SIG_TONE[v["signal"]]
    accent = TONE_COLOR[t]
    s = v["score"] * 100
    dot = max(2, min(98, 50 + s / 2))
    span = v["high"] - v["low"]
    now = max(0, min(100, (price - v["low"]) / span * 100)) if span else 50
    mid = max(0, min(100, (v["mid"] - v["low"]) / span * 100)) if span else 50
    er = v["exp_ret"]
    return f"""
<div class="card sig" style="--accent:{accent};--tint:{TONE_TINT[t]}">
  <div class="top"><span class="h">{esc(label)}</span><span class="conf">kindlus: {esc(v['confidence'])}</span></div>
  <div class="label">{SIGNAL_ICON[v['signal']]} {v['signal']}</div>
  <div class="meter"><div class="dot" style="left:{dot:.1f}%"></div></div>
  <div class="meter-l"><span>Müü −100</span><b>skoor {s:+.0f}</b><span>+100 Ost</span></div>
  <div class="stats">
    <div class="stat"><div class="k">Tõusu tõenäosus</div><div class="v">{v['p_up'] * 100:.0f}%</div></div>
    <div class="stat"><div class="k">Oodatav hind</div><div class="v">{money(v['mid'], cur)}<small style="color:{TONE_COLOR[tone(er)]}">{pct(er)}</small></div></div>
  </div>
  <div class="rng"><div class="k">80% tõenäosusega vahemik · ▏praegu ● oodatav</div>
    <div class="rbar"><div class="mid" style="left:{mid:.1f}%"></div><div class="now" style="left:{now:.1f}%"></div></div>
    <div class="rl"><span>{money(v['low'], cur)}</span><span>{money(v['high'], cur)}</span></div>
  </div>
</div>"""


def factor_rows(items, positive):
    color = UP if positive else DOWN
    out = []
    for grp, _nm, s, txt in items:
        w = min(100, abs(s) * 100)
        out.append(f"""<div class="frow"><div><div class="ft">{esc(txt)}</div><div class="fg">{esc(A.GROUP_NAMES[grp])}</div></div>
<div class="fb"><div style="width:{w:.0f}%;background:{color}"></div></div>
<div class="fs" style="color:{TONE_COLOR['up' if positive else 'down']}">{s * 100:+.0f}</div></div>""")
    return "".join(out) or "<div class='fg'>Puuduvad</div>"


# ---------------------------------------------------------------- otsing ja kiirvalikud

if "ticker" not in st.session_state:
    st.session_state.ticker = "AAPL"


def _quick_pick():
    v = st.session_state.get("quick")
    if v:
        st.session_state.ticker = v
    st.session_state.quick = None


def _open(tk):
    st.session_state.ticker = tk


st.markdown("""<div class="brand"><div class="logo">↗</div><div class="t">Aktsiaanalüüs</div>
<div class="s">hinnang 4–26 nädalaks</div></div>""", unsafe_allow_html=True)

search_col, _sp = st.columns([2, 1])
with search_col:
    if st_searchbox is not None:
        picked = st_searchbox(
            search_cached,
            label=None,
            placeholder="🔎  Kirjuta nimi või ticker – nt apple, nvidia, lhv",
            key="aktsia_otsing",
            debounce=300,
        )
        if picked and picked != st.session_state.get("last_search"):
            st.session_state.last_search = picked
            st.session_state.ticker = picked
    else:
        typed = st.text_input("Otsi aktsiat", placeholder="Ticker, nt AAPL")
        if typed and typed.strip().upper() != st.session_state.get("last_search"):
            st.session_state.last_search = typed.strip().upper()
            st.session_state.ticker = typed.strip().upper()
st.pills("Kiirvalik", QUICK, key="quick", on_change=_quick_pick, label_visibility="collapsed")

ticker = st.session_state.ticker.strip().upper()

try:
    with st.spinner(f"Laen {ticker} andmeid…"):
        data, res = run(ticker)
except Exception as e:
    st.error(f"Andmete laadimine ebaõnnestus: {e}")
    st.stop()

info = data["info"]
cur = info.get("currency", "USD")
price = res["price"]
chg = price / res["prev"] - 1
tgt = info.get("targetMeanPrice")

# ---------------------------------------------------------------- päis

name = info.get("longName") or info.get("shortName") or ticker
sub = " · ".join(esc(x) for x in [info.get("exchange") and (info.get("fullExchangeName") or info.get("exchange")),
                                  info.get("sector"), info.get("industry")] if x)
initials = "".join(w[0] for w in name.replace(",", "").split()[:2]).upper() or ticker[:2]
hi, lo = res["d"]["high_52w"].iloc[-1], res["d"]["low_52w"].iloc[-1]
pos52 = (price - lo) / (hi - lo) * 100 if hi > lo else 50
vol = res["sigma_d"] * math.sqrt(252)
vol_txt = "rahulik" if vol < 0.2 else "tavaline" if vol < 0.35 else "kõikuv" if vol < 0.55 else "väga kõikuv"
ed = data.get("earnings_date")
ed_days = (ed - pd.Timestamp.today().normalize()).days if ed is not None else None

st.markdown(f"""
<div class="card hero-card" style="margin-top:14px">
 <div class="hero">
  <div class="hero-left"><div class="avatar">{esc(initials)}</div>
   <div><div class="name">{esc(name)}</div>
   <div class="sub"><span class="chip">{esc(ticker)}</span>{sub}</div></div></div>
  <div class="hero-right"><div class="price">{money(price, cur)}</div>
   <span class="pill {tone(chg)}">{'▲' if chg >= 0 else '▼'} {pct(chg)} viimane päev</span></div>
 </div>
</div>
<div class="kpis">
 <div class="kpi"><div class="k">52 nädala vahemik</div><div class="v">{lo:,.0f} – {hi:,.0f}</div>
   <div class="mini"><div class="fill" style="width:{pos52:.0f}%"></div><div class="mk" style="left:{pos52:.0f}%"></div></div>
   <div class="d" style="margin-top:8px">{pct(price / hi - 1)} tipust</div></div>
 <div class="kpi"><div class="k">Analüütikute siht</div><div class="v">{money(tgt, cur)}</div>
   <div class="d">{f"<span class='pill {tone(tgt / price - 1)}'>{pct(tgt / price - 1)}</span> 12 kuu peale" if tgt else "andmed puuduvad"}</div></div>
 <div class="kpi"><div class="k">Volatiilsus</div><div class="v">{vol * 100:.0f}%</div><div class="d">aastas · {vol_txt}</div></div>
 <div class="kpi"><div class="k">Turuväärtus</div><div class="v">{big(info.get('marketCap'))}</div>
   <div class="d">{f"tulemused {ed:%d.%m.%Y} ({ed_days} p pärast)" if ed_days is not None and ed_days >= 0 else "&nbsp;"}</div></div>
</div>
""", unsafe_allow_html=True)

for w in res["warnings"]:
    st.markdown(f"<div class='note'>⚠️ <div>{esc(w)}</div></div>", unsafe_allow_html=True)

# Kokkuvõte ühe pilguga, lihtsas keeles
facs = sorted(res["factors"], key=lambda f: f[2], reverse=True)
pos = [f for f in facs if f[2] > 0.05][:5]
neg = [f for f in facs[::-1] if f[2] < -0.05][:5]


def plain_summary(res, info, price):
    """Lühike seletus tavakeeles: mis on peamised põhjused."""
    g = res["groups"]
    out = []
    tl, fu = g.get("tech_long"), g.get("fund")
    if tl is not None and tl <= -0.4:
        out.append("Aktsia on viimastel kuudel palju tõusnud ja on oma tavatasemest kõrgel. "
                   "Ajalooliselt on sellisele tõusule sageli järgnenud jahtumine.")
    elif tl is not None and tl >= 0.4:
        out.append("Aktsia on viimastel kuudel palju langenud ja on oma tavatasemest madalal. "
                   "Ajalooliselt on sellisele langusele sageli järgnenud taastumine.")
    if fu is not None and fu >= 0.3:
        out.append("Ettevõtte numbrid (kasv ja kasumlikkus) on tugevad.")
    elif fu is not None and fu <= -0.15:
        out.append("Ettevõtte numbrid on nõrgad: hind on kõrge või kasumlikkus kehv.")
    t = info.get("targetMeanPrice")
    if t:
        u = t / price - 1
        if u >= 0.15:
            out.append(f"Analüütikud näevad 12 kuuga tõusuruumi {u * 100:.0f}%.")
        elif u < 0:
            out.append("Hind on juba analüütikute keskmisest hinnasihist kõrgemal.")
    if res["views"]["12 nädalat"]["confidence"] == "madal":
        out.append("Signaalid on omavahel vastuolus, seega on kindlus madal.")
    return " ".join(out) or "Selgeid tugevaid signaale ei ole – pilt on neutraalne."


main = res["views"]["12 nädalat"]
vt = SIG_TONE[main["signal"]]
pills = "".join(f"<span style='color:var(--ink2);font-size:13px;margin-left:6px'>{esc(l)}</span>{sig_pill(v['signal'])}"
                for l, v in res["views"].items())
st.markdown(f"""<div class="verdict" style="--vc:{TONE_COLOR[vt]}">
<div class="head">Järgmise 3 kuu vaade: <span>{SIGNAL_ICON[main['signal']]} {main['signal']}</span></div>
<div class="plain">{esc(plain_summary(res, info, price))}</div>
<div class="row">{pills}</div></div>""", unsafe_allow_html=True)

tabs = st.tabs(["📊 Ülevaade", "💡 Päeva ideed", "📈 Graafik", "🏢 Ettevõte", "⚖️ Võrdlus", "📘 Õpetus"])
T_OVER, T_IDEAS, T_CHART, T_FUND, T_CMP, T_HELP = tabs
T_ANAL = T_FUND  # analüütikud samal vahelehel ettevõtte numbritega

# ---------------------------------------------------------------- Ülevaade

with T_OVER:
    st.markdown("<div class='sigs'>" + "".join(sig_card(l, v, price, cur) for l, v in res["views"].items()) + "</div>",
                unsafe_allow_html=True)
    st.write("")

    left, right = st.columns([1, 1.5], gap="medium")
    with left:
        rows = []
        for k, v in res["groups"].items():
            if v is None:
                continue
            s = v * 100
            w = abs(s) / 2
            l = 50 if s >= 0 else 50 - w
            col = BLUE if s >= 0 else ORANGE
            rows.append(f"""<div class="grp"><div>{esc(A.GROUP_NAMES[k])}</div>
<div class="gtrack"><div class="gbar" style="left:{l:.1f}%;width:{w:.1f}%;background:{col}"></div></div>
<div class="gval">{s:+.0f}</div></div>""")
        st.markdown(f"""<div class="card" style="height:100%"><div class="ct">Grupiskoorid<span class="hint">−100 … +100</span></div>
{''.join(rows)}
<div class="fg" style="margin-top:12px">Lühike vaade kaalub rohkem tehnilist osa, pikk vaade fundamentaali ja analüütikuid.</div></div>""",
                    unsafe_allow_html=True)

    with right:
        with st.container(border=True):
            st.markdown("<div class='ct'>Hinnaprognoos<span class='hint'>viimane aasta + 26 nädalat ette</span></div>",
                        unsafe_allow_html=True)
            d = res["d"].tail(252)
            fig = go.Figure()
            last_date = d.index[-1]
            L = A.LONGEST
            fut = pd.bdate_range(last_date, periods=L + 1)
            sd = res["sigma_d"]
            t = np.arange(L + 1)
            kx = [0] + [v["days"] for v in res["views"].values()]
            ky = [0.0] + [math.log(v["mid"] / price) for v in res["views"].values()]
            mu_t = np.interp(t, kx, ky)  # oodatav tee läbib iga horisondi punkti
            mid = price * np.exp(mu_t)
            up = price * np.exp(mu_t + A.Z80 * sd * np.sqrt(t))
            dn = price * np.exp(mu_t - A.Z80 * sd * np.sqrt(t))
            fig.add_trace(go.Scatter(x=d.index, y=d["Close"], name="Hind", line=dict(color=BLUE, width=2),
                                     fill="tozeroy", fillcolor="rgba(59,130,246,0.08)",
                                     hovertemplate="%{x|%d.%m.%Y}: %{y:.2f}<extra></extra>"))
            fig.add_trace(go.Scatter(x=list(fut) + list(fut[::-1]), y=list(up) + list(dn[::-1]), fill="toself",
                                     fillcolor="rgba(139,92,246,0.14)", line=dict(width=0), name="80% vahemik", hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=fut, y=mid, name="Oodatav", line=dict(color=VIOLET, width=2, dash="dot"),
                                     hovertemplate="%{x|%d.%m.%Y}: %{y:.2f}<extra></extra>"))
            for label, v in res["views"].items():
                x = fut[min(v["days"], L)]
                fig.add_trace(go.Scatter(x=[x], y=[v["mid"]], mode="markers+text",
                                         marker=dict(size=10, color=VIOLET, line=dict(color="white", width=2)),
                                         text=[f"{v['days'] // 5} näd"], textposition="top center", showlegend=False,
                                         hovertemplate=f"{label}: %{{y:.2f}} ({v['low']:.2f}–{v['high']:.2f})<extra></extra>"))
            if tgt:
                fig.add_hline(y=tgt, line=dict(color="#94a3b8", dash="dash", width=1.2),
                              annotation_text=f"Analüütikute siht {tgt:.0f}", annotation_position="top left",
                              annotation_font_color="#64748b")
            ymin = min(d["Close"].min(), dn.min()) * 0.97
            ymax = max(d["Close"].max(), up.max(), tgt or 0) * 1.02
            fig.update_layout(height=300, margin=dict(l=0, r=0, t=6, b=0), hovermode="x unified",
                              legend=dict(orientation="h", y=-0.12), yaxis=dict(range=[ymin, ymax]))
            show(fig)

    st.write("")
    a, b = st.columns(2, gap="medium")
    with a:
        st.markdown(f"<div class='card'><div class='ct'>✅ Räägib poolt</div>{factor_rows(pos, True)}</div>",
                    unsafe_allow_html=True)
    with b:
        st.markdown(f"<div class='card'><div class='ct'>⚠️ Räägib vastu</div>{factor_rows(neg, False)}</div>",
                    unsafe_allow_html=True)
    st.caption("NB: tugev tõus keskmistest kaugele loetakse siin ettevaatusmärgiks (keskmisele naasmine). "
               "Miks – vt 📘 Õpetus.")
    T_BT = st.expander("🧪 Kas mudel on selle aktsiaga varem töötanud?")

# ---------------------------------------------------------------- Graafik

with T_CHART:
    per = st.segmented_control("Periood", ["3 kuud", "6 kuud", "1 aasta", "2 aastat", "5 aastat"], default="1 aasta",
                               label_visibility="collapsed") or "1 aasta"
    n = {"3 kuud": 63, "6 kuud": 126, "1 aasta": 252, "2 aastat": 504, "5 aastat": 1300}[per]
    adv = st.toggle("Näita tehnilisi näitajaid (maht, RSI, MACD)", value=False)
    d = res["d"].tail(n)
    rows_n = 4 if adv else 1
    fig = make_subplots(rows=rows_n, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                        row_heights=[0.55, 0.13, 0.16, 0.16] if adv else [1],
                        subplot_titles=("Hind", "Maht", "RSI (14)", "MACD") if adv else None)
    fig.add_trace(go.Scatter(x=d.index, y=d["BB_up"], line=dict(width=0), showlegend=False, hoverinfo="skip"), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["BB_dn"], line=dict(width=0), fill="tonexty", fillcolor="rgba(139,92,246,0.08)",
                             name="Bollinger", hoverinfo="skip"), 1, 1)
    fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"], name="Hind",
                                 increasing_line_color=UP, decreasing_line_color=DOWN), 1, 1)
    for col, color in (("SMA20", YELLOW), ("SMA50", ORANGE), ("SMA200", VIOLET)):
        fig.add_trace(go.Scatter(x=d.index, y=d[col], name=col, line=dict(color=color, width=1.5)), 1, 1)
    if adv:
      fig.add_trace(go.Bar(x=d.index, y=d["Volume"], name="Maht", showlegend=False,
                         marker_color=np.where(d["Close"] >= d["Open"], UP, DOWN)), 2, 1)
      fig.add_trace(go.Scatter(x=d.index, y=d["RSI"], name="RSI", line=dict(color=BLUE, width=1.5), showlegend=False), 3, 1)
      for lvl in (30, 70):
          fig.add_hline(y=lvl, line=dict(color=NEUTRAL, dash="dot", width=1), row=3, col=1)
      fig.add_trace(go.Bar(x=d.index, y=d["MACD_hist"], name="MACD hist", showlegend=False,
                           marker_color=np.where(d["MACD_hist"] >= 0, UP, DOWN)), 4, 1)
      fig.add_trace(go.Scatter(x=d.index, y=d["MACD"], name="MACD", line=dict(color=BLUE, width=1.5), showlegend=False), 4, 1)
      fig.add_trace(go.Scatter(x=d.index, y=d["MACD_signal"], name="Signaal", line=dict(color=ORANGE, width=1.5), showlegend=False), 4, 1)
    fig.update_layout(height=820 if adv else 520, xaxis_rangeslider_visible=False, hovermode="x unified",
                      margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", y=1.04))
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    show(fig)

    last = res["d"].iloc[-1]
    st.markdown(
        f"RSI **{last['RSI']:.0f}** · MACD hist **{last['MACD_hist']:+.2f}** · "
        f"hind vs SMA50 **{pct(last['Close'] / last['SMA50'] - 1)}** · vs SMA200 **{pct(last['Close'] / last['SMA200'] - 1)}** · "
        f"ATR **{last['ATR']:.2f}** ({pct(last['ATR'] / last['Close'], sign=False)} päevas)"
    )

# ---------------------------------------------------------------- Fundamentaal

with T_FUND:
    st.markdown("<div class='ct' style='font-size:18px'>🏢 Ettevõtte numbrid</div>", unsafe_allow_html=True)
    rows = [
        ("Turuväärtus", big(info.get("marketCap"))),
        ("P/E (viimased 12 kuud)", f"{info['trailingPE']:.1f}" if info.get("trailingPE") else "–"),
        ("Forward P/E", f"{info['forwardPE']:.1f}" if info.get("forwardPE") else "–"),
        ("PEG", f"{(info.get('trailingPegRatio') or info.get('pegRatio')):.2f}" if (info.get("trailingPegRatio") or info.get("pegRatio")) else "–"),
        ("P/B", f"{info['priceToBook']:.1f}" if info.get("priceToBook") else "–"),
        ("EV/EBITDA", f"{info['enterpriseToEbitda']:.1f}" if info.get("enterpriseToEbitda") else "–"),
        ("Käibe kasv a/a", pct(info.get("revenueGrowth"))),
        ("Kasumi kasv a/a", pct(info.get("earningsGrowth"))),
        ("Brutomarginaal", pct(info.get("grossMargins"), False)),
        ("Puhasmarginaal", pct(info.get("profitMargins"), False)),
        ("ROE", pct(info.get("returnOnEquity"), False)),
        ("Võlg / omakapital", f"{info['debtToEquity']:.0f}%" if info.get("debtToEquity") is not None else "–"),
        ("Vaba rahavoog", big(info.get("freeCashflow"))),
        ("Dividenditootlus", f"{info['dividendYield']:.2f}%" if info.get("dividendYield") else "–"),
        ("Beeta", f"{info['beta']:.2f}" if info.get("beta") else "–"),
        ("Lühikeseks müüdud (float)", pct(info.get("shortPercentOfFloat"), False)),
        ("Siseringi osalus", pct(info.get("heldPercentInsiders"), False)),
        ("Institutsioonide osalus", pct(info.get("heldPercentInstitutions"), False)),
    ]
    a, b = st.columns([1, 1])
    with a:
        st.markdown("**Põhinäitajad**")
        st.dataframe(pd.DataFrame(rows, columns=["Näitaja", "Väärtus"]), hide_index=True, use_container_width=True, height=670)
    with b:
        st.markdown("**Skoor näitajate kaupa**")
        if res["fund"]:
            df = pd.DataFrame([(n, t, s * 100) for n, s, t in res["fund"]], columns=["Näitaja", "Selgitus", "Skoor"])
            st.dataframe(df, hide_index=True, use_container_width=True,
                         column_config={"Skoor": st.column_config.ProgressColumn(min_value=-100, max_value=100, format="%+.0f")})
            st.metric("Fundamentaalne koondskoor", f"{res['groups']['fund'] * 100:+.0f}")
        else:
            st.info("Fundamentaalandmeid pole.")
        if info.get("longBusinessSummary"):
            with st.expander("Ettevõtte kirjeldus (inglise k)"):
                st.write(info["longBusinessSummary"])

# ---------------------------------------------------------------- Analüütikud

with T_ANAL:
    st.write("")
    st.markdown("<div class='ct' style='font-size:18px'>🎯 Analüütikud ja uudised</div>", unsafe_allow_html=True)
    a, b = st.columns(2)
    with a:
        st.markdown("**Hinnasihid vs praegune hind**")
        lo_t, mean_t, hi_t = info.get("targetLowPrice"), info.get("targetMeanPrice"), info.get("targetHighPrice")
        if mean_t:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[lo_t, hi_t], y=["Siht", "Siht"], mode="lines", line=dict(color=NEUTRAL, width=6), hoverinfo="skip", showlegend=False))
            pts = [("Madalaim", lo_t, ORANGE), ("Keskmine", mean_t, BLUE), ("Kõrgeim", hi_t, AQUA)]
            for lbl, val, colr in pts:
                fig.add_trace(go.Scatter(x=[val], y=["Siht"], mode="markers+text", marker=dict(size=14, color=colr),
                                         text=[f"{lbl}<br>{val:.0f}"], textposition="top center", name=lbl,
                                         hovertemplate=f"{lbl}: {val:.2f} ({pct(val / price - 1)})<extra></extra>"))
            fig.add_vline(x=price, line=dict(color=VIOLET, width=2, dash="dash"), annotation_text=f"Praegu {price:.0f}")
            fig.update_layout(height=220, showlegend=False, margin=dict(l=0, r=0, t=40, b=10), yaxis=dict(visible=False))
            show(fig)
            st.caption(f"{info.get('numberOfAnalystOpinions', '?')} analüütikut · konsensus {info.get('recommendationMean', 0):.2f}/5 "
                       f"(1 = tugev ost, 5 = müü) · siht on 12 kuu peale")
        else:
            st.info("Hinnasihte pole.")
    with b:
        st.markdown("**Soovituste jaotus (viimased kuud)**")
        r = data["recs"]
        if not r.empty and "period" in r:
            r = r.iloc[::-1]
            lbl = {"0m": "See kuu", "-1m": "−1 kuu", "-2m": "−2 kuud", "-3m": "−3 kuud"}
            fig = go.Figure()
            for col, nm, colr in (("strongBuy", "Tugev ost", "#008300"), ("buy", "Ost", AQUA), ("hold", "Hoia", NEUTRAL),
                                  ("sell", "Müü", ORANGE), ("strongSell", "Tugev müük", DOWN)):
                fig.add_trace(go.Bar(x=[lbl.get(p, p) for p in r["period"]], y=r[col], name=nm, marker_color=colr,
                                     marker_line=dict(width=2, color="rgba(0,0,0,0)")))
            fig.update_layout(barmode="stack", height=260, margin=dict(l=0, r=0, t=10, b=10), legend=dict(orientation="h", y=-0.2))
            show(fig)
        else:
            st.info("Soovituste ajalugu pole.")

    st.markdown("**Viimased reitingumuutused**")
    ud = data["updown"]
    if not ud.empty:
        ud = ud.head(15).reset_index()
        ud = ud.rename(columns={"GradeDate": "Kuupäev", "Firm": "Firma", "ToGrade": "Reiting", "FromGrade": "Eelmine",
                                "Action": "Tegevus", "priceTargetAction": "Siht", "currentPriceTarget": "Uus siht", "priorPriceTarget": "Eelmine siht"})
        ud["Kuupäev"] = pd.to_datetime(ud["Kuupäev"]).dt.strftime("%d.%m.%Y")
        ud["Tegevus"] = ud["Tegevus"].map({"up": "⬆ tõstis", "down": "⬇ langetas", "main": "kinnitas", "init": "alustas", "reit": "kordas"}).fillna(ud["Tegevus"])
        st.dataframe(ud, hide_index=True, use_container_width=True)
    else:
        st.info("Andmeid pole.")

    st.markdown("**Uudised**")
    if data["news"]:
        for n in data["news"]:
            meta = " · ".join(str(x)[:10] for x in [n.get("source"), n.get("date")] if x)
            st.markdown(f"- [{n['title']}]({n['url']}) <span style='opacity:.6'>{meta}</span>", unsafe_allow_html=True)
    else:
        st.caption(f"Uudiseid ei õnnestunud laadida. Vaata: https://finance.yahoo.com/quote/{ticker}/news")

# ---------------------------------------------------------------- Ajalooline test

with T_BT:
    st.markdown(
        f"""
Kui hästi oleks **ainult tehniline osa** {ticker} puhul viimase ~4 aasta jooksul töötanud.
Fundamentaal- ja analüütikuandmeid ajaloo kohta pole, neid see test ei kata.

- **Ostusignaal: tõusis** – kui skoor oli ≥ +10, mitu % juhtudest oli hind horisondi lõpus kõrgem
- Võrdle seda reaga **Tõusis (kõik päevad)** – see on "lihtsalt hoia" baas
- **Korrelatsioon** > 0 tähendab, et skoor on suunda õigesti näidanud
"""
    )
    bt = A.backtest(res)
    if not bt.empty:
        show = bt.set_index("Horisont").T
        fmt = {}
        for idx in show.index:
            if "päevi" in idx.lower() or idx == "Päevi testis":
                fmt[idx] = "{:.0f}"
            elif idx == "Korrelatsioon":
                fmt[idx] = "{:+.2f}"
            else:
                fmt[idx] = "{:.1%}"
        st.dataframe(pd.DataFrame({c: [fmt[i].format(v) if pd.notna(v) else "–" for i, v in show[c].items()] for c in show.columns},
                                  index=show.index), use_container_width=True)
    st.info("Laiemas testis (20 USA suurettevõtet, mida mudeli häälestamisel ei kasutatud) oli korrelatsioon positiivne "
            "90% (4 näd), 80% (12 näd) ja 70% (26 näd) aktsiatest. Ostusignaali järel oli keskmine tootlus "
            "12 nädalaga 6,6% (kõik päevad 4,2%) ja 26 nädalaga 10,6% (kõik päevad 8,8%). "
            "Eelis on olemas, aga tagasihoidlik – mitte garantii.")

# ---------------------------------------------------------------- Võrdlus

with T_CMP:
    lst = st.text_input("Tickerid komaga eraldatult", value="AAPL, MSFT, NVDA, GOOGL, AMZN, META, TSLA")
    if st.button("Võrdle", type="primary"):
        rows = []
        prog = st.progress(0.0)
        tks = [t.strip().upper() for t in lst.split(",") if t.strip()]
        for i, tk in enumerate(tks):
            try:
                dt, rs = run(tk)
                inf = dt["info"]
                row = {"Ticker": tk, "Nimi": (inf.get("shortName") or "")[:28], "Hind": round(rs["price"], 2)}
                for lbl, v in rs["views"].items():
                    row[f"{lbl}"] = f"{SIGNAL_ICON[v['signal']]} {v['signal']} ({v['score'] * 100:+.0f})"
                row["12 näd oodatav"] = pct(rs["views"]["12 nädalat"]["exp_ret"])
                row["26 näd oodatav"] = pct(rs["views"]["26 nädalat"]["exp_ret"])
                row["Analüütikute siht"] = pct(inf["targetMeanPrice"] / rs["price"] - 1) if inf.get("targetMeanPrice") else "–"
                row["Forward P/E"] = round(inf["forwardPE"], 1) if inf.get("forwardPE") else None
                row["_s"] = rs["views"]["12 nädalat"]["score"]
                rows.append(row)
            except Exception as e:
                rows.append({"Ticker": tk, "Nimi": f"viga: {e}"[:40], "_s": -9})
            prog.progress((i + 1) / len(tks))
        prog.empty()
        df = pd.DataFrame(rows).sort_values("_s", ascending=False).drop(columns="_s")
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.caption("Järjestatud 12 nädala skoori järgi.")

# ---------------------------------------------------------------- Õpetus

with T_HELP:
    st.subheader("📘 Kuidas seda lehte lugeda ja aktsiat analüüsida")
    st.markdown(
        """
Aktsia hinda mõjutavad kolm asja: **ettevõtte enda tulemused** (fundamentaal),
**turu meeleolu ja hinnaliikumine** (tehniline) ja **ootused** (analüütikud).
See leht näitab kõiki kolme ja paneb need ühte hinnangusse. Allpool on iga osa
lahti seletatud: mida see näitab, miks seda vaja on ja kuidas seda vaadata.
"""
    )

    with st.expander("🧭 Kiire tööjärjekord: kuidas ühte aktsiat 10 minutiga analüüsida", expanded=True):
        st.markdown(
            """
1. **Lihtne vastus** lehe ülaosas. Loe läbi „Järgmise 3 kuu vaade“ ja selle selgitus tavakeeles.
2. **Ülevaade → hinnangukaardid.** Mis signaal on 4, 12 ja 26 nädalal? Kas kõik näitavad
   samas suunas? Kui jah ja kindlus on *kõrge*, on pilt selgem.
3. **Ülevaade → „Räägib poolt / vastu“.** See on kõige tähtsam osa: saad aru, *miks* skoor on selline.
4. **Ettevõte.** Kas ettevõte kasvab, teenib kasumit ja pole üle võlgu? Kas hind (P/E) on
   kasvu suhtes mõistlik? Kui palju on analüütikute hinnasiht praegusest kõrgemal?
5. **Graafik.** Kas hind on tõusutrendis või languses? Lülita sisse „tehnilised näitajad“,
   kui tahad näha RSI-d ja MACD-d.
6. **Kollased hoiatused:** tulemuste avaldus lähipäevil tähendab suuremat hinnakõikumist.
7. **Ülevaate lõpus „Kas mudel on varem töötanud?“** Kui korrelatsioon on negatiivne,
   usalda skoori selle aktsia puhul vähem.
8. **Otsus on sinu.** Mudel on abivahend. Mõtle alati, kui palju oled valmis kaotama.
"""
        )

    with st.expander("📊 Ülevaade: hinnangukaardid"):
        st.markdown(
            """
| Rida | Mida näitab | Kuidas vaadata |
|---|---|---|
| **Signaal** (OST … MÜÜ) | Kokkuvõte skoorist | OST ≥ +25, KERGE OST +10…+25, HOIA −10…+10, KERGE MÜÜK −10…−25, MÜÜ ≤ −25 |
| **Skoor** | Kõigi gruppide kaalutud keskmine, −100 kuni +100 | Mida kaugemal nullist, seda tugevam signaal. Alla ±10 on sisuliselt neutraalne |
| **Kindlus** | Kas grupid on omavahel ühel meelel | *Kõrge* = tehniline, fundamentaal ja analüütikud näitavad samas suunas. *Madal* = vastuolulised signaalid, ole ettevaatlik |
| **Tõusu tõenäosus** | Hinnanguline võimalus, et hind on horisondi lõpus kõrgem | 50% = mündiviske. 60%+ on juba märgatav eelis. Üle 70% tuleb harva |
| **Oodatav hind** | Vahemiku keskpunkt | See pole lubadus, vaid kõige tõenäolisem *keskmine* tulemus |
| **80% vahemik** | 8 korral 10-st peaks hind jääma sinna vahele | Lai vahemik = volatiilne aktsia = suurem risk. Alumine piir näitab realistlikku halba stsenaariumi |

**Miks kolm horisonti?** Lühikesel ajal liigutab hinda peamiselt meeleolu, pikal
ajal ettevõtte tulemused. Seetõttu on 4 nädala hinnangus rohkem tehnilist analüüsi
ja 26 nädala hinnangus rohkem fundamentaali ja analüütikuid.

**Grupiskoorid** (tulpdiagramm) näitavad iga grupi skoori eraldi: sinine = positiivne,
oranž = negatiivne.

**Hinnaprognoosi graafik:** sinine joon on viimase aasta hind, punktiir on oodatav tee
ja helesinine lehter on 80% vahemik. Lehter läheb laiemaks, sest mida kaugemale
tulevikku, seda ebakindlam. Lilla katkendjoon on analüütikute 12 kuu hinnasiht.
"""
        )

    with st.expander("📈 Graafik: küünlad, keskmised, RSI, MACD"):
        st.markdown(
            """
**Küünlad (candlesticks)**: iga küünal on üks päev. Roheline = päev lõppes tõusuga,
punane = langusega. Paks osa näitab avamis- ja sulgemishinda, peenikesed jooned päeva
kõrgeimat ja madalaimat hinda.

**Libisevad keskmised (SMA)**: silutud hinnajoon, mis näitab trendi.
- **SMA20** (kollane): lühike trend, umbes 1 kuu
- **SMA50** (oranž): keskmine trend, umbes 2,5 kuud
- **SMA200** (lilla): pikk trend, umbes 1 aasta. Kõige tähtsam joon
- *Kuidas vaadata:* hind üle SMA200 = pikaajaline tõusutrend. Kui SMA50 lõikab SMA200
  alt üles, on see „kuldne rist“ (tõusumärk), ülevalt alla „surmarist“ (langusmärk).
- ⚠️ *Selle mudeli eripära:* kui hind on SMA200-st **väga kaugel üleval** (nt +20%),
  on see ettevaatusmärk. Ajaloos on sellised aktsiad järgnevatel kuudel sageli jahtunud.

**Bollingeri ribad** (hall ala): tavapärane kõikumisvahemik, 20 päeva keskmine ±2
standardhälvet. Hind üle ülemise riba = lühiajaliselt üle ostetud, alla alumise
= üle müüdud. Kitsad ribad = vaikne periood, millele järgneb tihti suurem liikumine.

**Maht**: mitu aktsiat päevas kaubeldi. Suur maht hinnaliikumise ajal = liikumine
on „päris“, suured tegijad on asjas. Suur hinnamuutus väikese mahuga on nõrgem signaal.

**RSI (0–100)**: kui tugevalt on viimasel ajal ostetud või müüdud.
- **üle 70** = üle ostetud, tõus võib väsida
- **alla 30** = üle müüdud, võimalik põrge
- **45–65** = terve, rahulik tõus

**MACD**: näitab, kas trend kiireneb või aeglustub.
- Sinine joon üle oranži = tõusumomentum, all = langusmomentum
- Tulbad (histogramm) näitavad nende vahet. Kasvavad rohelised tulbad = tõus tugevneb,
  kahanevad = tõus väsib

**ATR**: keskmine päevane hinnakõikumine. Aitab hinnata, kui kaugele *stop-loss*
panna: tavaliselt 2–3 × ATR praegusest hinnast allapoole.
"""
        )

    with st.expander("🏢 Fundamentaal: kas ettevõte on hea ja kas hind on mõistlik"):
        st.markdown(
            """
| Näitaja | Mida näitab | Hea | Halb |
|---|---|---|---|
| **P/E** | Hind ÷ aasta kasum. Mitu aastat kasumit maksad | 10–20 | üle 40 või negatiivne |
| **Forward P/E** | Sama, aga *järgmise* aasta oodatava kasumiga | madalam kui praegune P/E = kasum kasvab | |
| **PEG** | P/E ÷ kasumi kasvutempo. Arvestab kasvu | alla 1 = odav kasvu suhtes | üle 2–3 = kallis |
| **P/B** | Hind ÷ raamatupidamislik vara | alla 3 | sõltub palju sektorist |
| **EV/EBITDA** | Ettevõtte koguväärtus ÷ ärikasum (arvestab võlga) | alla 12 | üle 25 |
| **Käibe kasv** | Kui palju müük aastaga kasvas | üle 10% | negatiivne |
| **Kasumi kasv** | Kui palju kasum aastaga kasvas | üle 15% | negatiivne |
| **Bruto-/puhasmarginaal** | Mitu senti 1 eurost müügist jääb kasumiks | puhasmarginaal üle 15% | alla 5% või kahjum |
| **ROE** | Omakapitali tootlus. Kui tõhusalt raha teenitakse | üle 15% | alla 5% |
| **Võlg / omakapital** | Võlakoormus | alla 100% | üle 200% |
| **Vaba rahavoog (FCF)** | Raha, mis jääb pärast investeeringuid. Kõige ausam kasuminäitaja | positiivne ja kasvav | negatiivne |
| **Dividenditootlus** | Aastane dividend ÷ hind | stabiilsetel ettevõtetel 2–5% | väga kõrge (üle 8%) võib tähendada probleemi |
| **Beeta** | Kõikumine võrreldes turuga | 1 = nagu turg | üle 1,5 = palju kõikuvam |
| **Lühikeseks müüdud** | Osa aktsiatest, mille langusele panustatakse | alla 5% | üle 15% = paljud ootavad langust |

**Kõige tähtsam reegel:** kõrge P/E pole iseenesest halb, kui ettevõte kasvab kiiresti
(vaata PEG-i). Odav aktsia pole iseenesest hea, kui käive ja kasum langevad.
Võrdle alati sama sektori ettevõtetega: tehnoloogias on P/E 30 normaalne,
pankades kallis.
"""
        )

    with st.expander("🎯 Analüütikud: mida suured pangad arvavad"):
        st.markdown(
            """
- **Hinnasiht** on analüütikute keskmine ootus hinnale **12 kuu pärast**. Vaata ka
  madalaimat ja kõrgeimat sihti: suur vahe tähendab, et ekspertide arvamused lähevad lahku.
- **Konsensus 1–5**: 1 = tugev ost, 3 = hoia, 5 = müü. Alla 2 on väga positiivne.
- **Soovituste jaotus**: kas „ost“ soovitusi tuleb kuude lõikes juurde või jääb vähemaks.
  Suund on sageli tähtsam kui tase.
- **Reitingumuutused**: kõige värskem info. Mitu järjestikust *tõstmist* (⬆) on
  positiivne märk.
- ⚠️ Analüütikud on sageli liiga optimistlikud ja reageerivad hinnale hilinemisega.
  Kasuta neid ühe sisendina, mitte tõena.
- Kui hind on juba **üle** keskmise hinnasihi, on suur osa ootustest hinnas.
"""
        )

    with st.expander("🔁 Ülevenitatus ehk miks „tugev tõus“ on siin ettevaatusmärk"):
        st.markdown(
            """
Levinud tarkus ütleb: *„trend on sõber, osta tõusvat aktsiat“*. Testisin seda
40 USA suurettevõtte andmetel aastatel 2022–2026. Üksiku aktsia puhul 1–6 kuu
vaates tulemus kinnitust ei leidnud: aktsiad, mis olid oma keskmisest väga kaugele
tõusnud, kippusid järgmistel kuudel jahtuma. Kaugele langenud aktsiad kippusid
taastuma. Seda nimetatakse **keskmisele naasmiseks** (mean reversion).

Seepärast annab mudel:
- **miinuspunkte**, kui hind on palju üle 200 päeva keskmise või on 3–6 kuuga palju tõusnud
- **plusspunkte**, kui hind on keskmisest tugevalt allpool

⚠️ See ei kehti alati. Kui ettevõttel on päris probleem (kahjum, skandaal, langev
käive), võib langus jätkuda. Seepärast vaata alati ka fundamentaali: **odav + terve
ettevõte** on hea kombinatsioon, **odav + kehvad tulemused** võib olla lõks.
"""
        )

    with st.expander("🧪 Ajalooline test: kas mudelit saab selle aktsia puhul usaldada"):
        st.markdown(
            """
Test vaatab iga päeva viimase ~4 aasta jooksul: mis oli tol päeval tehniline skoor
ja mis juhtus hinnaga järgmise 4 / 12 / 26 nädala jooksul.

- **Tõusis (kõik päevad)**: kui tihti hind lihtsalt tõusis, ükskõik mis signaal oli.
  See on võrdlusbaas („osta ja hoia“).
- **Ostusignaal: tõusis**: kui tihti hind tõusis pärast ostusignaali. **Peab olema
  baasist kõrgem**, muidu signaal ei lisa midagi.
- **Ostusignaal: keskm. tootlus** vs **Keskm. tootlus (kõik)**: sama mõte tootluse kohta.
- **Korrelatsioon**: +0,1…+0,3 = skoor on suunda hästi näidanud. Lähedal nullile = pole
  midagi näidanud. Negatiivne = mudel on selle aktsia puhul eksinud, usalda vähem.

Piirang: test katab ainult tehnilist osa, sest fundamentaal- ja analüütikuandmete
ajalugu pole saadaval.
"""
        )

    with st.expander("⚠️ Riskid ja head tavad"):
        st.markdown(
            """
- **Ükski mudel ei ennusta tulevikku kindlalt.** 60% tõenäosus tähendab, et 4 korral 10-st läheb teisiti.
- **Hajuta.** Ära pane kõike ühte aktsiasse. 10–20 eri sektori aktsiat või indeksifond vähendab riski oluliselt.
- **Tulemuste avaldused** (kollane hoiatus) võivad liigutada hinda ühe päevaga ±10–20%.
- **Mõtle enne ostu läbi väljumine:** mis hinnaga müüd kahjumiga (stop-loss) ja mis hinnaga võtad kasumi.
  80% vahemiku alumine piir ja ATR aitavad seda paika panna.
- **Kulud ja maksud:** sagedane kauplemine sööb tootluse ära. Eestis aitab investeerimiskonto maksu edasi lükata.
- **Indeksifond (nt S&P 500) on alati võrdlusbaas.** Kui sa ei usu, et valitud aktsia teeb
  indeksist paremini, on indeks lihtsam valik.
- See tööriist on õppimiseks ja analüüsi toeks, **mitte investeerimisnõuanne**.
"""
        )

    with st.expander("📖 Sõnastik"):
        st.markdown(
            """
- **Ticker**: aktsia lühinimi börsil (AAPL = Apple)
- **Volatiilsus**: kui palju hind kõigub. 25% aastas on tavaline suurettevõttel, 50%+ on väga kõikuv
- **52 näd vahemik**: viimase aasta madalaim ja kõrgeim hind
- **Momentum**: hinnaliikumise hoog, ehk kui palju on hind viimastel kuudel muutunud
- **Suhteline tugevus**: kas aktsia on teinud turust (S&P 500) paremini või halvemini
- **S&P 500 / SPY**: USA 500 suurima ettevõtte indeks, „turu“ mõõdupuu
- **Turuväärtus**: aktsia hind × aktsiate arv, ehk kogu ettevõtte väärtus börsil
- **Stop-loss**: eelnevalt paika pandud hind, millest allapoole müüd, et kahjum ei kasvaks
"""
        )


    with st.expander("⚙️ Kuidas hinnang arvutatakse"):
        st.markdown(
            """
**4 gruppi, igaüks −100 … +100:**
- **Tehniline (lühiajaline):** RSI, MACD, Bollinger, hind vs 20p keskmine, 1 kuu liikumine
- **Tehniline (ülevenitatus):** kui kaugel on hind 200p keskmisest, 3/6 kuu tõus, tugevus vs S&P 500.
  *Kaugele tõusnud = ettevaatust, kaugele langenud = tõusuruum* (ajaloos nii töötanud)
- **Fundamentaalne:** P/E, PEG, kasv, marginaal, ROE, võlg, vaba rahavoog
- **Analüütikud:** keskmine hinnasiht ja konsensussoovitus

**Kaalud horisondi järgi:**

| Grupp | 4 näd | 12 näd | 26 näd |
|---|---|---|---|
| Tehniline (lühiajaline) | 35% | 10% | 5% |
| Tehniline (ülevenitatus) | 30% | 30% | 25% |
| Fundamentaalne | 15% | 30% | 35% |
| Analüütikud | 20% | 30% | 35% |

**Hinnavahemik:** arvutatakse aktsia enda viimase aasta volatiilsusest (80% tõenäosusega
jääb hind sinna vahele). Vahemiku keskpunkti nihutab skoor. Turu pikaajaline keskmine
tootlus (~7% aastas) on arvestatud.

**Päeva ideed:** iga päev skaneeritakse ~40 USA suurettevõtet. Järjestus põhineb
12 ja 26 nädala skooride keskmisel. Ühest sektorist võetakse maksimaalselt üks idee.
"""
        )

# ---------------------------------------------------------------- Päeva ideed
# (täidetakse viimasena, et ülejäänud leht jõuaks enne skaneerimist ekraanile)

with T_IDEAS:
    today = dt.date.today().isoformat()
    st.markdown(f"""<div class="card"><div class="ct">💡 Päeva 3 ideed analüüsiks<span class="hint">{dt.date.today():%d.%m.%Y}</span></div>
<div class="fg" style="font-size:13.5px;color:var(--ink2)">Mudel skaneerib iga päev {len(UNIVERSE)} USA suurettevõtet ja valib 3 kõrgeima
skooriga aktsiat eri sektoritest (12 + 26 nädala vaade). Need on <b>ideed edasiseks uurimiseks</b>, mitte ostusoovitus.</div></div>""",
                unsafe_allow_html=True)
    st.write("")
    with st.spinner("Skaneerin aktsiaid… (esimest korda päevas ~30 sek)"):
        picks, scanned = daily_ideas(today)
    if not picks:
        st.info("Ideid ei õnnestunud leida. Andmeallikas võib olla ajutiselt kättesaamatu. Proovi hiljem uuesti.")
    else:
        cols = st.columns(len(picks), gap="medium")
        for i, (col, p) in enumerate(zip(cols, picks), start=1):
            with col:
                t = SIG_TONE[p["v26"]["signal"]]
                pros = "".join(f"<li>{esc(x)}</li>" for x in p["pros"])
                con = f"<div class='fg' style='margin-top:8px;color:#c9302f'>⚠️ {esc(p['con'])}</div>" if p["con"] else ""
                warn = "<div class='note' style='margin-top:10px'>📅 Tulemused lähipäevil – suurem kõikumine</div>" if p["earnings_soon"] else ""
                ups = f"<span class='pill {tone(p['upside'])}'>{pct(p['upside'])}</span>" if p["upside"] is not None else "–"
                st.markdown(f"""
<div class="card sig" style="--accent:{TONE_COLOR[t]}">
  <div class="top"><span class="h">#{i} · {esc(p['sector'])}</span><span class="conf">skoor {p['score'] * 100:+.0f}</span></div>
  <div style="font-size:22px;font-weight:800;margin-top:10px;color:var(--ink)">{esc(p['ticker'])}</div>
  <div class="fg" style="font-size:13px">{esc(p['name'])} · {money(p['price'])}</div>
  <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:12px">
    <span class='fg' style='align-self:center'>12 näd</span>{sig_pill(p['v12']['signal'])}
    <span class='fg' style='align-self:center'>26 näd</span>{sig_pill(p['v26']['signal'])}</div>
  <div class="stats">
    <div class="stat"><div class="k">26 näd oodatav</div><div class="v" style="color:{TONE_COLOR[tone(p['v26']['exp_ret'])]}">{pct(p['v26']['exp_ret'])}</div></div>
    <div class="stat"><div class="k">Analüütikute siht</div><div class="v">{ups}</div></div>
  </div>
  <div class="ct" style="margin:14px 0 4px;font-size:13px">Miks</div>
  <ul style="margin:0 0 0 18px;padding:0;font-size:13.5px;color:var(--ink2);line-height:1.5">{pros}</ul>
  {con}{warn}
</div>""", unsafe_allow_html=True)
                st.button(f"Ava {p['ticker']} analüüs →", key=f"idea_{p['ticker']}", on_click=_open, args=(p["ticker"],),
                          use_container_width=True)
        st.caption(f"Skaneeritud {scanned}/{len(UNIVERSE)} aktsiat. Värskendatakse kord päevas. "
                   "Enne otsust vaata alati läbi täisanalüüs, eriti fundamentaal ja riskid.")

st.markdown("<div class='foot'>Andmed: Yahoo Finance (kuni 15 min viitega) · Reeglipõhine mudel · "
            "Informatiivne tööriist, mitte investeerimisnõuanne</div>", unsafe_allow_html=True)
