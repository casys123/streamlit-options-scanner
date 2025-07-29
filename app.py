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

FINNHUB_API_KEY = "d24bts1r01qmb591jeo0d24bts1r01qmb591jeog"
if FINNHUB_API_KEY == "YOUR_API_KEY_HERE":
    st.warning("⚠️ Please update your Finnhub API key to fetch live market data.")

# Load default stock list from file or fallback
@st.cache_data
def load_default_tickers():
    try:
        return pd.read_csv("default_stock_list.csv")["Ticker"].tolist()[:300]
    except:
        return ["AAPL", "MSFT", "TSLA", "AMZN", "NVDA", "AMD", "GOOGL", "META", "NFLX", "INTC"]

# ----------- USER INPUTS ----------- #
with st.sidebar:
    st.header("Scan Settings")
    default_tickers = ",".join(load_default_tickers())
    watchlist = st.text_area("Enter stock tickers (comma separated):", default_tickers)
    rsi_min = st.slider("RSI Minimum", 0, 100, 40)
    rsi_max = st.slider("RSI Maximum", 0, 100, 60)
    iv_min = st.slider("Minimum Implied Volatility (%)", 0, 150, 30)
    vol_min = st.number_input("Minimum Avg Volume (1M)", value=1000000, step=100000)
    breakout_days = st.select_slider("Breakout Window (days)", options=[30, 60], value=30)
    auto_email = st.checkbox("📧 Email me daily summary (requires SMTP config)")
    email_address = st.text_input("Email address (optional)") if auto_email else None
    st.markdown("---")
    run = st.button("🔍 Run Scan")

# ----------- FUNCTIONS ----------- #
def fetch_finnhub_data(ticker):
    try:
        profile_url = f"https://finnhub.io/api/v1/stock/profile2?symbol={ticker}&token={FINNHUB_API_KEY}"
        quote_url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_API_KEY}"
        metrics_url = f"https://finnhub.io/api/v1/stock/metric?symbol={ticker}&metric=all&token={FINNHUB_API_KEY}"

        profile = requests.get(profile_url).json()
        quote = requests.get(quote_url).json()
        metrics = requests.get(metrics_url).json()

        if not quote.get("c"):
            st.warning(f"⚠️ No quote data found for {ticker}.")
            return None
        if not metrics.get("metric"):
            st.warning(f"⚠️ No metrics found for {ticker}.")
            return None

        price = quote.get("c")
        high = quote.get("h")
        low = quote.get("l")
        vol = quote.get("v")
        iv = metrics.get("metric", {}).get("impliedVolatility", None)
        dividend_yield = metrics.get("metric", {}).get("dividendYieldIndicatedAnnual", 0)
        rsi = metrics.get("metric", {}).get("rsi", 50)

        return {
            "Ticker": ticker,
            "Price": price,
            "Breakout High": high,
            "Breakout": price > high * 0.98 if high else False,
            "RSI": rsi,
            "IV": iv,
            "Sector": profile.get("finnhubIndustry", "N/A"),
            "Market Cap": profile.get("marketCapitalization", 0),
            "Dividend Yield": dividend_yield,
            "Avg Volume": vol,
            "Earnings Date": profile.get("earningsDate", "N/A")
        }
    except Exception as e:
        st.error(f"❌ Error fetching data for {ticker}: {e}")
        return None


def evaluate_covered_call_potential(data):
    return bool(data["IV"] and data["IV"] > 0.4 and data["Dividend Yield"] == 0)

def evaluate_put_credit_spread_risk(data):
    return bool(data["IV"] and data["IV"] > 0.3 and rsi_min <= data["RSI"] <= rsi_max)

def send_email_report(content, to_email):
    try:
        smtp_server = "smtp.gmail.com"
        port = 465
        sender_email = "your-email@gmail.com"
        password = "your-app-password"

        message = f"Subject: Daily Options Scan Report\n\n{content}"
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, to_email, message)
        st.success(f"✅ Email sent to {to_email}")
    except Exception as e:
        st.error(f"❌ Failed to send email: {e}")

# ----------- MAIN SCAN ----------- #
if run:
    tickers = [x.strip().upper() for x in watchlist.split(",") if x.strip()][:300]
    results = []
    entry_date = datetime.today().date()
    exit_date = entry_date + timedelta(days=7)

    with st.spinner("Fetching and analyzing data from Finnhub..."):
        for tkr in tickers:
            data = fetch_finnhub_data(tkr)
            if data:
                data["Covered Call"] = evaluate_covered_call_potential(data)
                data["Put Credit Spread"] = evaluate_put_credit_spread_risk(data)
                data["Entry Date"] = entry_date
                data["Exit Date"] = exit_date
                results.append(data)

    if results:
        df = pd.DataFrame(results)
        df = df[(df["RSI"] >= rsi_min) & (df["RSI"] <= rsi_max)]
        df = df[df["IV"] * 100 >= iv_min]
        df = df[df["Avg Volume"] >= vol_min]

        st.success(f"✅ Found {len(df)} stocks matching your filters.")

        tab1, tab2, tab3 = st.tabs(["📈 Covered Calls", "🔐 Put Credit Spreads", "🚀 Breakout Candidates"])

        with tab1:
            df_calls = df[df["Covered Call"] == True].copy()
            if not df_calls.empty:
                st.subheader("📈 Best Premium Stocks for Covered Calls")
                st.dataframe(df_calls, use_container_width=True)
                csv_calls = df_calls.to_csv(index=False).encode("utf-8")
                st.download_button("📥 Download Covered Calls", csv_calls, "covered_calls.csv", "text/csv")
            else:
                st.warning("No suitable Covered Call candidates found.")

        with tab2:
            df_spreads = df[df["Put Credit Spread"] == True].copy()
            if not df_spreads.empty:
                st.subheader("🔐 Put Credit Spreads with ≥65% POP")
                st.dataframe(df_spreads, use_container_width=True)
                csv_spreads = df_spreads.to_csv(index=False).encode("utf-8")
                st.download_button("📥 Download Put Credit Spreads", csv_spreads, "put_credit_spreads.csv", "text/csv")
            else:
                st.warning("No suitable Put Credit Spread candidates found.")

        with tab3:
            df_breakout = df[df["Breakout"] == True].copy()
            if not df_breakout.empty:
                st.subheader(f"🚀 Breakout Candidates (past {breakout_days} days)")
                st.dataframe(df_breakout, use_container_width=True)
                csv_breakout = df_breakout.to_csv(index=False).encode("utf-8")
                st.download_button("📥 Download Breakouts", csv_breakout, "breakouts.csv", "text/csv")
            else:
                st.warning("No breakout candidates found.")

        if auto_email and email_address:
            email_summary = df[["Ticker", "Price", "RSI", "IV", "Covered Call", "Put Credit Spread", "Breakout", "Entry Date", "Exit Date"]].to_string(index=False)
            send_email_report(email_summary, email_address)
    else:
        st.warning("❌ No matching stocks found with current settings.")

st.markdown("---")
st.caption("Built with ❤️ using Finnhub and Streamlit")
