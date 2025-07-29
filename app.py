import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from datetime import datetime, timedelta

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
        hist = stock.history(period="90d")
        info = stock.info

        if hist.empty:
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

        best_premium = 0
        best_strike = None
        best_dte = None
        put_spreads = []

        if stock.options:
            for exp in stock.options:
                try:
                    dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.today()).days
                    if dte > dte_days:
                        continue
                    opt_chain = stock.option_chain(exp)

                    # Covered Call Scan
                    for call in opt_chain.calls.itertuples():
                        if call.strike > price and call.bid >= price * (min_premium_pct / 100):
                            best_premium = call.bid
                            best_strike = call.strike
                            best_dte = dte
                            break

                    # Put Credit Spread Scan
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
                                    "Expiration": exp
                                })
                                break
                except:
                    continue

        return {
            "Ticker": ticker,
            "Price": price,
            "Breakout High": breakout_high,
            "Breakout": breakout,
            "RSI": round(rsi, 2),
            "IV": round(info.get("impliedVolatility", 0) * 100, 2),
            "Option DTE": best_dte,
            "Strike": best_strike,
            "Covered Call Premium": best_premium,
            "Sector": info.get("sector", "N/A"),
            "Market Cap": info.get("marketCap", 0),
            "Dividend Yield": round(info.get("dividendYield", 0) * 100, 2),
            "Avg Volume": info.get("averageVolume", 0),
            "Earnings Date": info.get("earningsDate", "N/A"),
            "Put Spreads": put_spreads
        }
    except:
        return None

def fetch_economic_calendar():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    try:
        df = pd.read_xml(url)
        df['color'] = df['impact'].map({"High": "🔴", "Medium": "🟡", "Low": "🟢"})
        return df[["date", "time", "country", "event", "impact", "color"]]
    except:
        return pd.DataFrame()

with st.sidebar:
    st.header("Scan Settings")
    watchlist = st.text_area("Enter stock tickers (comma separated):", ",".join(load_default_tickers()), key="watchlist")
    rsi_min = st.slider("RSI Minimum", 0, 100, 40)
    rsi_max = st.slider("RSI Maximum", 0, 100, 60)
    iv_min = st.slider("Minimum Implied Volatility (%)", 0, 150, 30)
    vol_min = st.number_input("Minimum Avg Volume (1M)", value=1000000, step=100000)
    breakout_days = st.select_slider("Breakout Window (days)", options=[30, 60], value=30)
    dte_days = st.slider("Max DTE for Covered Calls", 7, 60, 30)
    min_premium_pct = st.slider("Min Covered Call Premium (% of stock price)", 0.5, 10.0, 1.5)
    run = st.button("🔍 Run Scan")

entry_date = datetime.today().date()
exit_date = entry_date + timedelta(days=7)

tabs = st.tabs(["📊 Breakout Scanner", "💰 Covered Calls", "🔐 Put Credit Spreads", "📅 Economic Calendar"])

if run:
    tickers = [x.strip().upper() for x in watchlist.split(",") if x.strip()][:300]
    results = []
    put_spread_rows = []

    for ticker in tickers:
        result = fetch_yfinance_data(ticker, breakout_days, dte_days, min_premium_pct)
        if result and result["RSI"] >= rsi_min and result["RSI"] <= rsi_max and result["IV"] >= iv_min and result["Avg Volume"] >= vol_min:
            results.append(result)
            put_spread_rows.extend(result.get("Put Spreads", []))

    if results:
        df = pd.DataFrame(results)
        with tabs[0]:
            st.subheader("📊 Breakout Candidates")
            breakout_df = df[df["Breakout"] == True]
            st.dataframe(breakout_df)
            st.download_button("📥 Download Breakouts", breakout_df.to_csv(index=False), "breakouts.csv")

        with tabs[1]:
            st.subheader("💰 Covered Call Opportunities")
            cc_df = df[df["Covered Call Premium"] > 0]
            cc_df["Entry Date"] = entry_date
            cc_df["Exit Date"] = exit_date
            st.dataframe(cc_df)
            st.download_button("📥 Download Covered Calls", cc_df.to_csv(index=False), "covered_calls.csv")

        with tabs[2]:
            st.subheader("🔐 Put Credit Spreads")
            ps_df = pd.DataFrame(put_spread_rows)
            ps_df["Entry Date"] = entry_date
            ps_df["Exit Date"] = exit_date
            st.dataframe(ps_df)
            st.download_button("📥 Download Put Spreads", ps_df.to_csv(index=False), "put_spreads.csv")

else:
    with tabs[3]:
        cal = fetch_economic_calendar()
        if not cal.empty:
            cal["event_display"] = cal["color"] + " " + cal["event"]
            st.dataframe(cal[["date", "time", "country", "event_display", "impact"]], use_container_width=True)
        else:
            st.warning("Could not load calendar data.")
