"""Aktsiaanalüüs – Streamliti rakendus. Käivita: ./start.command"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import analysis as A

try:
    from streamlit_searchbox import st_searchbox
except ImportError:  # varulahendus: tavaline tekstikast
    st_searchbox = None

st.set_page_config(page_title="Aktsiaanalüüs", page_icon="📈", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def _search(q: str):
    return A.search(q)


def search_cached(q: str):
    return _search(q.strip().lower()) if q and q.strip() else []

# Värvid (valideeritud kategooriline palett) + staatusvärvid
BLUE, ORANGE, AQUA, VIOLET, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#eda100"
UP, DOWN, NEUTRAL = "#1baf7a", "#e34948", "#8a8984"
SIGNAL_COLOR = {"OST": UP, "KERGE OST": UP, "HOIA": NEUTRAL, "KERGE MÜÜK": DOWN, "MÜÜ": DOWN}
SIGNAL_ICON = {"OST": "▲▲", "KERGE OST": "▲", "HOIA": "■", "KERGE MÜÜK": "▼", "MÜÜ": "▼▼"}


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


# ---------------------------------------------------------------- vormindus

def money(x, cur="USD"):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    sym = "$" if cur == "USD" else ""
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


def badge(signal):
    c = SIGNAL_COLOR[signal]
    return (f"<span style='background:{c};color:#fff;padding:3px 10px;border-radius:6px;"
            f"font-weight:700;font-size:0.95rem'>{SIGNAL_ICON[signal]} {signal}</span>")


# ---------------------------------------------------------------- külgriba

with st.sidebar:
    st.header("📈 Aktsiaanalüüs")
    if st_searchbox is not None:
        picked = st_searchbox(
            search_cached,
            label="Otsi aktsiat",
            placeholder="Kirjuta nimi või ticker, nt apple, nvidia…",
            key="aktsia_otsing",
            default="AAPL",
            default_options=[("AAPL – Apple Inc. (NASDAQ)", "AAPL")],
            debounce=300,
        )
        ticker = (picked or "AAPL").strip().upper()
        st.caption(f"Valitud: **{ticker}**")
    else:
        ticker = st.text_input("Aktsia ticker", value="AAPL").strip().upper()
    with st.expander("Kuidas hinnang tekib?"):
        st.markdown(
            """
**4 gruppi, igaüks −100 … +100:**
- **Tehniline (lühiajaline):** RSI, MACD, Bollinger, hind vs 20p keskmine, 1 kuu liikumine
- **Tehniline (ülevenitatus):** kui kaugel on hind 200p keskmisest, 3/6 kuu tõus, tugevus vs S&P500.
  *Kaugele tõusnud = ettevaatust, kaugele langenud = tõusuruum* (ajaloos nii töötanud)
- **Fundamentaalne:** P/E, PEG, kasv, marginaal, ROE, võlg, vaba rahavoog
- **Analüütikud:** keskmine hinnasiht ja konsensussoovitus

**Kaalud horisondi järgi:** 1 nädal → peamiselt tehniline; 12 nädalat → rohkem
fundamentaal ja analüütikud.

**Hinnavahemik:** aktsia enda volatiilsusest (80% tõenäosusega jääb hind
vahemikku), keskpunkti nihutab skoor.
"""
        )
    st.caption("⚠️ Informatiivne tööriist, mitte investeerimisnõuanne. Otsused ja risk on sinu.")

if not ticker:
    st.stop()

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

# ---------------------------------------------------------------- päis

name = info.get("longName") or info.get("shortName") or ticker
st.title(f"{name} ({ticker})")
meta = " · ".join(x for x in [info.get("sector"), info.get("industry"), f"turuväärtus {big(info.get('marketCap'))}" if info.get("marketCap") else None] if x)
if meta:
    st.caption(meta)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Hind", money(price, cur), pct(chg))
hi, lo = res["d"]["high_52w"].iloc[-1], res["d"]["low_52w"].iloc[-1]
c2.metric("52 näd vahemik", f"{lo:.0f}–{hi:.0f}", f"{pct(price / hi - 1)} tipust", delta_color="off")
c3.metric("Volatiilsus (aastane)", pct(res["sigma_d"] * math.sqrt(252), sign=False))
tgt = info.get("targetMeanPrice")
c4.metric("Analüütikute siht (12 kuud)", money(tgt, cur), pct(tgt / price - 1) if tgt else None)

for w in res["warnings"]:
    st.warning(w)

tabs = st.tabs(["Ülevaade", "Graafik", "Fundamentaal", "Analüütikud ja uudised", "Ajalooline test", "Võrdlus"])

# ---------------------------------------------------------------- Ülevaade

with tabs[0]:
    st.subheader("Hinnang 1–12 nädalaks")
    cols = st.columns(3)
    for col, (label, v) in zip(cols, res["views"].items()):
        with col, st.container(border=True):
            st.markdown(f"**{label}**")
            st.markdown(badge(v["signal"]), unsafe_allow_html=True)
            st.markdown("  \n".join([
                f"Skoor **{v['score'] * 100:+.0f}** · kindlus **{v['confidence']}**",
                f"Tõusu tõenäosus **{v['p_up'] * 100:.0f}%**",
                f"Oodatav hind **{money(v['mid'], cur)}** ({pct(v['exp_ret'])})",
                f"80% vahemik **{v['low']:.2f} – {v['high']:.2f}**",
            ]))
    st.caption("Skoor −100 … +100. Kindlus näitab, kas grupid on omavahel ühel meelel. "
               "1 nädala vaade on ajaloos olnud nõrgim – suhtu sellesse kui müra lähedasse.")

    left, right = st.columns([1, 1.3])
    with left:
        st.markdown("**Grupiskoorid**")
        g = {A.GROUP_NAMES[k]: v * 100 for k, v in res["groups"].items() if v is not None}
        fig = go.Figure(go.Bar(
            x=list(g.values()), y=list(g.keys()), orientation="h",
            marker_color=[BLUE if x >= 0 else ORANGE for x in g.values()],
            text=[f"{x:+.0f}" for x in g.values()], textposition="outside",
            hovertemplate="%{y}: %{x:+.0f}<extra></extra>",
        ))
        fig.update_layout(height=260, margin=dict(l=0, r=30, t=10, b=10), xaxis=dict(range=[-110, 110], zeroline=True))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.markdown("**Hinnaprognoos (80% vahemik)**")
        d = res["d"].tail(126)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=d.index, y=d["Close"], name="Hind", line=dict(color=BLUE, width=2),
                                 hovertemplate="%{x|%d.%m.%Y}: %{y:.2f}<extra></extra>"))
        last_date = d.index[-1]
        fut = pd.bdate_range(last_date, periods=61)
        v12 = res["views"]["12 nädalat"]
        mu_d = math.log(v12["mid"] / price) / 60
        sd = res["sigma_d"]
        t = np.arange(61)
        mid = price * np.exp(mu_d * t)
        up = price * np.exp(mu_d * t + A.Z80 * sd * np.sqrt(t))
        dn = price * np.exp(mu_d * t - A.Z80 * sd * np.sqrt(t))
        fig.add_trace(go.Scatter(x=list(fut) + list(fut[::-1]), y=list(up) + list(dn[::-1]), fill="toself",
                                 fillcolor="rgba(42,120,214,0.15)", line=dict(width=0), name="80% vahemik", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=fut, y=mid, name="Oodatav", line=dict(color=BLUE, width=2, dash="dot"),
                                 hovertemplate="%{x|%d.%m.%Y}: %{y:.2f}<extra></extra>"))
        for label, v in res["views"].items():
            x = fut[min(v["days"], 60)]
            fig.add_trace(go.Scatter(x=[x], y=[v["mid"]], mode="markers+text", marker=dict(size=9, color=BLUE),
                                     text=[label if v["days"] == 60 else ""], textposition="top center", showlegend=False,
                                     hovertemplate=f"{label}: %{{y:.2f}} ({v['low']:.2f}–{v['high']:.2f})<extra></extra>"))
        if tgt:
            fig.add_hline(y=tgt, line=dict(color=VIOLET, dash="dash", width=1.5),
                          annotation_text=f"Analüütikute siht {tgt:.0f}", annotation_position="top left")
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=10), hovermode="x unified",
                          legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Mis hinnangut mõjutab")
    facs = sorted(res["factors"], key=lambda f: f[2], reverse=True)
    pos = [f for f in facs if f[2] > 0.05][:7]
    neg = [f for f in facs[::-1] if f[2] < -0.05][:7]
    a, b = st.columns(2)
    with a:
        st.markdown("**✅ Toetavad**")
        for grp, nm, s, txt in pos:
            st.markdown(f"- {txt} <span style='opacity:.6'>({A.GROUP_NAMES[grp]}, {s * 100:+.0f})</span>", unsafe_allow_html=True)
        if not pos:
            st.markdown("_Puuduvad_")
    with b:
        st.markdown("**⚠️ Vastu**")
        for grp, nm, s, txt in neg:
            st.markdown(f"- {txt} <span style='opacity:.6'>({A.GROUP_NAMES[grp]}, {s * 100:+.0f})</span>", unsafe_allow_html=True)
        if not neg:
            st.markdown("_Puuduvad_")
    st.caption("Tehniline (ülevenitatus) ja hinna kaugus keskmistest töötavad vastupidi tavatarkusele: tugev tõus on "
               "ettevaatusmärk, tugev langus tõusuruum. 2022–2026 testis on aktsiad pärast kaugele venitamist "
               "järgmistel kuudel keskmiselt keskmisele lähemale naasnud (vt 'Ajalooline test').")

# ---------------------------------------------------------------- Graafik

with tabs[1]:
    per = st.radio("Periood", ["3 kuud", "6 kuud", "1 aasta", "2 aastat", "5 aastat"], index=2, horizontal=True)
    n = {"3 kuud": 63, "6 kuud": 126, "1 aasta": 252, "2 aastat": 504, "5 aastat": 1300}[per]
    d = res["d"].tail(n)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.55, 0.13, 0.16, 0.16],
                        subplot_titles=("Hind", "Maht", "RSI (14)", "MACD"))
    fig.add_trace(go.Scatter(x=d.index, y=d["BB_up"], line=dict(width=0), showlegend=False, hoverinfo="skip"), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["BB_dn"], line=dict(width=0), fill="tonexty", fillcolor="rgba(138,137,132,0.12)",
                             name="Bollinger", hoverinfo="skip"), 1, 1)
    fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"], name="Hind",
                                 increasing_line_color=UP, decreasing_line_color=DOWN), 1, 1)
    for col, color in (("SMA20", YELLOW), ("SMA50", ORANGE), ("SMA200", VIOLET)):
        fig.add_trace(go.Scatter(x=d.index, y=d[col], name=col, line=dict(color=color, width=1.5)), 1, 1)
    fig.add_trace(go.Bar(x=d.index, y=d["Volume"], name="Maht", showlegend=False,
                         marker_color=np.where(d["Close"] >= d["Open"], UP, DOWN)), 2, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["RSI"], name="RSI", line=dict(color=BLUE, width=1.5), showlegend=False), 3, 1)
    for lvl in (30, 70):
        fig.add_hline(y=lvl, line=dict(color=NEUTRAL, dash="dot", width=1), row=3, col=1)
    fig.add_trace(go.Bar(x=d.index, y=d["MACD_hist"], name="MACD hist", showlegend=False,
                         marker_color=np.where(d["MACD_hist"] >= 0, UP, DOWN)), 4, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["MACD"], name="MACD", line=dict(color=BLUE, width=1.5), showlegend=False), 4, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["MACD_signal"], name="Signaal", line=dict(color=ORANGE, width=1.5), showlegend=False), 4, 1)
    fig.update_layout(height=820, xaxis_rangeslider_visible=False, hovermode="x unified",
                      margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", y=1.04))
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    st.plotly_chart(fig, use_container_width=True)

    last = res["d"].iloc[-1]
    st.markdown(
        f"RSI **{last['RSI']:.0f}** · MACD hist **{last['MACD_hist']:+.2f}** · "
        f"hind vs SMA50 **{pct(last['Close'] / last['SMA50'] - 1)}** · vs SMA200 **{pct(last['Close'] / last['SMA200'] - 1)}** · "
        f"ATR **{last['ATR']:.2f}** ({pct(last['ATR'] / last['Close'], sign=False)} päevas)"
    )

# ---------------------------------------------------------------- Fundamentaal

with tabs[2]:
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

with tabs[3]:
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
            st.plotly_chart(fig, use_container_width=True)
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
            st.plotly_chart(fig, use_container_width=True)
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

with tabs[4]:
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
            "75% (1 näd), 90% (4 näd) ja 80% (12 näd) aktsiatest. Ostusignaali järel oli 12 nädala keskmine tootlus "
            "6,6% vs 4,2% kõigil päevadel. Eelis on olemas, aga tagasihoidlik – mitte garantii.")

# ---------------------------------------------------------------- Võrdlus

with tabs[5]:
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

st.divider()
st.caption("Andmed: Yahoo Finance (võivad olla kuni 15 min viitega). Reeglipõhine mudel, mitte investeerimisnõuanne.")
