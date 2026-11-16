import streamlit as st
import pandas as pd
import yfinance as yf

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
@st.cache_data(ttl=300)  # Aktualisiert automatisch alle 5 Minuten
def load_transactions():
    url = st.secrets["SHEET_CSV_URL"]
    # Deutsches Zahlenformat (Komma als Dezimaltrennzeichen, Punkt als Tausender) direkt parsen
    df = pd.read_csv(url, decimal=",", thousands=".")
    return df

# Mapping deiner WKNs zu Yahoo-Finance-Tickern (EUR-Kurse von Xetra/Tradegate)
WKN_TO_TICKER = {
    "A3EU6F": "NOV.DE",   # Novo-Nordisk B
    "531370": "AFX.DE",   # Carl Zeiss Meditec
    "645290": "NEM.DE",   # Nemetschek
    "716460": "SAP.DE",   # SAP SE
    "A1JX4P": "4S0.DE",   # ServiceNow
    "A0YA2M": "VRSK",     # Verisk Analytics (ggf. .DE prüfen)
    "A0J2R1": "WKL.AS",   # Wolters Kluwer
    "853888": "OR.PA",    # L'Oreal
    "855178": "KMB",      # Kimberly-Clark
    "A42D4F": "A42D4F.SG",# Space Exploration Tech
    "859892": "TER",      # Teradyne
    "938914": "AIR.DE",   # Airbus
    "927079": "ILMN",     # Illumina
    "852062": "PG",       # Procter & Gamble
    "929198": "UPS",      # UPS
    # Weitere WKNs aus deinem Bestand lassen sich hier beliebig ergänzen
}

st.title("📊 Aktuelle Portfolio-Performance")

if st.button("🔄 Daten jetzt neu aus GDrive laden"):
    st.cache_data.clear()
    st.rerun()

df = load_transactions()

# --- 3. BESTAND & DURCHSCHNITTSKURS BERECHNEN ---
trades = df[df["Typ"].isin(["Kauf", "Verkauf"])].copy()
trades["Signed_Qty"] = trades.apply(lambda r: r["Stückzahl"] if r["Typ"] == "Kauf" else -r["Stückzahl"], axis=1)
trades["Signed_Val"] = trades.apply(lambda r: r["Gesamtwert"] if r["Typ"] == "Kauf" else -r["Gesamtwert"], axis=1)

# Gruppieren nach WKN und Name
portfolio = trades.groupby(["WKN", "Name"], as_index=False).agg(
    Bestand=("Signed_Qty", "sum"),
    Netto_Invest=("Signed_Val", "sum")
)

# Nur Positionen behalten, die aktuell noch im Depot liegen (> 0 Stück)
aktiv = portfolio[portfolio["Bestand"] > 0.001].copy()
aktiv["Einstandskurs (€)"] = aktiv["Netto_Invest"] / aktiv["Bestand"]

# --- 4. AKTUELLE KURSE ABRUFEN ---
aktuelle_kurse = []
for wkn in aktiv["WKN"]:
    ticker_symbol = WKN_TO_TICKER.get(str(wkn).strip())
    if ticker_symbol:
        try:
            hist = yf.Ticker(ticker_symbol).history(period="1d")
            preis = hist["Close"].iloc[-1] if not hist.empty else None
        except Exception:
            preis = None
    else:
        preis = None
    aktuelle_kurse.append(preis)

aktiv["Aktueller Kurs (€)"] = aktuelle_kurse
aktiv["Aktueller Wert (€)"] = aktiv["Bestand"] * aktiv["Aktueller Kurs (€)"]
aktiv["Gewinn / Verlust (€)"] = aktiv["Aktueller Wert (€)"] - aktiv["Netto_Invest"]
aktiv["Performance (%)"] = (aktiv["Gewinn / Verlust (€)"] / aktiv["Netto_Invest"]) * 100

# --- 5. KPI-ÜBERSICHT & TABELLE ---
gesamt_invest = aktiv["Netto_Invest"].sum()
gesamt_wert = aktiv["Aktueller Wert (€)"].sum()
gesamt_gv = gesamt_wert - gesamt_invest
gesamt_perf = (gesamt_gv / gesamt_invest * 100) if gesamt_invest > 0 else 0

col1, col2, col3 = st.columns(3)
col1.metric("Aktueller Depotwert", f"{gesamt_wert:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
col2.metric("Investiertes Kapital", f"{gesamt_invest:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
col3.metric("Gesamt-Performance", f"{gesamt_gv:,.2f} €", f"{gesamt_perf:+.2f} %")

st.dataframe(
    aktiv[["Name", "WKN", "Bestand", "Einstandskurs (€)", "Aktueller Kurs (€)", "Aktueller Wert (€)", "Gewinn / Verlust (€)", "Performance (%)"]],
    use_container_width=True,
    hide_index=True
)
