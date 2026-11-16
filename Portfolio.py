import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import altair as alt
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

    # 3. Preis-Matrix aufbauen
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
                        first_trade = trades[trades["ISIN"] == isin]["Date_Norm"].min()
                        aligned = s_eur.reindex(all_dates).ffill()
                        aligned.loc[aligned.index < first_trade] = 0.0
                        price_matrix[isin] = aligned.fillna(price_matrix[isin])
                except Exception:
                    pass
        except Exception:
            pass

    for isin, cur_p in current_prices_dict.items():
        if isin in price_matrix.columns:
            price_matrix.loc[end_dt, isin] = cur_p

    daily_depot_value = (holdings * price_matrix).sum(axis=1)

    return pd.DataFrame({
        "Depotwert (€)": daily_depot_value,
        "Netto-Einzahlungen (€)": daily_deposits
    }, index=all_dates)

@st.cache_data(ttl=300)
def build_intraday_series(aktiv_df, current_prices_dict, net_deposits_today):
    """Lädt 15-Minuten-Kurse für den aktuellen Handelstag ('1 Tag')."""
    mapped = aktiv_df[aktiv_df["ISIN"].isin(ISIN_TO_TICKER)].copy()
    if mapped.empty:
        return pd.DataFrame()

    tickers = [ISIN_TO_TICKER[isin] for isin in mapped["ISIN"]]
    try:
        raw = yf.download(tickers, period="1d", interval="15m", progress=False, group_by="ticker")
        intraday_frames = {}
        for _, row in mapped.iterrows():
            isin = row["ISIN"]
            sym = ISIN_TO_TICKER[isin]
            qty = row["Bestand"]
            try:
                s = raw["Close"] if len(tickers) == 1 else raw[sym]["Close"]
                s = s.dropna()
                if not s.empty and s.iloc[-1] > 0:
                    s.index = pd.to_datetime(s.index).tz_localize(None)
                    scale = current_prices_dict[isin] / float(s.iloc[-1])
                    intraday_frames[isin] = s * scale * qty
            except Exception:
                pass

        if not intraday_frames:
            return pd.DataFrame()

        df_intra = pd.DataFrame(intraday_frames).ffill().bfill()
        unmapped_val = aktiv_df[~aktiv_df["ISIN"].isin(intraday_frames.keys())]["Aktueller Wert (€)"].sum()
        total_series = df_intra.sum(axis=1) + unmapped_val

        return pd.DataFrame({
            "Depotwert (€)": total_series,
            "Netto-Einzahlungen (€)": net_deposits_today
        })
    except Exception:
        return pd.DataFrame()

st.title("📊 Aktuelle Portfolio-Performance")

if st.button("🔄 Daten jetzt neu aus GDrive laden"):
    st.cache_data.clear()
    st.rerun()

df = load_transactions()

# --- 3. BESTAND & DURCHSCHNITTSKURS BERECHNEN ---
valid_types = ["Kauf", "Verkauf"]
trades = df[df["Typ"].isin(valid_types) & (df["ISIN"] != "-")].copy()

portfolio_list = []
for isin, group in trades.groupby("ISIN"):
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
    fx_rates = get_fx_rates()
    aktuelle_kurse = []
    current_prices_map = {}

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

        if preis_eur is None or pd.isna(preis_eur):
            preis_eur = einstand

        aktuelle_kurse.append(preis_eur)
        current_prices_map[isin] = preis_eur

    aktiv["Aktueller Kurs (€)"] = aktuelle_kurse
    aktiv["Aktueller Wert (€)"] = aktiv["Bestand"] * aktiv["Aktueller Kurs (€)"]
    aktiv["Gewinn / Verlust (€)"] = aktiv["Aktueller Wert (€)"] - aktiv["Netto_Invest"]
    aktiv["Performance (%)"] = aktiv.apply(
        lambda r: (r["Gewinn / Verlust (€)"] / r["Netto_Invest"] * 100) if r["Netto_Invest"] > 0 else 0.0, axis=1
    )

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

    st.markdown("---")
    st.subheader("📈 Portfolio-Wachstum (Historie)")

    # --- 6. ZEITRAUM-SCHALTER & LINIEN-CHART MIT JAHRES- & HALBJAHRESLINIEN ---
    timeframe = st.radio(
        "Zeitraum wählen:",
        ["Gesamte Zeit", "1 Jahr", "1 Monat", "1 Tag"],
        horizontal=True
    )

    history_df = build_history_series(df, current_prices_map)

    if timeframe == "1 Tag":
        net_dep_today = float(history_df["Netto-Einzahlungen (€)"].iloc[-1]) if not history_df.empty else 0.0
        intra_df = build_intraday_series(aktiv, current_prices_map, net_dep_today)
        plot_df = intra_df[["Depotwert (€)"]] if not intra_df.empty else history_df.tail(2)[["Depotwert (€)"]]
        show_year_guides = False
    else:
        end_date = history_df.index.max()
        if timeframe == "1 Monat":
            start_date = end_date - timedelta(days=30)
            show_year_guides = False
        elif timeframe == "1 Jahr":
            start_date = end_date - timedelta(days=365)
            show_year_guides = True
        else:
            start_date = history_df.index.min()
            show_year_guides = True

        plot_df = history_df[history_df.index >= start_date]

    if not plot_df.empty:
        chart_source = plot_df.reset_index().rename(columns={"index": "Datum"})
        chart_long = chart_source.melt("Datum", var_name="Kennzahl", value_name="Betrag (€)")

        # X-Achse: Bei Gesamte Zeit / 1 Jahr nur Jahreszahlen ohne Monatsangabe
        if show_year_guides:
            x_axis = alt.X(
                "Datum:T",
                title=None,
                axis=alt.Axis(
                    format="%Y",
                    tickCount="year",
                    grid=False,
                    labelAngle=0
                )
            )
        else:
            x_axis = alt.X(
                "Datum:T",
                title=None,
                axis=alt.Axis(
                    format="%d.%m. %H:%M" if timeframe == "1 Tag" else "%d.%m.%Y",
                    grid=True
                )
            )

        lines = alt.Chart(chart_long).mark_line(strokeWidth=2.2).encode(
            x=x_axis,
            y=alt.Y("Betrag (€):Q", title="Betrag (€)", scale=alt.Scale(zero=(timeframe == "Gesamte Zeit"))),
            color=alt.Color(
                "Kennzahl:N",
                scale=alt.Scale(
                    domain=["Depotwert (€)", "Netto-Einzahlungen (€)"],
                    range=["#00CC96", "#636EFA"]
                ),
                legend=alt.Legend(orient="bottom", title=None)
            ),
            tooltip=[
                alt.Tooltip("Datum:T", title="Datum", format="%d.%m.%Y" if timeframe != "1 Tag" else "%d.%m.%Y %H:%M"),
                alt.Tooltip("Kennzahl:N", title="Kategorie"),
                alt.Tooltip("Betrag (€):Q", title="Wert", format=",.2f")
            ]
        )

        # Vertikale Orientierungslinien bei 1.1. und 1.7. jeden Jahres
        if show_year_guides:
            min_dt = chart_source["Datum"].min()
            max_dt = chart_source["Datum"].max()
            years = range(min_dt.year, max_dt.year + 1)

            jan_dates = [pd.Timestamp(year=y, month=1, day=1) for y in years if min_dt <= pd.Timestamp(year=y, month=1, day=1) <= max_dt]
            jul_dates = [pd.Timestamp(year=y, month=7, day=1) for y in years if min_dt <= pd.Timestamp(year=y, month=7, day=1) <= max_dt]

            layers = [lines]

            if jan_dates:
                jan_df = pd.DataFrame({"
