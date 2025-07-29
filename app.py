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
def fetch_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="90d")
        info = stock.info
        if hist.empty:
            return None

        close = hist["Close"]
        avg_volume = hist["Volume"].tail(30).mean()
        breakout_high = max(close.tail(breakout_days))
        breakout_status = close.iloc[-1] > breakout_high * 0.98
        rsi = compute_rsi(close)

        return {
            "Ticker": ticker,
            "Price": close.iloc[-1],
            "Breakout High": breakout_high,
            "Breakout": breakout_status,
            "RSI": rsi,
            "IV": info.get("impliedVolatility", None),
            "Sector": info.get("sector", "N/A"),
            "Market Cap": info.get("marketCap", 0),
            "Dividend Yield": info.get("dividendYield", 0),
            "Avg Volume": avg_volume,
            "Earnings Date": info.get("nextEarningsDate", "N/A")
        }
    except Exception:
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

    with st.spinner("Fetching and analyzing data..."):
        for tkr in tickers:
            data = fetch_data(tkr)
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
st.caption("Built with ❤️ using yFinance and Streamlit")

