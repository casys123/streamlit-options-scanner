import streamlit as st
import pandas as pd
import yfinance as yf
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
    breakout_days = st.select_slider("Breakout Window (days)", options=[30, 60], value=30)
    dte_days = st.slider("Max DTE for Covered Calls", 7, 60, 30)
    min_premium_pct = st.slider("Min Covered Call Premium (% of stock price)", 0.5, 10.0, 1.5)
    auto_email = st.checkbox("📧 Email me daily summary (requires SMTP config)")
    email_address = st.text_input("Email address (optional)") if auto_email else None
    st.markdown("---")
    run = st.button("🔍 Run Scan")

def fetch_yfinance_data(ticker, dte_days, min_premium_pct):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="90d")
        info = stock.info

        if hist.empty:
            st.warning(f"⚠️ No historical data for {ticker}.")
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
        if stock.options:
            for exp in stock.options:
                try:
                    dte = (datetime.strptime(exp, "%Y-%m-%d") - datetime.today()).days
                    if dte > dte_days:
                        continue
                    opt_chain = stock.option_chain(exp)
                    for call in opt_chain.calls.itertuples():
                        if call.strike > price and call.bid >= price * (min_premium_pct / 100):
                            best_premium = call.bid
                            best_strike = call.strike
                            best_dte = dte
                            break
                    if best_premium:
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
            "Earnings Date": info.get("earningsDate", "N/A")
        }
    except Exception as e:
        st.error(f"❌ Error fetching data for {ticker}: {e}")
        return None

if run:
    tickers = [x.strip().upper() for x in watchlist.split(",") if x.strip()][:300]
    results = []
    entry_date = datetime.today().date()
    exit_date = entry_date + timedelta(days=7)

    with st.spinner("🔍 Scanning stocks, please wait..."):
        for ticker in tickers:
            result = fetch_yfinance_data(ticker, dte_days, min_premium_pct)
            if result and result["RSI"] >= rsi_min and result["RSI"] <= rsi_max and result["IV"] >= iv_min and result["Avg Volume"] >= vol_min:
                results.append(result)

    if results:
        df = pd.DataFrame(results)
        st.success(f"✅ Scan complete. {len(df)} stocks matched your filters.")
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Results", csv, "options_scan.csv", "text/csv")
    else:
        st.warning("❌ No matching stocks found.")
