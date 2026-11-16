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
    if "ISIN" in df.columns:
        df["ISIN"] = df["ISIN"].astype(str).str.strip()
    return df

# Vollständiges ISIN-zu-Ticker-Mapping für deine Positionen
ISIN_TO_TICKER = {
    "CA05156X8504": "ACB",        # Aurora Cannabis
    "DE0005313704": "AFX.DE",     # Carl Zeiss Meditec
    "DE0006452907": "NEM.DE",     # Nemetschek
    "DE0007164600": "SAP.DE",     # SAP SE
    "DE000A0D9PT0": "MTX.DE",     # MTU Aero Engines
    "DK0062498333": "NOV.DE",     # Novo-Nordisk B (Xetra EUR)
    "FR0000120321": "OR.PA",      # L'Oreal (Euronext EUR)
    "KYG694511059": "PAX",        # Patria Investments
    "KYG875721634": "0700.HK",    # Tencent Holdings
    "NL0000235190": "AIR.DE",     # Airbus (Xetra EUR)
    "NL0000395903": "WKL.AS",     # Wolters Kluwer (Euronext EUR)
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
    """Holt aktuelle Wechselkurse (EUR zu USD/NOK/HKD/CAD) für saubere EUR-Bewertung."""
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

st.title("📊 Aktuelle Portfolio-Performance")

if st.button("🔄 Daten jetzt neu aus GDrive laden"):
    st.cache_data.clear()
    st.rerun()

df = load_transactions()

# --- 3. BESTAND & DURCHSCHNITTSKURS BERECHNEN (NACH ISIN) ---
trades = df[df["Typ"].isin(["Kauf", "Verkauf"]) & (df["ISIN"] != "-")].copy()

portfolio_list = []
for isin, group in trades.groupby("ISIN"):
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
                avg_price = investiert / bestand
                investiert -= (stk * avg_price)
            bestand -= stk

    if bestand > 0.001:
        einstandskurs = investiert / bestand
        # Aktuellsten Namen aus dem letzten Trade dieser ISIN nehmen
        name = group["Name"].iloc[-1]
        portfolio_list.append({
            "ISIN": isin,
            "Name": name,
            "Bestand": bestand,
            "Netto_Invest": max(0.0, investiert),
            "Einstandskurs (€)": einstandskurs
        })

aktiv = pd.DataFrame(portfolio_list)

if not aktiv.empty:
    # --- 4. AKTUELLE KURSE ABRUFEN & IN EUR UMRECHNEN ---
    fx_rates = get_fx_rates()
    aktuelle_kurse = []

    for _, row in aktiv.iterrows():
        isin = row["ISIN"]
        einstand = row["Einstandskurs (€)"]
        ticker_symbol = ISIN_TO_TICKER.get(isin)

        preis_eur = None
        if ticker_symbol:
            try:
                t = yf.Ticker(ticker_symbol)
                hist = t.history(period="5d")
                if not hist.empty:
                    raw_price = float(hist["Close"].iloc[-1])
                    currency = t.fast_info.get("currency", "EUR")
                    if currency in fx_rates and fx_rates[currency] > 0:
                        preis_eur = raw_price / fx_rates[currency]
                    else:
                        preis_eur = raw_price
            except Exception:
                preis_eur = None

        # Fallback auf Einstandskurs (z.B. bei nicht börsennotierten/illiquiden Werten)
        if preis_eur is None or pd.isna(preis_eur):
            preis_eur = einstand

        aktuelle_kurse.append(preis_eur)

    aktiv["Aktueller Kurs (€)"] = aktuelle_kurse
    aktiv["Aktueller Wert (€)"] = aktiv["Bestand"] * aktiv["Aktueller Kurs (€)"]
    aktiv["Gewinn / Verlust (€)"] = aktiv["Aktueller Wert (€)"] - aktiv["Netto_Invest"]
    aktiv["Performance (%)"] = aktiv.apply(
        lambda r: (r["Gewinn / Verlust (€)"] / r["Netto_Invest"] * 100) if r["Netto_Invest"] > 0 else 0.0, axis=1
    )

    # Alphabetisch nach Name sortieren
    aktiv = aktiv.sort_values(by="Name", ascending=True)

    # --- 5. KPI-ÜBERSICHT & TABELLE ---
    gesamt_invest = aktiv["Netto_Invest"].sum()
    gesamt_wert = aktiv["Aktueller Wert (€)"].sum()
    gesamt_gv = gesamt_wert - gesamt_invest
    gesamt_perf = (gesamt_gv / gesamt_invest * 100) if gesamt_invest > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Aktueller Depotwert", f"{gesamt_wert:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
    col2.metric("Investiertes Kapital", f"{gesamt_invest:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
    col3.metric("Gesamt-Performance", f"{gesamt_gv:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."), f"{gesamt_perf:+.2f} %")

    st.dataframe(
        aktiv[["Name", "ISIN", "Bestand", "Einstandskurs (€)", "Aktueller Kurs (€)", "Aktueller Wert (€)", "Gewinn / Verlust (€)", "Performance (%)"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Bestand": st.column_config.NumberColumn(format="%.2f"),
            "Einstandskurs (€)": st.column_config.NumberColumn(format="%.2f €"),
            "Aktueller Kurs (€)": st.column_config.NumberColumn(format="%.2f €"),
            "Aktueller Wert (€)": st.column_config.NumberColumn(format="%.2f €"),
            "Gewinn / Verlust (€)": st.column_config.NumberColumn(format="%+.2f €"),
            "Performance (%)": st.column_config.NumberColumn(format="%+.2f %%"),
        }
    )
else:
    st.info("Keine aktiven Positionen im Depot gefunden.")
