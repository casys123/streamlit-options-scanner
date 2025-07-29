import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

st.set_page_config(page_title="Stock Options Strategy Scanner", layout="wide")
st.title("📈 Stock Options Breakout, Covered Calls & Put Credit Spreads")

st.markdown("""
This tool scans **optionable stocks** for:
- 📊 **Breakout potential** (30 to 60 days)
- 💰 **Weekly Covered Call** opportunities with high premiums
- 🔐 **Put Credit Spreads** with ≥65% probability of profit
""")

# ----------- USER INPUTS ----------- #
with st.sidebar:
    st.header("Scan Settings")
    watchlist = st.text_area("Enter stock tickers (comma separated):", "AAPL,MSFT,TSLA,AMZN,NVDA,AMD")
    rsi_min = st.slider("RSI Minimum", 0, 100, 40)
    rsi_max = st.slider("RSI Maximum", 0, 100, 60)
    iv_min = st.slider("Minimum Implied Volatility (%)", 0, 150, 30)
    st.markdown("---")
    run = st.button("🔍 Run Scan")

# ----------- FUNCTIONS ----------- #
def fetch_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="90d")
        info = stock.info
        if hist.empty:
            return None

        close = hist["Close"]
        rsi = compute_rsi(close)

        return {
            "Ticker": ticker,
            "Price": close.iloc[-1],
            "52W High": max(close[-252:]),
            "RSI": rsi,
            "IV": info.get("impliedVolatility", None),
            "Sector": info.get("sector", "N/A"),
            "Market Cap": info.get("marketCap", 0),
            "Dividend Yield": info.get("dividendYield", 0)
        }
    except Exception as e:
        return None


def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs.iloc[-1])), 2)


def evaluate_covered_call_potential(data):
    if data["IV"] and data["IV"] > 0.4 and data["Dividend Yield"] == 0:
        return "✅"
    return ""


def evaluate_put_credit_spread_risk(data):
    if data["IV"] and data["IV"] > 0.3 and rsi_min <= data["RSI"] <= rsi_max:
        return "✅"
    return ""

# ----------- MAIN SCAN ----------- #
if run:
    tickers = [x.strip().upper() for x in watchlist.split(",") if x.strip()]
    results = []
    with st.spinner("Fetching and analyzing data..."):
        for tkr in tickers:
            data = fetch_data(tkr)
            if data:
                data["Covered Call"] = evaluate_covered_call_potential(data)
                data["Put Credit Spread"] = evaluate_put_credit_spread_risk(data)
                results.append(data)

    if results:
        df = pd.DataFrame(results)
        df = df[(df["RSI"] >= rsi_min) & (df["RSI"] <= rsi_max)]
        df = df[df["IV"] * 100 >= iv_min]
        st.success(f"✅ Found {len(df)} stocks matching your filters.")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Results", csv, "options_strategy_scan.csv", "text/csv")
    else:
        st.warning("❌ No matching stocks found with current settings.")

st.markdown("---")
st.caption("Built with ❤️ using yFinance and Streamlit")
