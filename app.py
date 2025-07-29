import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import smtplib
import ssl

st.set_page_config(page_title="Stock Options Strategy Scanner", layout="wide")
st.title("📈 Stock Options Breakout, Covered Calls & Put Credit Spreads")

st.markdown("""
This tool scans **optionable stocks** for:
- 📊 **Breakout potential** (30 to 60 days)
- 💰 **Weekly Covered Call** opportunities with high premiums
- 🔐 **Put Credit Spreads** with ≥65% probability of profit
""")

POLYGON_API_KEY = "ej1WiumfIa3HsbU8HxlqQRTxAbzj9Jnz"
if POLYGON_API_KEY == "ej1WiumfIa3HsbU8HxlqQRTxAbzj9Jnz":
    st.warning("⚠️ Please update your Polygon.io API key to fetch live market data.")

@st.cache_data
def load_default_tickers():
    try:
        return pd.read_csv("default_stock_list.csv")["Ticker"].tolist()[:300]
    except:
        return ["AAPL", "MSFT", "TSLA", "AMZN", "NVDA", "AMD", "GOOGL", "META", "NFLX", "INTC"]

with st.sidebar:
    st.header("Scan Settings")
    default_tickers = ",".join(load_default_tickers())
    watchlist = st.text_area("Enter stock tickers (comma separated):", default_tickers)
    rsi_min = st.slider("RSI Minimum", 0, 100, 40)
    rsi_max = st.slider("RSI Maximum", 0, 100, 60)
    iv_min = st.slider("Minimum Implied Volatility (%)", 0, 150, 30)
    vol_min = st.number_input("Minimum Avg Volume (1M)", value=1000000, step=100000)
    dte_max = st.number_input("Max DTE (days to expiration)", min_value=7, value=45, step=1)
    breakout_days = st.select_slider("Breakout Window (days)", options=[30, 60], value=30)
    auto_email = st.checkbox("📧 Email me daily summary (requires SMTP config)")
    email_address = st.text_input("Email address (optional)") if auto_email else None
    st.markdown("---")
    run = st.button("🔍 Run Scan")

def fetch_polygon_data(ticker):
    try:
        headers = {"Authorization": f"Bearer {POLYGON_API_KEY}"}
        price_url = f"https://api.polygon.io/v2/last/trade/{ticker}?apiKey={POLYGON_API_KEY}"
        summary_url = f"https://api.polygon.io/v3/reference/tickers/{ticker}?apiKey={POLYGON_API_KEY}"
        rsi_url = f"https://api.polygon.io/v1/indicators/rsi/{ticker}?timespan=day&window=14&apiKey={POLYGON_API_KEY}"
        options_url = f"https://api.polygon.io/v3/snapshot/options/{ticker}?apiKey={POLYGON_API_KEY}"

        price_data = requests.get(price_url, headers=headers).json()
        summary_data = requests.get(summary_url, headers=headers).json()
        rsi_data = requests.get(rsi_url, headers=headers).json()
        options_data = requests.get(options_url, headers=headers).json()

        price = price_data.get("results", {}).get("p", None)
        rsi = rsi_data.get("results", {}).get("values", [{}])[-1].get("value", 50)

        iv = 0.0
        volume = 0
        top_iv = 0.0
        top_volume = 0
        top_dte = None
        top_strike = None

        if "results" in options_data:
            options_list = options_data["results"]
            valid_options = [opt for opt in options_list if opt.get("details", {}).get("expiration_date")]
            for opt in valid_options:
                try:
                    exp_date = datetime.strptime(opt["details"]["expiration_date"], "%Y-%m-%d")
                    dte = (exp_date - datetime.now()).days
                    if dte <= dte_max:
                        iv_candidate = opt.get("implied_volatility", 0)
                        vol_candidate = opt.get("volume", 0)
                        if iv_candidate > top_iv and vol_candidate > top_volume:
                            top_iv = iv_candidate
                            top_volume = vol_candidate
                            top_dte = dte
                            top_strike = opt["details"].get("strike_price")
                except:
                    continue

        iv = top_iv
        volume = top_volume

        if price is None:
            st.warning(f"⚠️ No price data found for {ticker}.")
            return None

        return {
            "Ticker": ticker,
            "Price": price,
            "Breakout High": price * 1.03,
            "Breakout": False,
            "RSI": rsi,
            "IV": iv,
            "Option DTE": top_dte,
            "Strike": top_strike,
            "Sector": summary_data.get("results", {}).get("sic_description", "N/A"),
            "Market Cap": summary_data.get("results", {}).get("market_cap", 0),
            "Dividend Yield": 0,
            "Avg Volume": volume,
            "Earnings Date": summary_data.get("results", {}).get("earnings_date", "N/A")
        }
    except Exception as e:
        st.error(f"❌ Error fetching data for {ticker}: {e}")
        return None
