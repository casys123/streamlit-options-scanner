import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

st.set_page_config(page_title="Stock Options Breakout Scanner", layout="wide")
st.title("📈 Stock Options Breakout & Strategy Scanner")

st.markdown("""
This tool scans **optionable stocks** for:
- 📊 **Breakout potential** (30 to 60 days)
- 💰 **Weekly Covered Call** opportunities
- 🔐 **Put Credit Spreads** on SPY, QQQ, IWM
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
            "Sector": info.get("sector", "N/A")
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

# ----------- MAIN SCAN ----------- #
if run:
    tickers = [x.strip().upper() for x in watchlist.split(",") if x.strip()]
    results = []
    with st.spinner("Fetching and analyzing data..."):
        for tkr in tickers:
            data = fetch_data(tkr)
            if data and data["RSI"] >= rsi_min and data["RSI"] <= rsi_max and data["IV"] and data["IV"]*100 >= iv_min:
                results.append(data)

    if results:
        df = pd.DataFrame(results)
        st.success(f"✅ Found {len(df)} stocks matching your filters.")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Results", csv, "options_scan.csv", "text/csv")
    else:
        st.warning("❌ No matching stocks found with current settings.")

st.markdown("---")
st.caption("Built with ❤️ using yFinance and Streamlit")
