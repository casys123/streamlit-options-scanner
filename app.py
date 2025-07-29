import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime, timedelta
from xml.etree import ElementTree

# -------- CONFIG --------
st.set_page_config(page_title="Stock Scanner", layout="wide")
st.title("📈 Options Strategy Scanner (Breakouts, Covered Calls, Put Credit Spreads)")

# -------- ECONOMIC CALENDAR (US only) --------
@st.cache_data(ttl=302400)  # Cache for ~3.5 days (Twice per week)
def fetch_us_econ_calendar():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    try:
        res = requests.get(url)
        tree = ElementTree.fromstring(res.content)
        events = []
        for e in tree.findall("event"):
            if e.find("country").text != "USD":
                continue
            impact = e.find("impact").text
            color = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(impact, "⚪")
            events.append({
                "Date": e.find("date").text,
                "Time": e.find("time").text,
                "Event": e.find("title").text,
                "Impact": impact,
                "Color": color
            })
        return pd.DataFrame(events)
    except:
        return pd.DataFrame()

# -------- LOAD TICKERS --------
@st.cache_data
def load_optionable_tickers():
    try:
        return pd.read_csv("default_stock_list.csv")["Ticker"].tolist()
    except:
        return ["AAPL", "MSFT", "TSLA", "SPY", "QQQ", "IWM", "DIA", "AMD", "NVDA", "GOOGL", "META", "NFLX"]

# -------- RSI CALC --------
def get_rsi(data, window=14):
    delta = data.diff()
    gain = delta.where(delta > 0, 0).rolling(window=window).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# -------- SCAN FUNCTION --------
def scan_stock(ticker, breakout_days, call_dte_limit, call_min_pct, min_pop=0.65):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="60d")
        if hist.empty:
            return None
        price = hist["Close"].iloc[-1]
        rsi = get_rsi(hist["Close"]).iloc[-1]
        info = stock.info
        iv = round(info.get("impliedVolatility", 0) * 100, 2)
        avg_vol = info.get("averageVolume", 0)

        breakout = price >= hist["Close"].tail(breakout_days).max() * 0.98
        covered_calls, spreads = [], []

        if stock.options:
            for exp in stock.options:
                dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.today()).days
                if dte > call_dte_limit:
                    continue
                chain = stock.option_chain(exp)

                # Covered Calls
                for call in chain.calls.itertuples():
                    if 3 <= price <= 35 and call.strike > price:
                        if call.bid >= price * (call_min_pct / 100):
                            covered_calls.append({
                                "Ticker": ticker, "Strike": call.strike, "Premium": call.bid,
                                "Yield %": round((call.bid / price) * 100, 2), "DTE": dte,
                                "Exp": exp, "Price": price, "Entry": datetime.today().date(),
                                "Exit": datetime.today().date() + timedelta(days=dte)
                            })

                # Put Credit Spreads
                puts = chain.puts.sort_values("strike")
                for i in range(len(puts) - 1):
                    short, long = puts.iloc[i], puts.iloc[i+1]
                    width = long.strike - short.strike
                    credit = short.bid - long.ask
                    if credit > 0 and width > 0 and (credit / width) >= 0.33:
                        pop = 0.75 if short.strike < price else 0.5
                        if pop >= min_pop:
                            spreads.append({
                                "Ticker": ticker, "Short": short.strike, "Long": long.strike,
                                "Credit": round(credit, 2), "Width": width, "POP": pop,
                                "Exp": exp, "DTE": dte, "Price": price
                            })
                            break
        return {
            "Ticker": ticker, "Price": price, "RSI": round(rsi, 2), "IV": iv,
            "Avg Vol": avg_vol, "Breakout": breakout,
            "Covered Calls": covered_calls, "Put Spreads": spreads
        }
    except:
        return None

# -------- UI & TABS --------
tab1, tab2, tab3, tab4 = st.tabs(["📊 Breakouts", "📤 Covered Calls", "📥 Put Credit Spreads", "📅 Calendar"])

with tab1:
    st.subheader("📊 Breakout Stock Scanner")
    breakout_days = st.selectbox("Breakout window", [30, 60])
    rsi_range = st.slider("RSI Range", 0, 100, (30, 70))
    min_vol = st.number_input("Min Avg Volume", value=100000)
    scan_btn = st.button("🔍 Run Breakout Scan")
    if scan_btn:
        tickers = load_optionable_tickers()
        rows = []
        for t in tickers:
            res = scan_stock(t, breakout_days, 14, 1.5)
            if res and res["Breakout"] and rsi_range[0] <= res["RSI"] <= rsi_range[1] and res["Avg Vol"] >= min_vol:
                rows.append(res)
        st.dataframe(pd.DataFrame(rows))

with tab2:
    st.subheader("📤 Covered Call Finder")
    call_dte = st.slider("Max DTE", 7, 30, 14)
    call_prem = st.slider("Min Premium (% of stock price)", 0.5, 10.0, 1.5)
    run_calls = st.button("🔍 Scan Covered Calls")
    if run_calls:
        tickers = load_optionable_tickers()
        calls = []
        for t in tickers:
            r = scan_stock(t, 30, call_dte, call_prem)
            if r and r["Covered Calls"]:
                calls += r["Covered Calls"]
        df = pd.DataFrame(calls)
        st.dataframe(df)
        st.download_button("Download Calls", df.to_csv(index=False), "covered_calls.csv")

with tab3:
    st.subheader("📥 Put Credit Spread Screener")
    min_pop = st.slider("Min POP (%)", 50, 90, 65)
    run_spreads = st.button("🔍 Scan Put Spreads")
    if run_spreads:
        tickers = load_optionable_tickers()
        spreads = []
        for t in tickers:
            r = scan_stock(t, 30, 14, 1.5, min_pop / 100)
            if r and r["Put Spreads"]:
                spreads += r["Put Spreads"]
        df = pd.DataFrame(spreads)
        st.dataframe(df)
        st.download_button("Download Spreads", df.to_csv(index=False), "put_spreads.csv")

with tab4:
    st.subheader("📅 Weekly US Economic Calendar")
    econ = fetch_us_econ_calendar()
    if not econ.empty:
        econ["Label"] = econ["Color"] + \" \" + econ[\"Event\"] + \" (\" + econ[\"Impact\"] + \")\"
        st.dataframe(econ[["Date", "Time", "Label"]])
        st.download_button(\"Download Calendar\", econ.to_csv(index=False), \"econ_calendar.csv\")
    else:
        st.error(\"Could not fetch calendar.\")
