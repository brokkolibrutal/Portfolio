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
    df["Gesamtwert_num"] = df["Gesamtwert"].apply(clean_number) if "Gesamtwert" in df.columns else 0.0
    return df

# Vollständiges Mapping deiner WKNs zu Euro-Tickern (Xetra/Tradegate/US)
WKN_TO_TICKER = {
    "531370": "AFX.DE",   # Carl Zeiss Meditec
    "633835": "SJM",      # J.M. Smucker
    "645290": "NEM.DE",   # Nemetschek
    "716460": "SAP.DE",   # SAP SE
    "850501": "BMY",      # Bristol-Myers Squibb
    "850628": "JPM",      # JPMorgan Chase
    "852062": "PG",       # Procter & Gamble
    "853862": "GIS",      # General Mills
    "853888": "OR.PA",    # L'Oreal
    "854161": "ADM",      # Archer-Daniels-Midland
    "A3EU6F": "NOV.DE",   # Novo-Nordisk B
    "A1JX4P": "4S0.DE",   # ServiceNow
    "A0YA2M": "VRSK",     # Verisk Analytics
    "A0J2R1": "WKL.AS",   # Wolters Kluwer
    "A42D4F": "A42D4F.SG",# Space Exploration Tech
    "859892": "TER",      # Teradyne
    "938914": "AIR.DE",   # Airbus
    "927079": "ILMN",     # Illumina
    "929198": "UPS",      # UPS
}

st.title("📊 Aktuelle Portfolio-Performance")

if st.button("🔄 Daten jetzt neu aus GDrive laden"):
    st.cache_data.clear()
    st.rerun()

df = load_transactions()

# --- 3. BESTAND & DURCHSCHNITTSKURS BERECHNEN (GEWICHTETER DURSCHNITT) ---
trades = df[df["Typ"].isin(["Kauf", "Verkauf"])].copy()

# Wir berechnen den aktuellen Bestand pro WKN/Name iterativ oder über Aggregation
# Um realistische Einstandskurse bei Teilverkäufen zu haben:
portfolio_list = []
for (wkn, name), group in trades.groupby(["WKN", "Name"]):
    # Nach Datum sortieren, falls Datum vorhanden
    if "Datum" in group.columns:
        group = group.sort_values(by="Datum", ascending=True)
    
    bestand = 0.0
    investiert = 0.0
    
    for _, row in group.iterrows():
        stk = row["Stückzahl_num"]
        wert = row["Gesamtwert_num"]
        typ = row["Typ"]
        
        if typ == "Kauf":
            investiert += wert
            bestand += stk
        elif typ == "Verkauf":
            if bestand > 0:
                # Anteiligen Einstand herausrechnen
                avg_price = investiert / bestand if bestand > 0 else 0
                investiert -= (stk * avg_price)
            bestand -= stk
            
    if bestand > 0.001:
        einstandskurs = investiert / bestand
        portfolio_list.append({
            "WKN": str(wkn).strip(),
            "Name": name,
            "Bestand": bestand,
            "Netto_Invest": max(0.0, investiert),
            "Einstandskurs (€)": einstandskurs
        })

aktiv = pd.DataFrame(portfolio_list)

if not aktiv.empty:
    # --- 4. AKTUELLE KURSE ABRUFEN ---
    aktuelle_kurse = []
    for wkn in aktiv["WKN"]:
        ticker_symbol = WKN_TO_TICKER.get(wkn)
        preis = None
        if ticker_symbol:
            try:
                hist = yf.Ticker(ticker_symbol).history(period="5d")
                if not hist.empty:
                    preis = hist["Close"].iloc[-1]
            except Exception:
                preis = None
        aktuelle_kurse.append(preis)

    aktiv["Aktueller Kurs (€)"] = aktuelle_kurse
    
    # Falls US-Ticker in USD, einfache Annahme / Anzeige (oder direkt Wert berechnen)
    aktiv["Aktueller Wert (€)"] = aktiv["Bestand"] * aktiv["Aktueller Kurs (€)"].fillna(0)
    aktiv["Gewinn / Verlust (€)"] = aktiv["Aktueller Wert (€)"] - aktiv["Netto_Invest"]
    aktiv["Performance (%)"] = aktiv.apply(
        lambda r: (r["Gewinn / Verlust (€)"] / r["Netto_Invest"] * 100) if r["Netto_Invest"] > 0 else 0.0, axis=1
    )

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
else:
    st.info("Keine aktiven Positionen im Depot gefunden.")
