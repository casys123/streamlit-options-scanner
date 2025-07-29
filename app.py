import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime, timedelta
from xml.etree import ElementTree
import traceback

st.set_page_config(page_title="Stock Options Strategy Scanner", layout="wide")
st.title("📈 Stock Options Breakout, Covered Calls & Put Credit Spreads")

@st.cache_data
def load_default_tickers():
    try:
        return pd.read_csv("default_stock_list.csv")["Ticker"].tolist()[:300]
    except:
        return ["AAPL", "MSFT", "TSLA", "AMZN", "NVDA", "AMD", "GOOGL", "META", "NFLX", "INTC"]

def fetch_yfinance_data(ticker, breakout_days, dte_days, min_premium_pct):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="30d")
        info = stock.info if stock.info else {}

        if hist.empty:
            st.warning(f"No historical data for {ticker}")
            return None

        close = hist["Close"]
        change = close.diff()
        gain = change.where(change > 0, 0)
        loss = -change.where(change < 0, 0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs.iloc[-1]))

        price = close.iloc[-1]
        breakout_high = max(close.tail(breakout_days))
        breakout = price >= breakout_high * 0.98

        covered_calls = []
        put_spreads = []

        if stock.options:
            for exp in stock.options:
                try:
                    dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.today()).days
                    if dte > dte_days:
                        continue
                    opt_chain = stock.option_chain(exp)

                    if opt_chain.calls.empty or opt_chain.puts.empty:
                        continue

                    for call in opt_chain.calls.itertuples():
                        if call.strike > price and call.bid >= price * (min_premium_pct / 100):
                            covered_calls.append({
                                "Ticker": ticker,
                                "Expiration": exp,
                                "Strike": call.strike,
                                "Premium": call.bid,
                                "DTE": dte,
                                "Entry Date": datetime.today().date(),
                                "Exit Date": datetime.today().date() + timedelta(days=dte)
                            })

                    puts = opt_chain.puts.sort_values("strike")
                    for i in range(len(puts) - 1):
                        short = puts.iloc[i]
                        long = puts.iloc[i+1]
                        width = long.strike - short.strike
                        credit = short.bid - long.ask
                        if width > 0 and credit > 0 and (credit / width) >= 0.33:
                            pop = 0.70 if short.strike < price else 0.50
                            if pop >= 0.65:
                                put_spreads.append({
                                    "Ticker": ticker,
                                    "Short Strike": short.strike,
                                    "Long Strike": long.strike,
                                    "Credit": round(credit, 2),
                                    "Width": width,
                                    "DTE": dte,
                                    "POP": pop,
                                    "Expiration": exp,
                                    "Entry Date": datetime.today().date(),
                                    "Exit Date": datetime.today().date() + timedelta(days=dte)
                                })
                                break
                except:
                    continue

        iv = round(info.get("impliedVolatility", 0) * 100, 2)

        return {
            "Ticker": ticker,
            "Price": price,
            "Breakout High": breakout_high,
            "Breakout": breakout,
            "RSI": round(rsi, 2),
            "IV": iv,
            "Covered Calls": covered_calls,
            "Put Spreads": put_spreads,
            "Sector": info.get("sector", "N/A"),
            "Market Cap": info.get("marketCap", 0),
            "Dividend Yield": round(info.get("dividendYield", 0) * 100, 2),
            "Avg Volume": info.get("averageVolume", 0),
            "Earnings Date": info.get("earningsDate", "N/A")
        }
    except:
        return None

def fetch_economic_calendar():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    try:
        response = requests.get(url)
        tree = ElementTree.fromstring(response.content)
        events = []
        for item in tree.findall("event"):
            date = item.find("date").text
            time = item.find("time").text
            country = item.find("country").text
            event = item.find("title").text
            impact = item.find("impact").text
            color = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(impact, "⚪")
            events.append({"Date": date, "Time": time, "Country": country, "Event": event, "Impact": impact, "Color": color})
        return pd.DataFrame(events)
    except:
        return pd.DataFrame()

with st.sidebar:
    st.header("Scan Settings")
    watchlist = st.text_area("Enter stock tickers (comma separated):", "AAPL,MSFT,TSLA")
    price_range = st.selectbox("Select stock price range:", ["All", "< $10", "$10 - $50", "$50 - $150", "$150+"], index=0)
    rsi_min = st.slider("RSI Minimum", 0, 100, 0)
    rsi_max = st.slider("RSI Maximum", 0, 100, 100)
    iv_min = st.slider("Minimum Implied Volatility (%)", 0, 150, 0)
    vol_min = st.number_input("Minimum Avg Volume (1M)", value=100000, step=10000)
    breakout_days = st.select_slider("Breakout Window (days)", options=[30, 60], value=30)
    dte_days = st.slider("Max DTE for Covered Calls", 7, 60, 30)
    min_premium_pct = st.slider("Min Covered Call Premium (% of stock price)", 0.5, 10.0, 0.5)
    run = st.button("🔍 Run Scan")

if run:
    tickers = [x.strip().upper() for x in watchlist.split(",") if x.strip()]
    results = []
    breakouts, calls, spreads = [], [], []

    for ticker in tickers:
        result = fetch_yfinance_data(ticker, breakout_days, dte_days, min_premium_pct)
        if result and result["RSI"] >= rsi_min and result["RSI"] <= rsi_max and result["IV"] >= iv_min and result["Avg Volume"] >= vol_min:
            price = result["Price"]
            if (price_range == "< $10" and price >= 10) or \
               (price_range == "$10 - $50" and (price < 10 or price > 50)) or \
               (price_range == "$50 - $150" and (price < 50 or price > 150)) or \
               (price_range == "$150+" and price <= 150):
                continue
            results.append(result)
            if result["Breakout"]:
                breakouts.append(result)
            calls.extend(result["Covered Calls"])
            spreads.extend(result["Put Spreads"])

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Breakout Stocks", "📤 Covered Calls", "📥 Put Credit Spreads", "📅 Econ Calendar"])

    with tab1:
        st.subheader("📊 Breakout Stocks")
        if breakouts:
            st.dataframe(pd.DataFrame(breakouts))
            st.download_button("Download Breakouts", pd.DataFrame(breakouts).to_csv(index=False), "breakouts.csv")
        else:
            st.info("No breakout candidates found.")

    with tab2:
        st.subheader("📤 Covered Call Opportunities")
        if calls:
            st.dataframe(pd.DataFrame(calls))
            st.download_button("Download Covered Calls", pd.DataFrame(calls).to_csv(index=False), "covered_calls.csv")
        else:
            st.info("No covered calls found with current filters.")

    with tab3:
        st.subheader("📥 Put Credit Spreads")
        if spreads:
            st.dataframe(pd.DataFrame(spreads))
            st.download_button("Download Put Spreads", pd.DataFrame(spreads).to_csv(index=False), "put_spreads.csv")
        else:
            st.info("No put credit spreads found with current filters.")

    with tab4:
        st.subheader("📅 Weekly Economic Calendar")
        econ = fetch_economic_calendar()
        if not econ.empty:
            econ["Display"] = econ["Color"] + " " + econ["Event"] + " (" + econ["Impact"] + ")"
            st.dataframe(econ[["Date", "Time", "Country", "Display"]])
            st.download_button("Download Calendar", econ.to_csv(index=False), "calendar.csv")
        else:
            st.error("Could not load economic calendar.")
