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
        hist = stock.history(period="90d")
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

                    if opt_chain.calls.empty or opt_chain.puts.empty:
                        st.info(f"No options data for {ticker} exp {exp}")
                        continue

                    for call in opt_chain.calls.itertuples():
                        if call.strike > price and call.bid >= price * (min_premium_pct / 100):
                            best_premium = call.bid
                            best_strike = call.strike
                            best_dte = dte
                            break

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
                except Exception as inner_e:
                    st.warning(f"Option chain error for {ticker}: {inner_e}")
                    st.text(traceback.format_exc())
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
    except Exception as e:
        st.error(f"Failed to retrieve data for {ticker}: {e}")
        st.text(traceback.format_exc())
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
            events.append({"date": date, "time": time, "country": country, "event": event, "impact": impact, "color": color})
        return pd.DataFrame(events)
    except Exception as e:
        st.error(f"Could not load calendar: {e}")
        st.text(traceback.format_exc())
        return pd.DataFrame()

# Internet access test
try:
    requests.get("https://www.google.com")
    st.success("✅ Internet access is working!")
except Exception as e:
    st.error(f"❌ No internet access: {e}")
