import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

st.set_page_config(page_title="Brokkoli Portfolio-Monitor", layout="wide")

# --- 1. PASSWORTSCHUTZ ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True

    st.title("🔒 Privater Portfolio-Bereich")
    pwd = st.text_input("Passwort eingeben:", type="password")
    if st.button("Anmelden"):
        if pwd == st.secrets["PORTFOLIO_PASSWORD"]:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Falsches Passwort.")
    return False

if not check_password():
    st.stop()

# --- 2. DATEN AUS GOOGLE SHEETS LADEN (OHNE API) ---
@st.cache_data(ttl=300)
def load_transactions():
    url = st.secrets["SHEET_CSV_URL"]
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip()

    def clean_number(val):
        if pd.isna(val):
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        val_str = str(val).strip()
        if val_str in ["-", "", "nan", "None"]:
            return 0.0
        val_str = val_str.replace(".", "").replace(",", ".")
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    df["Stückzahl_num"] = df["Stückzahl"].apply(clean_number) if "Stückzahl" in df.columns else 0.0
    df["Kurs_num"] = df["Kurs"].apply(clean_number) if "Kurs" in df.columns else 0.0
    df["Gesamtwert_num"] = df["Gesamtwert"].apply(clean_number) if "Gesamtwert" in df.columns else 0.0
    if "ISIN" in df.columns:
        df["ISIN"] = df["ISIN"].astype(str).str.strip()
    if "Datum" in df.columns:
        # Unterstützt sowohl YYYY-MM-DD als auch DD.MM.YYYY gemischt
        df["Datum"] = pd.to_datetime(df["Datum"], format="mixed", dayfirst=True, errors="coerce")
    return df

# Vollständiges ISIN-zu-Ticker-Mapping
ISIN_TO_TICKER = {
    "CA05156X8504": "ACB",        # Aurora Cannabis
    "DE0005313704": "AFX.DE",     # Carl Zeiss Meditec
    "DE0006452907": "NEM.DE",     # Nemetschek
    "DE0007164600": "SAP.DE",     # SAP SE
    "DE000A0D9PT0": "MTX.DE",     # MTU Aero Engines
    "DK0062498333": "NOV.DE",     # Novo-Nordisk B
    "FR0000120321": "OR.PA",      # L'Oreal
    "KYG694511059": "PAX",        # Patria Investments
    "KYG875721634": "0700.HK",    # Tencent Holdings
    "NL0000235190": "AIR.DE",     # Airbus
    "NL0000395903": "WKL.AS",     # Wolters Kluwer
    "NO0012470089": "TOM.OL",     # Tomra Systems
    "US0091581068": "APD",        # Air Products & Chemicals
    "US02079K1079": "GOOG",       # Alphabet C
    "US0231351067": "AMZN",       # Amazon.com
    "US0394831020": "ADM",        # Archer-Daniels-Midland
    "US1101221083": "BMY",        # Bristol-Myers Squibb
    "US1405011073": "CSWC",       # Capital Southwest
    "US18467V1098": "YOU",        # Clear Secure
    "US26853E1029": "EH",         # EHang Holdings
    "US3131483063": "AGM",        # Federal Agricultural Mortgage
    "US3703341046": "GIS",        # General Mills
    "US4523271090": "ILMN",       # Illumina
    "US46625H1005": "JPM",        # JPMorgan Chase
    "US4943681035": "KMB",        # Kimberly-Clark
    "US5738741041": "MRVL",       # Marvell Technology
    "US59522J1034": "MAA",        # Mid-America Apartment Communities
    "US6153691059": "MCO",        # Moody's
    "US6974351057": "PANW",       # Palo Alto Networks
    "US7010941042": "PH",         # Parker-Hannifin
    "US7427181091": "PG",         # Procter & Gamble
    "US81762P1021": "NOW",        # ServiceNow
    "US8288061091": "SPG",        # Simon Property Group
    "US8326964058": "SJM",        # J.M. Smucker
    "US84624L1061": "A42D4F.SG",  # Space Exploration Technologies A
    "US9113121068": "UPS",        # United Parcel Service 'B'
    "US92345Y1064": "VRSK",       # Verisk Analytics
    "US92826C8394": "V",          # Visa
    "US92936U1097": "WPC",        # W.P. Carey
}

@st.cache_data(ttl=300)
def get_fx_rates():
    rates = {"EUR": 1.0}
    pairs = {"USD": "EURUSD=X", "NOK": "EURNOK=X", "HKD": "EURHKD=X", "CAD": "EURCAD=X"}
    for curr, symbol in pairs.items():
        try:
            hist = yf.Ticker(symbol).history(period="5d")
            if not hist.empty:
                rates[curr] = float(hist["Close"].iloc[-1])
        except Exception:
            pass
    return rates

@st.cache_data(ttl=3600)
def build_history_series(df_input, current_prices_dict):
    """Berechnet die tägliche Entwicklung von Depotwert und Netto-Einzahlungen ab 2017."""
    df_all = df_input.dropna(subset=["Datum"]).copy()
    df_all = df_all.sort_values(by="Datum")

    end_dt = pd.Timestamp.today().normalize()
    start_dt = df_all["Datum"].min().normalize()
    all_dates = pd.date_range(start=start_dt, end=end_dt, freq="D")

    # 1. Netto-Einzahlungen (Einzahlung - Auszahlung)
    def calc_deposit(r):
        val = abs(r["Gesamtwert_num"])
        if r["Typ"] == "Einzahlung":
            return val
        elif r["Typ"] == "Auszahlung":
            return -val
        return 0.0

    df_all["Deposit_Flow"] = df_all.apply(calc_deposit, axis=1)
    daily_deposits = (
        df_all.groupby(df_all["Datum"].dt.normalize())["Deposit_Flow"]
        .sum()
        .reindex(all_dates, fill_value=0.0)
        .cumsum()
    )

    # 2. Täglicher Aktienbestand je ISIN
    trades = df_all[df_all["Typ"].isin(["Kauf", "Verkauf"]) & (df_all["ISIN"] != "-")].copy()
    trades["Signed_Qty"] = np.where(trades["Typ"] == "Kauf", trades["Stückzahl_num"], -trades["Stückzahl_num"])
    trades["Date_Norm"] = trades["Datum"].dt.normalize()

    holdings = (
        trades.pivot_table(index="Date_Norm", columns="ISIN", values="Signed_Qty", aggfunc="sum", fill_value=0.0)
        .reindex(all_dates, fill_value=0.0)
        .cumsum()
    )
    holdings = holdings.clip(lower=0.0)

    # 3. Preis-Matrix aufbauen (Trade-Kurse als Basis + Yahoo-Tageskurse ab Kaufdatum)
    trade_prices = trades.pivot_table(index="Date_Norm", columns="ISIN", values="Kurs_num", aggfunc="last")
    price_matrix = trade_prices.reindex(all_dates).ffill().fillna(0.0)

    mapped_isins = [isin for isin in holdings.columns if isin in ISIN_TO_TICKER]
    tickers = [ISIN_TO_TICKER[isin] for isin in mapped_isins]

    if tickers:
        try:
            raw_hist = yf.download(tickers, start=start_dt.strftime("%Y-%m-%d"), progress=False, group_by="ticker")
            for isin in mapped_isins:
                sym = ISIN_TO_TICKER[isin]
                try:
                    s = raw_hist["Close"] if len(tickers) == 1 else raw_hist[sym]["Close"]
                    s = s.dropna()
                    if not s.empty:
                        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
                        if isin in current_prices_dict and s.iloc[-1] > 0:
                            scale_to_eur = current_prices_dict[isin] / float(s.iloc[-1])
                            s_eur = s * scale_to_eur
                        else:
                            s_eur = s
                        # Nur ab dem ersten Kaufdatum füllen, damit vorher 0 steht
                        first_trade = trades[trades["ISIN"] == isin]["Date_Norm"].min()
                        aligned = s_eur.reindex(all_dates).
