import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import random

# Support both fast-flights v3.x and v2.x
FAST_FLIGHTS_AVAILABLE = False
FF_VERSION = None
IMPORT_ERROR_MSG = ""

try:
    from fast_flights import FlightQuery, Passengers, create_query, get_flights
    FAST_FLIGHTS_AVAILABLE = True
    FF_VERSION = 3
except ImportError:
    try:
        from fast_flights import FlightData, Passengers, create_filter, get_flights
        FAST_FLIGHTS_AVAILABLE = True
        FF_VERSION = 2
    except Exception as e:
        IMPORT_ERROR_MSG = str(e)

st.set_page_config(
    page_title="RMO ⇄ NRW Deal Radar (One-Way Mix)",
    page_icon="✈️",
    layout="wide"
)

# --- KONFIGURATION ---
AIRPORT_MD = "RMO"  # Chișinău
AIRPORTS_DE = ["DTM", "CGN", "DUS"]

# Typische Direktflug-Tage (0=Mo, 1=Di, 2=Mi, 3=Do, 4=Fr, 5=Sa, 6=So)
SCHEDULES_DE_TO_RMO = {
    "DTM": [1, 3, 5, 6],    # Wizz Air
    "CGN": [0, 2, 4, 5, 6], # Wizz Air / Eurowings
    "DUS": [1, 3, 4, 6],    # HiSky / FlyOne
}
SCHEDULES_RMO_TO_DE = {
    "DTM": [1, 3, 5, 6],
    "CGN": [0, 2, 4, 5, 6],
    "DUS": [1, 3, 4, 6],
}

# --- HELPER: ZEIT-PARSER ---
def parse_time_str(time_val):
    if not time_val:
        return None
    try:
        t_clean = str(time_val).strip()
        # Handle "14:20", "14:20:00", etc.
        parts = t_clean.split(":")
        if len(parts) >= 2:
            hour = int("".join(c for c in parts[0] if c.isdigit()))
            minute = int("".join(c for c in parts[1][:2] if c.isdigit()))
            return time(hour, minute)
    except Exception:
        pass
    return None

# --- HELPER: DEMO-FLÜGE GENERATOR ---
def generate_demo_oneway_data(months: int = 2):
    today = datetime.now().date()
    end_date = today + timedelta(days=months * 30)
    
    out_flights = []
    in_flights = []
    
    # Bekannte typische Flugzeiten
    sample_profiles_to_md = [
        ("CGN", "Wizz Air", 24, "22:15", "02:30", True),  # Zu spät (wird gefiltert)
        ("CGN", "Eurowings", 64, "06:15", "10:05", True), # Früher Flug
        ("DTM", "Wizz Air", 29, "14:30", "18:15", True),  # Gute humane Flugzeit
        ("DUS", "HiSky", 75, "10:45", "14:30", True),     # Nachmittag
        ("DUS", "FlyOne", 59, "15:10", "19:00", True),    # Vor 19:30
    ]
    
    sample_profiles_to_de = [
        ("CGN", "Wizz Air", 29, "06:00", "07:55", True),
        ("DTM", "Wizz Air", 22, "18:45", "20:30", True),
        ("DUS", "HiSky", 79, "07:30", "09:30", True),
        ("DUS", "FlyOne", 49, "11:00", "13:00", True),
    ]
    
    for offset in range(3, (end_date - today).days):
        cur_date = today + timedelta(days=offset)
        # Hinflüge (DE -> MD)
        for de_ap, airline, base_p, dep_t, arr_t, is_dir in sample_profiles_to_md:
            if cur_date.weekday() in SCHEDULES_DE_TO_RMO.get(de_ap, []):
                p = base_p + random.choice([-5, 0, 5, 12, 25])
                out_flights.append({
                    "date": cur_date,
                    "origin": de_ap,
                    "dest": AIRPORT_MD,
                    "airline": airline,
                    "price": p,
                    "dep_time": dep_t,
                    "arr_time": arr_t,
                    "stops": "Direct" if is_dir else "1 Stop",
                    "link": f"https://www.google.com/travel/flights?q=Flights%20to%20{AIRPORT_MD}%20from%20{de_ap}%20on%20{cur_date}"
                })
        # Rückflüge (MD -> DE)
        for de_ap, airline, base_p, dep_t, arr_t, is_dir in sample_profiles_to_de:
            if cur_date.weekday() in SCHEDULES_RMO_TO_DE.get(de_ap, []):
                p = base_p + random.choice([-4, 0, 8, 15, 30])
                in_flights.append({
                    "date": cur_date,
                    "origin": AIRPORT_MD,
                    "dest": de_ap,
                    "airline": airline,
                    "price": p,
                    "dep_time": dep_t,
                    "arr_time": arr_t,
                    "stops": "Direct" if is_dir else "1 Stop",
                    "link": f"https://www.google.com/travel/flights?q=Flights%20to%20{de_ap}%20from%20{AIRPORT_MD}%20on%20{cur_date}"
                })
                
    return out_flights, in_flights

# --- HELPER: LIVE ONE-WAY SCANNER ---
def scan_live_oneway(origin: str, dest: str, scan_date: str):
    found = []
    try:
        if FF_VERSION == 3:
            query = create_query(
                flights=[FlightQuery(date=scan_date, from_airport=origin, to_airport=dest)],
                trip="one-way",
                seat="economy",
                passengers=Passengers(adults=1),
                currency="EUR"
            )
            res = get_flights(query)
        else:
            filter_obj = create_filter(
                flight_data=[FlightData(date=scan_date, from_airport=origin, to_airport=dest)],
                trip="one-way",
                seat="economy",
                passengers=Passengers(adults=1),
            )
            res = get_flights(filter_obj, currency="EUR")
            
        flight_items = res.flights if hasattr(res, "flights") else (res if isinstance(res, list) else [])
        
        for fl in flight_items:
            # Preis
            raw_p = getattr(fl, "price", None)
            digits = "".join(c for c in str(raw_p or "") if c.isdigit())
            price_val = int(digits) if digits else None
            
            # Airline
            if hasattr(fl, "airlines") and fl.airlines:
                airline_name = ", ".join(fl.airlines) if isinstance(fl.airlines, list) else str(fl.airlines)
            else:
                airline_name = getattr(fl, "name", "Airline")
                
            # Stops
            stops_val = getattr(fl, "stops", 0)
            stops_label = "Direct" if (stops_val == 0 or stops_val is None) else f"{stops_val} Stop(s)"
            
            # Zeiten
            dep_time_str = getattr(fl, "departure_time", None) or getattr(fl, "dep_time", "")
            arr_time_str = getattr(fl, "arrival_time", None) or getattr(fl, "arr_time", "")
            
            if price_val and price_val > 0:
                found.append({
                    "date": datetime.strptime(scan_date, "%Y-%m-%d").date(),
                    "origin": origin,
                    "dest": dest,
                    "airline": airline_name,
                    "price": price_val,
                    "dep_time": str(dep_time_str) if dep_time_str else "--:--",
                    "arr_time": str(arr_time_str) if arr_time_str else "--:--",
                    "stops": stops_label,
                    "link": f"https://www.google.com/travel/flights?q=Flights%20to%20{dest}%20from%20{origin}%20on%20{scan_date}"
                })
    except Exception:
        pass
    return found

# --- KOMBINIER-LOGIK (MIX & MATCH) ---
def build_deal_matrix(
    outbound_pool,
    inbound_pool,
    main_direction: str,
    min_days: int,
    max_days: int,
    max_total_price: int,
    filter_late_rmo: bool,
    max_rmo_arr_hour: int,
    max_rmo_arr_min: int
):
    combos = []
    cutoff_time = time(max_rmo_arr_hour, max_rmo_arr_min)
    
    # Bestimme, welcher Pool der Hinflug und welcher der Rückflug ist
    # main_direction = "Start DE" -> Hinflug ist DE->MD, Rückflug ist MD->DE
    # main_direction = "Start MD" -> Hinflug ist MD->DE, Rückflug ist DE->MD
    
    first_legs = outbound_pool if main_direction == "Start DE" else inbound_pool
    second_legs = inbound_pool if main_direction == "Start DE" else outbound_pool
    
    for leg1 in first_legs:
        # Falls Flug nach Kischinau geht: Zeitfilter prüfen
        if filter_late_rmo and leg1["dest"] == AIRPORT_MD:
            arr_t = parse_time_str(leg1["arr_time"])
            if arr_t and arr_t > cutoff_time:
                continue  # Zu späte Landung in Kischinau!
                
        for leg2 in second_legs:
            # Falls Rückflug nach Kischinau geht: Zeitfilter prüfen
            if filter_late_rmo and leg2["dest"] == AIRPORT_MD:
                arr_t = parse_time_str(leg2["arr_time"])
                if arr_t and arr_t > cutoff_time:
                    continue
                    
            stay_days = (leg2["date"] - leg1["date"]).days
            if min_days <= stay_days <= max_days:
                total_p = leg1["price"] + leg2["price"]
                if total_p <= max_total_price:
                    # Gabelflug / Mix erkennen
                    is_mixed_airports = (leg1["origin"] != leg2["dest"]) if main_direction == "Start DE" else (leg1["dest"] != leg2["origin"])
                    route_summary = f"{leg1['origin']} ➔ {leg1['dest']} | {leg2['origin']} ➔ {leg2['dest']}"
                    
                    combos.append({
                        "Direction": "🇩🇪 ➔ 🇲🇩 (Start DE)" if main_direction == "Start DE" else "🇲🇩 ➔ 🇩🇪 (Start MD)",
                        "Route": route_summary,
                        "Airport DE Out": leg1["origin"] if main_direction == "Start DE" else leg1["dest"],
                        "Airport DE In": leg2["dest"] if main_direction == "Start DE" else leg2["origin"],
                        "Is Mix": "🔀 Mix" if is_mixed_airports else "Direct Return",
                        "Outbound Date": leg1["date"].strftime("%a, %d.%m.%Y"),
                        "Outbound Airline": f"{leg1['airline']} ({leg1['dep_time']} ➔ {leg1['arr_time']})",
                        "Return Date": leg2["date"].strftime("%a, %d.%m.%Y"),
                        "Return Airline": f"{leg2['airline']} ({leg2['dep_time']} ➔ {leg2['arr_time']})",
                        "Duration": f"{stay_days} Days",
                        "Total Price (€)": total_p,
                        "Price Split": f"{leg1['price']}€ + {leg2['price']}€",
                        "Link Out": leg1["link"],
                        "Link Back": leg2["link"],
                        "SortDate": leg1["date"]
                    })
                    
    df = pd.DataFrame(combos)
    if not df.empty:
        df = df.sort_values(by=["Total Price (€)", "SortDate"]).drop_duplicates(
            subset=["Route", "Outbound Date", "Return Date", "Total Price (€)"]
        )
    return df

# --- UI & SIDEBAR ---
st.title("✈️ Smart NRW ⇄ Chișinău Deal Radar")
st.markdown(
    "Kombiniert **unabhängige Einzelflüge** über **Köln (CGN)**, **Düsseldorf (DUS)** und **Dortmund (DTM)** "
    "zu den günstigsten Hin- und Rückreise-Paketen (**≤ 100 €**, 3–7 Tage Aufenthalt)."
)

with st.sidebar:
    st.header("⚙️ Einstellungen & Filter")
    data_mode = st.radio(
        "Modus",
        ["Demo-Vorschau (Sofort)", "Live Scan (Google Flights)"]
    )
    
    max_price = st.slider("Max. Gesamtpreis Hin+Zurück (€)", min_value=30, max_value=150, value=100, step=5)
    steal_threshold = st.slider("🔥 'Super-Deal' Alarmgrenze (€)", min_value=25, max_value=75, value=50, step=5)
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        min_days = st.number_input("Min. Tage", min_value=2, max_value=7, value=3)
    with col_d2:
        max_days = st.number_input("Max. Tage", min_value=3, max_value=14, value=7)
        
    airport_filter = st.multiselect(
        "Deutsche Flughäfen erlauben",
        AIRPORTS_DE,
        default=AIRPORTS_DE,
        help="Dortmund (DTM), Köln (CGN) und Düsseldorf (DUS)"
    )
    
    direction_choice = st.radio(
        "Startpunkt",
        ["Beide Richtungen", "🇩🇪 Start in Deutschland", "🇲🇩 Start in Chișinău"]
    )
    
    st.divider()
    st.subheader("🕒 Flugzeiten & Landeschutz")
    filter_late = st.checkbox(
        "Keine späte Landung in Kischinau",
        value=True,
        help="Sortiert Flüge aus, die planmäßig nach 19:30 Uhr in Chișinău (RMO) landen (z. B. die 02:30 Uhr Nachtflüge)."
    )
    cutoff_hour = st.slider("Späteste Landezeit in RMO", min_value=12, max_value=23, value=19)
    cutoff_min = 30
    st.caption(f"Aktives Limit: Landung in RMO maximal bis **{cutoff_hour:02d}:{cutoff_min:02d} Uhr**.")
    
    if data_mode == "Live Scan (Google Flights)":
        st.divider()
        months_to_scan = st.slider("Horizont (Monate im Voraus)", 1, 3, 1)
        run_live = st.button("🚀 Fast Live Scan starten", type="primary", use_container_width=True)
    else:
        run_live = False

# --- DATEN HOLEN & KOMBINIEREN ---
if data_mode == "Demo-Vorschau (Sofort)":
    raw_out, raw_in = generate_demo_oneway_data(months=2)
else:
    if not FAST_FLIGHTS_AVAILABLE:
        st.error(f"Konnte `fast-flights` nicht laden: {IMPORT_ERROR_MSG}")
        st.stop()
        
    if run_live:
        today = datetime.now().date()
        total_days = months_to_scan * 30
        
        scanned_out = []
        scanned_in = []
        
        # Erstelle schlanke Suchliste nur für Wochentage mit Direktflügen
        tasks_out = []
        tasks_in = []
        for ap in airport_filter:
            for offset in range(3, total_days):
                d = today + timedelta(days=offset)
                if d.weekday() in SCHEDULES_DE_TO_RMO.get(ap, []):
                    tasks_out.append((ap, AIRPORT_MD, d.strftime("%Y-%m-%d")))
                if d.weekday() in SCHEDULES_RMO_TO_DE.get(ap, []):
                    tasks_in.append((AIRPORT_MD, ap, d.strftime("%Y-%m-%d")))
                    
        total_tasks = len(tasks_out) + len(tasks_in)
        p_bar = st.progress(0)
        s_text = st.empty()
        c = 0
        
        # 1. Hinflüge scannen
        for orig, dst, d_str in tasks_out:
            c += 1
            p_bar.progress(c / total_tasks)
            s_text.text(f"[{c}/{total_tasks}] Scanne Einzelflug {orig} ➔ {dst} am {d_str}...")
            scanned_out.extend(scan_live_oneway(orig, dst, d_str))
            
        # 2. Rückflüge scannen
        for orig, dst, d_str in tasks_in:
            c += 1
            p_bar.progress(c / total_tasks)
            s_text.text(f"[{c}/{total_tasks}] Scanne Einzelflug {orig} ➔ {dst} am {d_str}...")
            scanned_in.extend(scan_live_oneway(orig, dst, d_str))
            
        p_bar.empty()
        s_text.empty()
        st.session_state["raw_out"] = scanned_out
        st.session_state["raw_in"] = scanned_in
        
    raw_out = st.session_state.get("raw_out", [])
    raw_in = st.session_state.get("raw_in", [])

# Kombiniere zu Gesamtangeboten
df_list = []
if raw_out or raw_in:
    if direction_choice in ["Beide Richtungen", "🇩🇪 Start in Deutschland"]:
        df_de = build_deal_matrix(
            raw_out, raw_in, "Start DE", min_days, max_days, max_price, filter_late, cutoff_hour, cutoff_min
        )
        if not df_de.empty:
            df_list.append(df_de)
            
    if direction_choice in ["Beide Richtungen", "🇲🇩 Start in Chișinău"]:
        df_md = build_deal_matrix(
            raw_out, raw_in, "Start MD", min_days, max_days, max_price, filter_late, cutoff_hour, cutoff_min
        )
        if not df_md.empty:
            df_list.append(df_md)

final_df = pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

# Filter auf gewählte DE-Flughäfen anwenden
if not final_df.empty:
    final_df = final_df[
        final_df["Airport DE Out"].isin(airport_filter) & final_df["Airport DE In"].isin(airport_filter)
    ]

# --- ERGEBNIS-ANZEIGE ---
if final_df.empty:
    if data_mode == "Live Scan (Google Flights)" and not run_live:
        st.info("👈 Wähle deine Filter in der Sidebar und klicke auf **🚀 Fast Live Scan starten**.")
    else:
        st.warning(f"Keine passenden Kombinationen unter {max_price} € gefunden (prüfe ggf. das Ankunftszeit-Limit).")
else:
    cheapest = final_df["Total Price (€)"].min()
    steals = final_df[final_df["Total Price (€)"] <= steal_threshold]
    mixes_count = len(final_df[final_df["Is Mix"] == "🔀 Mix"])
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Günstigster Trip gesamt", f"{cheapest} €")
    m2.metric(f"Angebote (≤ {max_price} €)", len(final_df))
    m3.metric(f"🔥 Super-Deals (≤ {steal_threshold} €)", len(steals))
    m4.metric("🔀 Gabelflug-Kombis", mixes_count)
    
    st.divider()
    
    # Top 3 Schnäppchen als Cards
    if not steals.empty:
        st.subheader(f"🔥 Top Schnäppchen (Unter {steal_threshold} € Hin & Zurück)")
        cols = st.columns(min(len(steals), 3))
        for idx, (_, row) in enumerate(steals.head(3).iterrows()):
            with cols[idx]:
                st.success(
                    f"### {row['Total Price (€)']} € ({row['Price Split']})\n"
                    f"**{row['Direction']}** — *{row['Is Mix']}*\n\n"
                    f"🛫 **Hin:** {row['Outbound Date']}\n"
                    f"└ {row['Outbound Airline']}\n\n"
                    f"🛬 **Rück:** {row['Return Date']} ({row['Duration']})\n"
                    f"└ {row['Return Airline']}\n\n"
                    f"[👉 Hinflug buchen]({row['Link Out']}) | [👉 Rückflug buchen]({row['Link Back']})"
                )
        st.divider()

    # Tabs
    tab_all, tab_mixes = st.tabs([
        f"Alle Flugpakete ({len(final_df)})", 
        f"Nur Gabelflüge / Mixe ({mixes_count})"
    ])
    
    show_cols = [
        "Direction", "Is Mix", "Route", "Total Price (€)", "Price Split", 
        "Outbound Date", "Outbound Airline", "Return Date", "Return Airline", 
        "Duration", "Link Out", "Link Back"
    ]
    
    with tab_all:
        st.dataframe(
            final_df[show_cols],
            column_config={
                "Link Out": st.column_config.LinkColumn("Hinflug", display_text="Flug 1 ↗"),
                "Link Back": st.column_config.LinkColumn("Rückflug", display_text="Flug 2 ↗"),
                "Total Price (€)": st.column_config.NumberColumn("Gesamtpreis", format="%d €")
            },
            hide_index=True,
            use_container_width=True
        )
        
    with tab_mixes:
        mix_only = final_df[final_df["Is Mix"] == "🔀 Mix"]
        st.dataframe(
            mix_only[show_cols],
            column_config={
                "Link Out": st.column_config.LinkColumn("Hinflug", display_text="Flug 1 ↗"),
                "Link Back": st.column_config.LinkColumn("Rückflug", display_text="Flug 2 ↗"),
                "Total Price (€)": st.column_config.NumberColumn("Gesamtpreis", format="%d €")
            },
            hide_index=True,
            use_container_width=True
                    )
        
