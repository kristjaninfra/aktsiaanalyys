"""Aktsiaanalüüsi mootor: andmed, indikaatorid, skoorid ja 4–26 nädala vaade.

Kõik skoorid on vahemikus -1 … +1 (rakenduses näidatakse -100 … +100).
Mudel on reeglipõhine ja läbipaistev. See EI ole investeerimisnõuanne.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")
import logging  # noqa: E402

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# Horisont -> kauplemispäevade arv
HORIZONS = {"4 nädalat": 20, "12 nädalat": 60, "26 nädalat": 130}
LONGEST = max(HORIZONS.values())

# Kui palju iga grupp igal horisondil kaalub
WEIGHTS = {
    20: {"tech_short": 0.35, "tech_long": 0.30, "analyst": 0.20, "fund": 0.15},
    60: {"tech_short": 0.10, "tech_long": 0.30, "analyst": 0.30, "fund": 0.30},
    130: {"tech_short": 0.05, "tech_long": 0.25, "analyst": 0.35, "fund": 0.35},
}

GROUP_NAMES = {
    "tech_short": "Tehniline (lühiajaline)",
    "tech_long": "Tehniline (ülevenitatus)",
    "fund": "Fundamentaalne",
    "analyst": "Analüütikud",
}

MARKET_DRIFT_ANNUAL = 0.07  # aktsiaturu keskmine pikaajaline tootlus
Z80 = 1.2816  # 80% vahemik


# ---------------------------------------------------------------- andmed

def fetch(ticker: str) -> dict:
    """Toob Yahoo Finance'ist kõik vajaliku. Viga tõstetakse ainult hinnaajaloo puudumisel."""
    t = yf.Ticker(ticker)
    hist = t.history(period="5y", auto_adjust=True)
    if hist is None or hist.empty:
        raise ValueError(f"Tickerile '{ticker}' ei leitud hinnaandmeid.")
    hist.index = hist.index.tz_localize(None)

    def safe(fn, default=None):
        try:
            v = fn()
            return default if v is None else v
        except Exception:
            return default

    info = safe(lambda: t.info, {}) or {}
    recs = safe(lambda: t.recommendations, pd.DataFrame())
    updown = safe(lambda: t.upgrades_downgrades, pd.DataFrame())
    calendar = safe(lambda: t.calendar, {}) or {}
    news_raw = safe(lambda: t.get_news(count=10), []) or []

    earnings_date = None
    ed = calendar.get("Earnings Date") if isinstance(calendar, dict) else None
    if ed:
        earnings_date = pd.Timestamp(ed[0] if isinstance(ed, (list, tuple)) else ed)

    news = []
    for n in news_raw:
        c = n.get("content", n)
        url = (c.get("canonicalUrl") or {}).get("url") or c.get("link")
        news.append({
            "title": c.get("title"),
            "date": c.get("pubDate") or c.get("providerPublishTime"),
            "source": (c.get("provider") or {}).get("displayName") or c.get("publisher"),
            "url": url,
        })

    return {
        "ticker": ticker.upper(),
        "hist": hist,
        "info": info,
        "recs": recs if isinstance(recs, pd.DataFrame) else pd.DataFrame(),
        "updown": updown if isinstance(updown, pd.DataFrame) else pd.DataFrame(),
        "earnings_date": earnings_date,
        "news": [n for n in news if n["title"]],
    }


US_EXCHANGES = {"NASDAQ", "NYSE", "NYSEArca", "NYSE American", "BATS Trading", "OTC Markets"}


def search(query: str, limit: int = 8) -> list:
    """Otsib nime või tickeri järgi. Tagastab [(silt, ticker)], USA börsid eespool."""
    query = (query or "").strip()
    if len(query) < 1:
        return []
    try:
        quotes = yf.Search(query, max_results=15, news_count=0).quotes
    except Exception:
        return []
    out = []
    for q in quotes:
        if q.get("quoteType") not in ("EQUITY", "ETF") or not q.get("symbol"):
            continue
        name = (q.get("longname") or q.get("shortname") or "").strip()
        exch = q.get("exchDisp") or q.get("exchange") or ""
        out.append((q["symbol"], name, exch, exch in US_EXCHANGES))
    out.sort(key=lambda x: not x[3])  # USA börsid ette, muidu Yahoo järjekord
    return [(f"{s} – {n} ({e})", s) for s, n, e, _ in out[:limit]]


def fetch_benchmark() -> pd.Series:
    h = yf.Ticker("SPY").history(period="5y", auto_adjust=True)
    h.index = h.index.tz_localize(None)
    return h["Close"]


# ---------------------------------------------------------------- indikaatorid

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c = d["Close"]
    for n in (20, 50, 200):
        d[f"SMA{n}"] = c.rolling(n).mean()
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    d["MACD"] = ema12 - ema26
    d["MACD_signal"] = d["MACD"].ewm(span=9, adjust=False).mean()
    d["MACD_hist"] = d["MACD"] - d["MACD_signal"]

    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["RSI"] = 100 - 100 / (1 + gain / loss)

    std20 = c.rolling(20).std()
    d["BB_up"] = d["SMA20"] + 2 * std20
    d["BB_dn"] = d["SMA20"] - 2 * std20
    d["BB_pct"] = (c - d["BB_dn"]) / (d["BB_up"] - d["BB_dn"])

    prev = c.shift()
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - prev).abs(), (d["Low"] - prev).abs()], axis=1).max(axis=1)
    d["ATR"] = tr.rolling(14).mean()

    d["ret_1m"] = c.pct_change(21)
    d["ret_3m"] = c.pct_change(63)
    d["ret_6m"] = c.pct_change(126)
    d["high_52w"] = c.rolling(252, min_periods=60).max()
    d["low_52w"] = c.rolling(252, min_periods=60).min()
    d["vol_20"] = d["Volume"].rolling(20).mean()
    return d


def _mask(score, source: pd.Series) -> pd.Series:
    return pd.Series(score, index=source.index).where(source.notna())


def tech_components(d: pd.DataFrame, bench: pd.Series | None = None):
    """Tagastab (lühiajalised, trendi) komponendid ajareana, iga veerg -1…+1."""
    c = d["Close"]
    short = pd.DataFrame(index=d.index)
    long = pd.DataFrame(index=d.index)

    # NB: testides 2022–2026 (20 USA suurettevõtet, igal aastal eraldi) ennustas
    # "trend üles = ost" 1–12 nädala tootlust VASTUPIDISELT. Seepärast on hinna
    # kaugus keskmistest ja momentum siin pööratud märgiga (keskmisele naasmine):
    # keskmisest kaugele üles venitatud = ettevaatust, alla venitatud = tõusuruum.
    short["Hind vs SMA20"] = -np.tanh((c / d["SMA20"] - 1) / 0.03)

    h = d["MACD_hist"]
    rising = h.diff() > 0
    short["MACD"] = _mask(np.select([(h > 0) & rising, (h > 0) & ~rising, (h <= 0) & rising], [1.0, 0.3, -0.3], -1.0), h)

    r = d["RSI"]
    short["RSI"] = _mask(np.select([r < 30, r < 45, r <= 65, r <= 75], [0.6, -0.3, 0.3, 0.0], -0.6), r)

    b = d["BB_pct"]
    short["Bollinger"] = _mask(np.select([b > 1, b < 0], [-0.5, 0.5], 0.0), b)

    short["Momentum 1k"] = -np.tanh(d["ret_1m"] / 0.08)

    long["Hind vs SMA200"] = -np.tanh((c / d["SMA200"] - 1) / 0.08)
    long["SMA50 vs SMA200"] = -np.tanh((d["SMA50"] / d["SMA200"] - 1) / 0.04)
    long["Momentum 3k"] = -np.tanh(d["ret_3m"] / 0.15)
    long["Momentum 6k"] = -np.tanh(d["ret_6m"] / 0.25)
    if bench is not None:
        b3 = bench.reindex(d.index).ffill().pct_change(63)
        long["Suhteline tugevus vs S&P500"] = -np.tanh((d["ret_3m"] - b3) / 0.10)
    return short, long


def tech_texts(row: pd.Series, bench_3m: float | None) -> dict:
    """Inimloetav kirjeldus iga tehnilise komponendi kohta (viimase päeva väärtustest)."""
    def pct(x):
        return f"{x * 100:+.1f}%"
    r = row["RSI"]
    rsi_txt = "üle müüdud" if r < 30 else "nõrk" if r < 45 else "terve tõusumomentum" if r <= 65 else "kõrge" if r <= 75 else "üle ostetud"
    b = row["BB_pct"]
    bb_txt = "üle ülemise riba" if b > 1 else "alla alumise riba" if b < 0 else "ribade sees"
    h = row["MACD_hist"]
    t = {
        "Hind vs SMA20": f"hind {pct(row['Close'] / row['SMA20'] - 1)} 20 päeva keskmisest",
        "MACD": f"MACD histogramm {'positiivne' if h > 0 else 'negatiivne'}",
        "RSI": f"RSI {r:.0f} – {rsi_txt}",
        "Bollinger": f"Bollinger: {bb_txt}",
        "Momentum 1k": f"1 kuu tootlus {pct(row['ret_1m'])}",
        "Hind vs SMA200": f"hind {pct(row['Close'] / row['SMA200'] - 1)} 200 päeva keskmisest",
        "SMA50 vs SMA200": f"50p keskmine {pct(row['SMA50'] / row['SMA200'] - 1)} 200p keskmisest",
        "Momentum 3k": f"3 kuu tootlus {pct(row['ret_3m'])}",
        "Momentum 6k": f"6 kuu tootlus {pct(row['ret_6m'])}",
    }
    if bench_3m is not None and not math.isnan(bench_3m):
        t["Suhteline tugevus vs S&P500"] = f"3 kuuga {pct(row['ret_3m'] - bench_3m)} vs S&P500"
    return t


# ---------------------------------------------------------------- fundamentaal ja analüütikud

def _band(x, bands, default):
    for limit, score in bands:
        if x < limit:
            return score
    return default


def fund_components(info: dict, price: float) -> list:
    """[(nimi, skoor, tekst)] – ainult need, mille kohta on andmed olemas."""
    out = []
    fpe = info.get("forwardPE")
    if fpe is not None:
        s = -0.8 if fpe <= 0 else _band(fpe, [(15, 0.6), (25, 0.2), (40, -0.2)], -0.6)
        out.append(("Forward P/E", s, f"forward P/E {fpe:.1f}"))
    peg = info.get("trailingPegRatio") or info.get("pegRatio")
    if peg is not None and peg > 0:
        out.append(("PEG", _band(peg, [(1, 0.7), (2, 0.2), (3, -0.3)], -0.6), f"PEG {peg:.2f}"))
    rg = info.get("revenueGrowth")
    if rg is not None:
        out.append(("Käibe kasv", float(np.tanh(rg / 0.15)), f"käibe kasv {rg * 100:+.1f}% a/a"))
    eg = info.get("earningsGrowth")
    if eg is not None:
        out.append(("Kasumi kasv", float(np.tanh(eg / 0.25)), f"kasumi kasv {eg * 100:+.1f}% a/a"))
    pm = info.get("profitMargins")
    if pm is not None:
        out.append(("Kasumimarginaal", -0.6 if pm < 0 else _band(pm, [(0.1, 0.0), (0.2, 0.3)], 0.6), f"puhasmarginaal {pm * 100:.1f}%"))
    roe = info.get("returnOnEquity")
    if roe is not None:
        out.append(("ROE", -0.5 if roe < 0 else _band(roe, [(0.1, 0.0), (0.2, 0.2)], 0.5), f"ROE {roe * 100:.0f}%"))
    de = info.get("debtToEquity")
    if de is not None:
        out.append(("Võlg/omakapital", _band(de, [(50, 0.4), (100, 0.1), (200, -0.2)], -0.5), f"võlg/omakapital {de:.0f}%"))
    fcf, mc = info.get("freeCashflow"), info.get("marketCap")
    if fcf is not None and mc:
        y = fcf / mc
        out.append(("FCF tootlus", -0.5 if y < 0 else _band(y, [(0.02, 0.0), (0.05, 0.2)], 0.6), f"vaba rahavoo tootlus {y * 100:.1f}%"))
    return out


def analyst_components(info: dict, price: float) -> list:
    out = []
    tgt = info.get("targetMeanPrice")
    n = info.get("numberOfAnalystOpinions") or 0
    if tgt and price:
        up = tgt / price - 1
        out.append(("Hinnasiht", float(np.tanh(up / 0.15)), f"keskmine hinnasiht {tgt:.2f} ({up * 100:+.1f}%), {n} analüütikut"))
    rm = info.get("recommendationMean")
    if rm:
        key = (info.get("recommendationKey") or "").replace("_", " ")
        out.append(("Soovitus", float(np.clip((3 - rm) / 2, -1, 1)), f"konsensus {rm:.2f}/5 ({key})"))
    return out


# ---------------------------------------------------------------- horisondi vaade

def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def signal_label(score: float) -> str:
    if score >= 0.25:
        return "OST"
    if score >= 0.10:
        return "KERGE OST"
    if score > -0.10:
        return "HOIA"
    if score > -0.25:
        return "KERGE MÜÜK"
    return "MÜÜ"


def horizon_view(price: float, sigma_d: float, groups: dict, days: int) -> dict:
    w = WEIGHTS[days]
    avail = {k: v for k, v in groups.items() if v is not None and not math.isnan(v)}
    total_w = sum(w[k] for k in avail)
    score = sum(w[k] * avail[k] for k in avail) / total_w if total_w else 0.0

    vol = sigma_d * math.sqrt(days)
    mu = MARKET_DRIFT_ANNUAL / 252 * days + score * 0.5 * vol
    signs = [np.sign(v) for v in avail.values() if abs(v) > 0.1]
    agreement = abs(sum(signs)) / len(signs) if signs else 0
    conf = "kõrge" if agreement >= 0.75 and abs(score) >= 0.2 else "keskmine" if agreement >= 0.5 else "madal"
    return {
        "days": days,
        "score": score,
        "signal": signal_label(score),
        "confidence": conf,
        "mid": price * math.exp(mu),
        "low": price * math.exp(mu - Z80 * vol),
        "high": price * math.exp(mu + Z80 * vol),
        "exp_ret": math.exp(mu) - 1,
        "p_up": _norm_cdf(mu / vol) if vol else 0.5,
        "groups_used": list(avail),
    }


# ---------------------------------------------------------------- koond

def analyze(data: dict, bench: pd.Series | None) -> dict:
    d = add_indicators(data["hist"])
    info = data["info"]
    last = d.iloc[-1]
    price = float(last["Close"])

    short_df, long_df = tech_components(d, bench)
    ts_now = short_df.iloc[-1].dropna()
    tl_now = long_df.iloc[-1].dropna()
    bench_3m = float(bench.reindex(d.index).ffill().pct_change(63).iloc[-1]) if bench is not None else None
    texts = tech_texts(last, bench_3m)

    fund = fund_components(info, price)
    anal = analyst_components(info, price)

    groups = {
        "tech_short": float(ts_now.mean()) if len(ts_now) else None,
        "tech_long": float(tl_now.mean()) if len(tl_now) else None,
        "fund": float(np.mean([s for _, s, _ in fund])) if fund else None,
        "analyst": float(np.mean([s for _, s, _ in anal])) if anal else None,
    }

    logret = np.log(d["Close"]).diff().dropna()
    sigma_d = float(logret.tail(252).std())

    views = {label: horizon_view(price, sigma_d, groups, days) for label, days in HORIZONS.items()}

    factors = []
    for name, s in ts_now.items():
        factors.append(("tech_short", name, float(s), texts.get(name, name)))
    for name, s in tl_now.items():
        factors.append(("tech_long", name, float(s), texts.get(name, name)))
    for name, s, txt in fund:
        factors.append(("fund", name, s, txt))
    for name, s, txt in anal:
        factors.append(("analyst", name, s, txt))

    warnings_ = []
    ed = data.get("earnings_date")
    if ed is not None:
        days_to = (ed - pd.Timestamp.today().normalize()).days
        if 0 <= days_to <= 90:
            warnings_.append(f"Järgmine tulemuste avaldus {ed:%d.%m.%Y} ({days_to} päeva pärast) – hind võib siis järsult liikuda.")
    if sigma_d * math.sqrt(252) > 0.5:
        warnings_.append(f"Väga volatiilne aktsia (aastane volatiilsus {sigma_d * math.sqrt(252) * 100:.0f}%). Hinnavahemikud on laiad.")
    if not fund:
        warnings_.append("Fundamentaalandmed puuduvad (nt ETF või väike ettevõte) – hinnang põhineb tehnilisel analüüsil.")
    if not anal:
        warnings_.append("Analüütikute andmed puuduvad.")

    return {
        "price": price,
        "prev": float(d["Close"].iloc[-2]),
        "d": d,
        "short_df": short_df,
        "long_df": long_df,
        "groups": groups,
        "views": views,
        "factors": factors,
        "fund": fund,
        "analyst": anal,
        "sigma_d": sigma_d,
        "warnings": warnings_,
    }


# ---------------------------------------------------------------- ajalooline test

def backtest(res: dict) -> pd.DataFrame:
    """Kui hästi oleks AINULT tehniline skoor selle aktsia puhul minevikus töötanud.

    Fundamentaal- ja analüütikuandmeid ajalooliselt pole, seega neid ei testita.
    Aknad kattuvad – tulemus on suunav, mitte statistiliselt range.
    """
    d = res["d"]
    ts = res["short_df"].mean(axis=1)
    tl = res["long_df"].mean(axis=1)
    valid = d["SMA200"].notna()
    rows = []
    for label, days in HORIZONS.items():
        w = WEIGHTS[days]
        s = (w["tech_short"] * ts + w["tech_long"] * tl) / (w["tech_short"] + w["tech_long"])
        fwd = d["Close"].shift(-days) / d["Close"] - 1
        df = pd.DataFrame({"s": s, "f": fwd})[valid].dropna()
        if df.empty:
            continue
        bull, bear = df[df.s >= 0.10], df[df.s <= -0.10]
        rows.append({
            "Horisont": label,
            "Päevi testis": len(df),
            "Tõusis (kõik päevad)": (df.f > 0).mean(),
            "Keskm. tootlus (kõik)": df.f.mean(),
            "Ostusignaal: päevi": len(bull),
            "Ostusignaal: tõusis": (bull.f > 0).mean() if len(bull) else np.nan,
            "Ostusignaal: keskm. tootlus": bull.f.mean() if len(bull) else np.nan,
            "Müügisignaal: päevi": len(bear),
            "Müügisignaal: langes": (bear.f < 0).mean() if len(bear) else np.nan,
            "Müügisignaal: keskm. tootlus": bear.f.mean() if len(bear) else np.nan,
            "Korrelatsioon": df.s.corr(df.f),
        })
    return pd.DataFrame(rows)
