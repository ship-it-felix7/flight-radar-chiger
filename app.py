import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import random

# Import fast_flights for live Google Flights scraping
try:
    from fast_flights import FlightData, Passengers, create_filter, get_flights
    FAST_FLIGHTS_AVAILABLE = True
except ImportError:
    FAST_FLIGHTS_AVAILABLE = False

st.set_page_config(
    page_title="RMO ⇄ DE Deal Radar",
    page_icon="✈️",
    layout="wide"
)

# --- CONFIGURATION & OPERATING SCHEDULES ---
AIRPORT_MD = "RMO"  # Official IATA code for Chișinău

# Typical direct flight operating weekdays (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun)
DIRECT_SCHEDULES = {
    "DTM": [1, 3, 5, 6],       # Wizz Air (typically Tue, Thu, Sat, Sun)
    "CGN": [0, 2, 4, 5, 6],    # Wizz Air / Eurowings (typically Mon, Wed, Fri, Sat, Sun)
    "DUS": [1, 3, 4, 6],       # HiSky / FlyOne (typically Tue, Thu, Fri, Sun)
}

# --- HELPER: MOCK DATA GENERATOR ---
def generate_demo_deals(max_price: int, min_days: int, max_days: int, months: int):
    deals = []
    today = datetime.now().date()
    end_date = today + timedelta(days=months * 30)
    
    airlines = [
        ("Wizz Air", "DTM", True, [34, 39, 44, 52, 68, 89]),
        ("Wizz Air", "CGN", True, [39, 45, 54, 65, 79, 95]),
        ("Eurowings", "CGN", True, [69, 78, 88, 99, 115]),
        ("HiSky", "DUS", True, [79, 89, 95, 110, 125]),
        ("FlyOne", "DUS", True, [64, 75, 85, 98, 120]),
    ]
    
    for _ in range(45):
        airline, de_airport, is_direct, price_pool = random.choice(airlines)
        dep_offset = random.randint(3, (end_date - today).days - max_days)
        dep_date = today + timedelta(days=dep_offset)
        duration = random.randint(min_days, max_days)
        ret_date = dep_date + timedelta(days=duration)
        
        direction = random.choice(["DE_TO_MD", "MD_TO_DE"])
        price = random.choice(price_pool)
        
        if price <= max_price:
            origin = de_airport if direction == "DE_TO_MD" else AIRPORT_MD
            destination = AIRPORT_MD if direction == "DE_TO_MD" else de_airport
            
            gf_link = (
                f"https://www.google.com/travel/flights?q=Flights%20to%20{destination}%20"
                f"from%20{origin}%20on%20{dep_date.strftime('%Y-%m-%d')}%20"
                f"through%20{ret_date.strftime('%Y-%m-%d')}"
            )
            
            deals.append({
                "Direction": "🇩🇪 ➔ 🇲🇩 (Start DE)" if direction == "DE_TO_MD" else "🇲🇩 ➔ 🇩🇪 (Start MD)",
                "Airport DE": de_airport,
                "Route": f"{origin} ⇄ {destination}",
                "Outbound": dep_date.strftime("%a, %d.%m.%Y"),
                "Return": ret_date.strftime("%a, %d.%m.%Y"),
                "SortDate": dep_date,
                "Trip Length": f"{duration} Days",
                "Airline": airline,
                "Type": "Direct" if is_direct else "1 Stop",
                "Total Price (€)": price,
                "Booking Link": gf_link
            })
            
    df = pd.DataFrame(deals)
    if not df.empty:
        df = df.sort_values(by=["Total Price (€)", "SortDate"]).drop_duplicates(
            subset=["Route", "Outbound", "Return"]
        )
    return df

# --- HELPER: FAST SMART LIVE SCANNER ---
def fetch_live_deals_smart(
    selected_airports: list,
    selected_directions: list,
    max_price: int,
    min_days: int,
    max_days: int,
    months_ahead: int,
    smart_weekdays_only: bool = True
):
    deals = []
    today = datetime.now().date()
    total_days_to_scan = months_ahead * 30
    
    search_queue = []
    for de_ap in selected_airports:
        valid_weekdays = DIRECT_SCHEDULES.get(de_ap, [0, 1, 2, 3, 4, 5, 6])
        
        for offset in range(3, total_days_to_scan):
            dep_date = today + timedelta(days=offset)
            if smart_weekdays_only and dep_date.weekday() not in valid_weekdays:
                continue
                
            for duration in range(min_days, max_days + 1):
                ret_date = dep_date + timedelta(days=duration)
                if smart_weekdays_only and ret_date.weekday() not in valid_weekdays:
                    continue
                    
                if "🇩🇪 ➔ 🇲🇩 (Start DE)" in selected_directions:
                    search_queue.append((de_ap, AIRPORT_MD, "🇩🇪 ➔ 🇲🇩 (Start DE)", de_ap, dep_date, ret_date, duration))
                if "🇲🇩 ➔ 🇩🇪 (Start MD)" in selected_directions:
                    search_queue.append((AIRPORT_MD, de_ap, "🇲🇩 ➔ 🇩🇪 (Start MD)", de_ap, dep_date, ret_date, duration))

    if not search_queue:
        return pd.DataFrame()

    progress_bar = st.progress(0)
    status_text = st.empty()
    total_queries = len(search_queue)

    for idx, (origin, dest, dir_label, de_ap, dep_date, ret_date, duration) in enumerate(search_queue):
        progress_bar.progress((idx + 1) / total_queries)
        dep_str = dep_date.strftime("%Y-%m-%d")
        ret_str = ret_date.strftime("%Y-%m-%d")
        status_text.text(f"[{idx+1}/{total_queries}] Checking {origin} ⇄ {dest} | {dep_str} to {ret_str} ({duration}d)...")
        
        try:
            filter_obj = create_filter(
                flight_data=[
                    FlightData(date=dep_str, from_airport=origin, to_airport=dest),
                    FlightData(date=ret_str, from_airport=dest, to_airport=origin),
                ],
                trip="round-trip",
                seat="economy",
                passengers=Passengers(adults=1),
            )
            result = get_flights(filter_obj, currency="EUR")
            
            for flight in result.flights:
                raw_price = "".join(c for c in str(flight.price) if c.isdigit())
                if raw_price:
                    price_val = int(raw_price)
                    if price_val <= max_price:
                        gf_link = (
                            f"https://www.google.com/travel/flights?q=Flights%20to%20{dest}%20"
                            f"from%20{origin}%20on%20{dep_str}%20through%20{ret_str}"
                        )
                        deals.append({
                            "Direction": dir_label,
                            "Airport DE": de_ap,
                            "Route": f"{origin} ⇄ {dest}",
                            "Outbound": dep_date.strftime("%a, %d.%m.%Y"),
                            "Return": ret_date.strftime("%a, %d.%m.%Y"),
                            "SortDate": dep_date,
                            "Trip Length": f"{duration} Days",
                            "Airline": flight.name,
                            "Type": "Direct" if flight.stops == 0 else f"{flight.stops} Stop(s)",
                            "Total Price (€)": price_val,
                            "Booking Link": gf_link
                        })
        except Exception:
            continue

    progress_bar.empty()
    status_text.empty()
    
    df = pd.DataFrame(deals)
    if not df.empty:
        df = df.sort_values(by=["Total Price (€)", "SortDate"]).drop_duplicates(
            subset=["Route", "Outbound", "Return", "Total Price (€)"]
        )
    return df


# --- UI LAYOUT ---
st.title("✈️ Deal Radar: Chișinău (RMO) ⇄ CGN / DUS / DTM")
st.markdown(
    "Finds **round-trip flights** (3 to 7 days) under **100 €** across **Cologne (CGN)**, **Düsseldorf (DUS)**, and **Dortmund (DTM)**."
)

with st.sidebar:
    st.header("⚙️ Search Settings")
    data_mode = st.radio(
        "Mode",
        ["Live Scan (Google Flights)", "Demo Mode (Instant Preview)"]
    )
    
    max_price = st.slider("Max Round-Trip Price (€)", min_value=30, max_value=150, value=100, step=5)
    steal_threshold = st.slider("🔥 Ultra-Bargain Alert (€)", min_value=25, max_value=80, value=50, step=5)
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        min_days = st.number_input("Min Days", min_value=2, max_value=7, value=3)
    with col_d2:
        max_days = st.number_input("Max Days", min_value=3, max_value=14, value=7)
        
    airport_filter = st.multiselect(
        "German Airports",
        ["DTM", "CGN", "DUS"],
        default=["DTM", "CGN", "DUS"],
        help="DTM (Dortmund) often has the cheapest Wizz Air flights (~35-50€ return)."
    )
    
    direction_filter = st.multiselect(
        "Direction",
        ["🇩🇪 ➔ 🇲🇩 (Start DE)", "🇲🇩 ➔ 🇩🇪 (Start MD)"],
        default=["🇩🇪 ➔ 🇲🇩 (Start DE)", "🇲🇩 ➔ 🇩🇪 (Start MD)"]
    )
    
    if data_mode == "Live Scan (Google Flights)":
        st.divider()
        st.subheader("⚡ Speed Optimization")
        smart_mode = st.checkbox(
            "Fast Scan: Direct Flight Days Only",
            value=True,
            help="Only scans the weekdays when Wizz Air, HiSky, FlyOne & Eurowings actually fly direct. Makes scanning ~5x faster!"
        )
        months_to_scan = st.slider(
            "Horizon (Months ahead)",
            min_value=1, max_value=3, value=1,
            help="Start with 1 month for a fast ~25-second scan on your phone, or slide up to 3 months for a full quarter scan."
        )
        run_live = st.button("🚀 Start Fast Live Scan", type="primary", use_container_width=True)
    else:
        run_live = False

# --- FETCH & FILTER DATA ---
if data_mode == "Demo Mode (Instant Preview)":
    df = generate_demo_deals(max_price=max_price, min_days=min_days, max_days=max_days, months=3)
    if not df.empty:
        df = df[df["Direction"].isin(direction_filter)]
        df = df[df["Airport DE"].isin(airport_filter)]
else:
    if not FAST_FLIGHTS_AVAILABLE:
        st.error("Package `fast-flights` is missing. Make sure `requirements.txt` contains `fast-flights`.")
        st.stop()
    if run_live:
        df = fetch_live_deals_smart(
            selected_airports=airport_filter,
            selected_directions=direction_filter,
            max_price=max_price,
            min_days=min_days,
            max_days=max_days,
            months_ahead=months_to_scan,
            smart_weekdays_only=smart_mode
        )
        st.session_state["live_df"] = df
    df = st.session_state.get("live_df", pd.DataFrame())

# --- DISPLAY RESULTS ---
if df.empty:
    if data_mode == "Live Scan (Google Flights)" and not run_live:
        st.info("👈 Tap the **>** arrow in the top-left corner to open filters, then tap **🚀 Start Fast Live Scan**.")
    else:
        st.warning(f"No round-trip flights found under {max_price} € for your selected filters.")
else:
    cheapest = df["Total Price (€)"].min()
    ultra_deals = df[df["Total Price (€)"] <= steal_threshold]
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Cheapest Round-Trip", f"{cheapest} €")
    m2.metric(f"Total Deals (≤ {max_price} €)", len(df))
    m3.metric(f"🔥 Ultra-Bargains (≤ {steal_threshold} €)", len(ultra_deals))
    
    st.divider()
    
    if not ultra_deals.empty:
        st.subheader(f"🔥 Top Steals Under {steal_threshold} € (Round-Trip!)")
        cols = st.columns(min(len(ultra_deals), 3))
        for idx, (_, row) in enumerate(ultra_deals.head(3).iterrows()):
            with cols[idx]:
                st.success(
                    f"### {row['Total Price (€)']} € — {row['Route']}\n"
                    f"**{row['Direction']}**\n\n"
                    f"📅 **Out:** {row['Outbound']}\n\n"
                    f"📅 **Back:** {row['Return']} ({row['Trip Length']})\n\n"
                    f"✈️ {row['Airline']} ({row['Type']})\n\n"
                    f"[👉 Open in Google Flights]({row['Booking Link']})"
                )
        st.divider()

    tab_all, tab_de, tab_md = st.tabs([
        f"All Deals ({len(df)})", 
        "🇩🇪 Start in Germany (CGN/DUS/DTM)", 
        "🇲🇩 Start in Chișinău (RMO)"
    ])
    
    display_cols = ["Direction", "Route", "Outbound", "Return", "Trip Length", "Airline", "Type", "Total Price (€)", "Booking Link"]
    
    for tab, subset in [
        (tab_all, df),
        (tab_de, df[df["Direction"] == "🇩🇪 ➔ 🇲🇩 (Start DE)"]),
        (tab_md, df[df["Direction"] == "🇲🇩 ➔ 🇩🇪 (Start MD)"])
    ]:
        with tab:
            st.dataframe(
                subset[display_cols],
                column_config={
                    "Booking Link": st.column_config.LinkColumn("Direct Link", display_text="Check Fare ↗"),
                    "Total Price (€)": st.column_config.NumberColumn("Total Price", format="%d €")
                },
                hide_index=True,
                use_container_width=True
            )
