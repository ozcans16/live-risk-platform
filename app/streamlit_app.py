import os
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import streamlit as st
import matplotlib.pyplot as plt
from rapidfuzz import fuzz


# ============================================================
# LIVE EVENT RISK INTELLIGENCE PLATFORM
# Rule-Based / No Machine Learning
# ============================================================



BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

os.makedirs(
    DATA_DIR,
    exist_ok=True
)

DB_PATH = os.path.join(
    DATA_DIR,
    "risk_history.db"
)



CITY = "Isparta"

LATITUDE = 37.7648
LONGITUDE = 30.5566

EARTHQUAKE_RADIUS_KM = 300

REQUEST_TIMEOUT = 8



st.set_page_config(
    page_title="Live Event Risk Intelligence",
    page_icon="🚨",
    layout="wide"
)



st.markdown(
    """
    <style>

    .main {
        padding-top: 1rem;
    }

    .risk-card {
        padding: 20px;
        border-radius: 12px;
        border: 1px solid rgba(128,128,128,0.25);
        text-align: center;
    }

    .small-text {
        color: #888888;
        font-size: 14px;
    }

    </style>
    """,
    unsafe_allow_html=True
)



def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def risk_level(score):
    if score < 30:
        return "LOW"

    if score < 60:
        return "MEDIUM"

    if score < 80:
        return "HIGH"

    return "CRITICAL"


def risk_emoji(score):
    if score < 30:
        return "🟢"

    if score < 60:
        return "🟡"

    if score < 80:
        return "🟠"

    return "🔴"



def initialize_database():

    try:

        connection = sqlite3.connect(
            DB_PATH
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS risk_history (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                timestamp TEXT NOT NULL,

                risk_score REAL NOT NULL,

                earthquake_score REAL NOT NULL,

                weather_score REAL NOT NULL,

                news_score REAL NOT NULL,

                transport_score REAL NOT NULL,

                event_count INTEGER NOT NULL

            )
            """
        )

        connection.commit()

        return connection

    except sqlite3.Error:

        return None


def save_risk_snapshot(
    scores,
    event_count
):

    connection = initialize_database()

    if connection is None:
        return

    try:

        connection.execute(
            """
            INSERT INTO risk_history (

                timestamp,

                risk_score,

                earthquake_score,

                weather_score,

                news_score,

                transport_score,

                event_count

            )

            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(
                    timezone.utc
                ).isoformat(),

                scores["earthquake"],

                scores["weather"],

                scores["news"],

                scores["transport"],

                scores["total"],

                event_count
            )
        )

        connection.commit()

    except sqlite3.Error:

        pass

    finally:

        connection.close()


def load_history():

    connection = initialize_database()

    if connection is None:

        return pd.DataFrame()

    try:

        history = pd.read_sql_query(
            """
            SELECT *
            FROM risk_history
            ORDER BY timestamp ASC
            """,
            connection
        )

    except Exception:

        history = pd.DataFrame()

    finally:

        connection.close()

    if not history.empty:

        history["timestamp"] = pd.to_datetime(
            history["timestamp"],
            errors="coerce",
            utc=True
        )

    return history



def empty_events():

    return pd.DataFrame(
        columns=[
            "event_type",
            "location",
            "severity",
            "timestamp",
            "source",
            "description",
            "latitude",
            "longitude",
            "event_cluster_id",
            "match_score"
        ]
    )



def collect_earthquakes():

    url = (
        "https://earthquake.usgs.gov/"
        "fdsnws/event/1/query"
    )

    parameters = {

        "format": "geojson",

        "latitude": LATITUDE,

        "longitude": LONGITUDE,

        "maxradiuskm": EARTHQUAKE_RADIUS_KM,

        "minmagnitude": 2.5,

        "orderby": "time",

        "limit": 50
    }

    try:

        response = requests.get(
            url,
            params=parameters,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        data = response.json()

        rows = []

        for feature in data.get(
            "features",
            []
        ):

            properties = feature.get(
                "properties",
                {}
            )

            geometry = feature.get(
                "geometry",
                {}
            )

            coordinates = geometry.get(
                "coordinates",
                []
            )

            longitude = (
                coordinates[0]
                if len(coordinates) > 0
                else np.nan
            )

            latitude = (
                coordinates[1]
                if len(coordinates) > 1
                else np.nan
            )

            rows.append(
                {

                    "event_type":
                        "earthquake",

                    "location":
                        properties.get(
                            "place",
                            "Unknown"
                        ),

                    "severity":
                        safe_float(
                            properties.get(
                                "mag"
                            )
                        ),

                    "timestamp":
                        pd.to_datetime(
                            properties.get(
                                "time"
                            ),
                            unit="ms",
                            errors="coerce",
                            utc=True
                        ),

                    "source":
                        "USGS",

                    "description":
                        properties.get(
                            "title",
                            "Earthquake"
                        ),

                    "latitude":
                        latitude,

                    "longitude":
                        longitude
                }
            )

        if not rows:

            return empty_events()

        return pd.DataFrame(rows)

    except Exception:

        return empty_events()



def collect_weather():

    url = (
        "https://api.open-meteo.com/"
        "v1/forecast"
    )

    parameters = {

        "latitude": LATITUDE,

        "longitude": LONGITUDE,

        "hourly":
            "temperature_2m,"
            "wind_speed_10m,"
            "precipitation",

        "forecast_days": 1,

        "timezone": "auto"
    }

    try:

        response = requests.get(
            url,
            params=parameters,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        data = response.json()

        hourly = data.get(
            "hourly",
            {}
        )

        times = hourly.get(
            "time",
            []
        )

        temperatures = hourly.get(
            "temperature_2m",
            []
        )

        winds = hourly.get(
            "wind_speed_10m",
            []
        )

        rain = hourly.get(
            "precipitation",
            []
        )

        if not times:

            return empty_events()

        weather = pd.DataFrame(
            {
                "time": times,
                "temperature": temperatures,
                "wind": winds,
                "rain": rain
            }
        )

        weather["time"] = pd.to_datetime(
            weather["time"],
            errors="coerce"
        )

        current_time = pd.Timestamp.now()

        weather["difference"] = (
            weather["time"]
            - current_time
        ).abs()

        current_index = (
            weather["difference"]
            .idxmin()
        )

        current = weather.loc[
            current_index
        ]

        wind = safe_float(
            current["wind"]
        )

        precipitation = safe_float(
            current["rain"]
        )

        temperature = safe_float(
            current["temperature"]
        )

        wind_score = min(
            (wind / 70) * 100,
            100
        )

        rain_score = min(
            (precipitation / 20) * 100,
            100
        )

        weather_score = max(
            wind_score,
            rain_score
        )

        return pd.DataFrame(
            [
                {

                    "event_type":
                        "weather",

                    "location":
                        CITY,

                    "severity":
                        round(
                            weather_score,
                            2
                        ),

                    "timestamp":
                        pd.Timestamp.now(
                            tz="UTC"
                        ),

                    "source":
                        "Open-Meteo",

                    "description":
                        (
                            f"Temperature: "
                            f"{temperature:.1f} °C | "
                            f"Wind: "
                            f"{wind:.1f} km/h | "
                            f"Rain: "
                            f"{precipitation:.1f} mm"
                        ),

                    "latitude":
                        LATITUDE,

                    "longitude":
                        LONGITUDE
                }
            ]
        )

    except Exception:

        return empty_events()



def collect_news():

    url = (
        "https://api.gdeltproject.org/"
        "api/v2/doc/doc"
    )

    parameters = {

        "query":
            (
                "earthquake OR "
                "storm OR "
                "flood OR "
                "fire OR "
                "accident OR "
                "crisis"
            ),

        "mode":
            "artlist",

        "format":
            "json",

        "maxrecords":
            25,

        "timespan":
            "6h",

        "sort":
            "HybridRel"
    }

    try:

        response = requests.get(
            url,
            params=parameters,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        data = response.json()

        articles = data.get(
            "articles",
            []
        )

        if not articles:

            return empty_events()

        keywords = {

            "earthquake": 3,

            "storm": 2,

            "flood": 3,

            "fire": 2,

            "accident": 2,

            "crisis": 2
        }

        rows = []

        for article in articles:

            title = str(
                article.get(
                    "title",
                    ""
                )
            ).strip()

            if not title:

                continue

            lower_title = title.lower()

            severity = 0

            for keyword, weight in keywords.items():

                if keyword in lower_title:

                    severity += weight

            rows.append(
                {

                    "event_type":
                        "news",

                    "location":
                        article.get(
                            "sourcecountry",
                            "Global"
                        ),

                    "severity":
                        min(
                            severity * 10,
                            100
                        ),

                    "timestamp":
                        pd.Timestamp.now(
                            tz="UTC"
                        ),

                    "source":
                        "GDELT",

                    "description":
                        title,

                    "latitude":
                        np.nan,

                    "longitude":
                        np.nan
                }
            )

        if not rows:

            return empty_events()

        return pd.DataFrame(rows)

    except Exception:

        return empty_events()



def collect_transport():

    url = (
        "https://opensky-network.org/"
        "api/states/all"
    )

    parameters = {

        "lamin":
            LATITUDE - 2.5,

        "lamax":
            LATITUDE + 2.5,

        "lomin":
            LONGITUDE - 3.0,

        "lomax":
            LONGITUDE + 3.0
    }

    try:

        response = requests.get(
            url,
            params=parameters,
            timeout=REQUEST_TIMEOUT
        )

        response.raise_for_status()

        data = response.json()

        aircraft = (
            data.get("states")
            or []
        )

        aircraft_count = len(
            aircraft
        )

        transport_score = min(
            (aircraft_count / 80) * 100,
            100
        )

        return pd.DataFrame(
            [
                {

                    "event_type":
                        "transport",

                    "location":
                        CITY,

                    "severity":
                        round(
                            transport_score,
                            2
                        ),

                    "timestamp":
                        pd.Timestamp.now(
                            tz="UTC"
                        ),

                    "source":
                        "OpenSky",

                    "description":
                        (
                            f"{aircraft_count} "
                            "aircraft detected"
                        ),

                    "latitude":
                        LATITUDE,

                    "longitude":
                        LONGITUDE
                }
            ]
        )

    except Exception:

        return empty_events()



def clean_events(data):

    if data.empty:

        return empty_events()

    data = data.copy()

    required_columns = [
        "event_type",
        "location",
        "severity",
        "timestamp",
        "source",
        "description",
        "latitude",
        "longitude"
    ]

    for column in required_columns:

        if column not in data.columns:

            data[column] = np.nan

    data["location"] = (
        data["location"]
        .fillna("Unknown")
        .astype(str)
        .str.strip()
    )

    data["description"] = (
        data["description"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    data["severity"] = pd.to_numeric(
        data["severity"],
        errors="coerce"
    ).fillna(0)

    data["severity"] = data[
        "severity"
    ].clip(
        lower=0,
        upper=100
    )

    data["timestamp"] = pd.to_datetime(
        data["timestamp"],
        errors="coerce",
        utc=True
    )

    data = data.dropna(
        subset=["timestamp"]
    )

    data = data.drop_duplicates(
        subset=[
            "event_type",
            "location",
            "description"
        ]
    )

    return data.reset_index(
        drop=True
    )



def match_events(data):

    if data.empty:

        return data

    data = data.copy()

    data["event_cluster_id"] = ""

    data["match_score"] = 100.0

    cluster_number = 1

    for event_type in data[
        "event_type"
    ].unique():

        indexes = list(
            data[
                data["event_type"]
                == event_type
            ].index
        )

        assigned = set()

        for index in indexes:

            if index in assigned:

                continue

            cluster_id = (
                f"{event_type.upper()}-"
                f"{cluster_number}"
            )

            data.loc[
                index,
                "event_cluster_id"
            ] = cluster_id

            assigned.add(index)

            base_text = data.loc[
                index,
                "description"
            ]

            for other_index in indexes:

                if other_index == index:
                    continue

                if other_index in assigned:
                    continue

                other_text = data.loc[
                    other_index,
                    "description"
                ]

                similarity = fuzz.token_set_ratio(
                    base_text,
                    other_text
                )

                if similarity >= 70:

                    data.loc[
                        other_index,
                        "event_cluster_id"
                    ] = cluster_id

                    data.loc[
                        other_index,
                        "match_score"
                    ] = similarity

                    assigned.add(
                        other_index
                    )

            cluster_number += 1

    return data



def calculate_risk(data):

    earthquake_score = 0.0
    weather_score = 0.0
    news_score = 0.0
    transport_score = 0.0

    if not data.empty:

        # -----------------------------
        # EARTHQUAKE
        # -----------------------------

        earthquakes = data[
            data["event_type"]
            == "earthquake"
        ]

        if not earthquakes.empty:

            maximum_magnitude = (
                earthquakes[
                    "severity"
                ].max()
            )

            earthquake_score = (
                (
                    maximum_magnitude
                    - 2.5
                )
                / 3.5
                * 100
            )

            earthquake_score = float(
                np.clip(
                    earthquake_score,
                    0,
                    100
                )
            )

        # -----------------------------
        # WEATHER
        # -----------------------------

        weather = data[
            data["event_type"]
            == "weather"
        ]

        if not weather.empty:

            weather_score = float(
                weather[
                    "severity"
                ].max()
            )

        # -----------------------------
        # NEWS
        # -----------------------------

        news = data[
            data["event_type"]
            == "news"
        ]

        if not news.empty:

            volume_score = min(
                (
                    len(news)
                    / 25
                )
                * 100,
                100
            )

            severity_average = (
                news[
                    "severity"
                ].mean()
            )

            news_score = (
                volume_score * 0.6
                +
                severity_average * 0.4
            )

            news_score = float(
                np.clip(
                    news_score,
                    0,
                    100
                )
            )

        # -----------------------------
        # TRANSPORT
        # -----------------------------

        transport = data[
            data["event_type"]
            == "transport"
        ]

        if not transport.empty:

            transport_score = float(
                transport[
                    "severity"
                ].max()
            )

    # -----------------------------
    # WEIGHTED RISK
    # -----------------------------

    total = (

        earthquake_score * 0.40

        + weather_score * 0.25

        + news_score * 0.20

        + transport_score * 0.15
    )

    total = float(
        np.clip(
            total,
            0,
            100
        )
    )

    return {

        "earthquake":
            round(
                earthquake_score,
                2
            ),

        "weather":
            round(
                weather_score,
                2
            ),

        "news":
            round(
                news_score,
                2
            ),

        "transport":
            round(
                transport_score,
                2
            ),

        "total":
            round(
                total,
                2
            )
    }



def detect_anomaly(history):

    if history.empty:

        return False, 0.0

    if len(history) < 5:

        return False, 0.0

    previous_scores = history[
        "risk_score"
    ].iloc[:-1]

    current_score = history[
        "risk_score"
    ].iloc[-1]

    mean = previous_scores.mean()

    standard_deviation = (
        previous_scores.std()
    )

    if (
        standard_deviation == 0
        or pd.isna(
            standard_deviation
        )
    ):

        return False, 0.0

    z_score = (
        current_score - mean
    ) / standard_deviation

    return (
        abs(z_score) >= 2,
        round(
            float(z_score),
            2
        )
    )



def collect_all_data():

    earthquake = (
        collect_earthquakes()
    )

    weather = (
        collect_weather()
    )

    news = (
        collect_news()
    )

    transport = (
        collect_transport()
    )

    frames = [
        earthquake,
        weather,
        news,
        transport
    ]

    frames = [
        frame
        for frame in frames
        if not frame.empty
    ]

    if not frames:

        return empty_events()

    combined = pd.concat(
        frames,
        ignore_index=True
    )

    combined = clean_events(
        combined
    )

    combined = match_events(
        combined
    )

    return combined



st.title(
    "🚨 Live Event Risk Intelligence Platform"
)

st.markdown(
    """
    **Real-time event monitoring and rule-based
    risk intelligence system**
    """
)

st.caption(
    "No Machine Learning • API-based data collection • "
    "Rule-based risk scoring"
)



with st.sidebar:

    st.header(
        "⚙️ Control Panel"
    )

    st.write(
        f"📍 Monitoring location: **{CITY}**"
    )

    st.write(
        f"🌐 Coordinates: "
        f"{LATITUDE}, {LONGITUDE}"
    )

    st.divider()

    refresh = st.button(
        "🔄 Collect Live Data",
        use_container_width=True
    )

    clear_history = st.button(
        "🗑 Clear History",
        use_container_width=True
    )

    st.divider()

    st.subheader(
        "Risk Weights"
    )

    st.write(
        "🌎 Earthquake: **40%**"
    )

    st.write(
        "🌦 Weather: **25%**"
    )

    st.write(
        "📰 News: **20%**"
    )

    st.write(
        "✈️ Transport: **15%**"
    )

    st.divider()

    st.subheader(
        "Data Sources"
    )

    st.write(
        "• USGS"
    )

    st.write(
        "• Open-Meteo"
    )

    st.write(
        "• GDELT"
    )

    st.write(
        "• OpenSky"
    )



if clear_history:

    connection = initialize_database()

    if connection is not None:

        try:

            connection.execute(
                "DELETE FROM risk_history"
            )

            connection.commit()

        except sqlite3.Error:

            pass

        finally:

            connection.close()

    st.success(
        "Risk history cleared."
    )

    st.rerun()



if "events" not in st.session_state:

    st.session_state.events = empty_events()


if "last_update" not in st.session_state:

    st.session_state.last_update = None



if (
    st.session_state.last_update
    is None
):

    with st.spinner(
        "Initial data collection..."
    ):

        st.session_state.events = (
            collect_all_data()
        )

        st.session_state.last_update = (
            datetime.now(
                timezone.utc
            )
        )



if refresh:

    with st.spinner(
        "Collecting live data..."
    ):

        st.session_state.events = (
            collect_all_data()
        )

        st.session_state.last_update = (
            datetime.now(
                timezone.utc
            )
        )

    st.success(
        "Live data updated."
    )


events = st.session_state.events



scores = calculate_risk(
    events
)

save_risk_snapshot(
    scores,
    len(events)
)

history = load_history()

anomaly, z_score = (
    detect_anomaly(
        history
    )
)



st.subheader(
    "📊 Live Risk Overview"
)

column1, column2, column3, column4 = (
    st.columns(4)
)


with column1:

    st.metric(
        "Risk Score",
        f"{scores['total']:.1f}/100"
    )


with column2:

    st.metric(
        "Risk Level",
        (
            f"{risk_emoji(scores['total'])} "
            f"{risk_level(scores['total'])}"
        )
    )


with column3:

    st.metric(
        "Active Events",
        len(events)
    )


with column4:

    st.metric(
        "Anomaly",
        "YES 🚨"
        if anomaly
        else "NO"
    )


if st.session_state.last_update:

    st.caption(
        "Last update: "
        + st.session_state.last_update.strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )


st.divider()



st.subheader(
    "🎯 Risk Components"
)

risk_data = pd.DataFrame(
    {
        "Source": [
            "Earthquake",
            "Weather",
            "News",
            "Transport"
        ],

        "Score": [
            scores["earthquake"],
            scores["weather"],
            scores["news"],
            scores["transport"]
        ]
    }
)

chart_column, info_column = st.columns(
    [2, 1]
)


with chart_column:

    st.bar_chart(
        risk_data.set_index(
            "Source"
        )
    )


with info_column:

    st.write(
        "### Risk Formula"
    )

    st.write(
        """
        **Total Risk =**

        Earthquake × 0.40

        Weather × 0.25

        News × 0.20

        Transport × 0.15
        """
    )



st.subheader(
    "🚨 Alert Center"
)

alerts = []


if scores["earthquake"] >= 60:

    alerts.append(
        "High earthquake risk score detected."
    )


if scores["weather"] >= 60:

    alerts.append(
        "Severe weather conditions detected."
    )


if scores["news"] >= 60:

    alerts.append(
        "High crisis-related news activity detected."
    )


if scores["transport"] >= 70:

    alerts.append(
        "High transport activity detected."
    )


if anomaly:

    alerts.append(
        f"Risk anomaly detected. "
        f"Z-score: {z_score}"
    )


if not alerts:

    st.success(
        "No active critical alerts."
    )

else:

    for alert in alerts:

        st.warning(
            alert
        )



st.subheader(
    "📈 Event Distribution"
)

if not events.empty:

    distribution = (
        events[
            "event_type"
        ]
        .value_counts()
        .rename_axis(
            "event_type"
        )
        .reset_index(
            name="count"
        )
    )

    st.bar_chart(
        distribution.set_index(
            "event_type"
        )
    )

else:

    st.info(
        "No live events available."
    )



st.subheader(
    "📋 Live Events"
)

if events.empty:

    st.info(
        """
        No live events were received from the
        external data sources.

        The dashboard is still running normally.
        Try the **Collect Live Data** button later.
        """
    )

else:

    display_columns = [

        "event_type",

        "location",

        "severity",

        "timestamp",

        "source",

        "description",

        "event_cluster_id",

        "match_score"
    ]

    st.dataframe(
        events[
            display_columns
        ]
        .sort_values(
            "timestamp",
            ascending=False
        ),
        use_container_width=True,
        hide_index=True
    )



st.subheader(
    "🗺️ Event Map"
)

if not events.empty:

    map_data = events[
        [
            "latitude",
            "longitude"
        ]
    ].copy()

    map_data["latitude"] = pd.to_numeric(
        map_data["latitude"],
        errors="coerce"
    )

    map_data["longitude"] = pd.to_numeric(
        map_data["longitude"],
        errors="coerce"
    )

    map_data = map_data.dropna()

    if not map_data.empty:

        st.map(
            map_data,
            latitude="latitude",
            longitude="longitude",
            zoom=6
        )

    else:

        st.info(
            "No events with geographic coordinates."
        )

else:

    st.info(
        "No geographic event data available."
    )



st.subheader(
    "📉 Risk Trend"
)

if len(history) >= 2:

    figure, axis = plt.subplots(
        figsize=(12, 4)
    )

    axis.plot(
        history["timestamp"],
        history["risk_score"],
        marker="o",
        linewidth=2
    )

    axis.axhline(
        30,
        linestyle="--",
        linewidth=1
    )

    axis.axhline(
        60,
        linestyle="--",
        linewidth=1
    )

    axis.axhline(
        80,
        linestyle="--",
        linewidth=1
    )

    axis.set_xlabel(
        "Time"
    )

    axis.set_ylabel(
        "Risk Score"
    )

    axis.set_ylim(
        0,
        100
    )

    axis.grid(
        alpha=0.25
    )

    figure.autofmt_xdate()

    st.pyplot(
        figure
    )

    plt.close(
        figure
    )

else:

    st.info(
        """
        Risk trend requires at least
        two collected snapshots.

        Click **Collect Live Data** periodically
        to build historical data.
        """
    )



st.subheader(
    "🗄️ Risk History"
)

if not history.empty:

    history_display = history.copy()

    history_display["timestamp"] = (
        history_display[
            "timestamp"
        ]
        .dt.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    st.dataframe(
        history_display.tail(20),
        use_container_width=True,
        hide_index=True
    )

else:

    st.info(
        "No historical risk data available."
    )



st.divider()

st.subheader(
    "ℹ️ System Information"
)

info1, info2, info3 = st.columns(3)

with info1:

    st.write(
        "**Architecture**"
    )

    st.write(
        "API → Cleaning → Matching → "
        "Risk Engine → SQLite → Dashboard"
    )

with info2:

    st.write(
        "**Detection**"
    )

    st.write(
        "Rule-based scoring + "
        "statistical anomaly detection"
    )

with info3:

    st.write(
        "**Machine Learning**"
    )

    st.write(
        "Not used in this version"
    )



st.divider()

st.caption(
    "Live Event Risk Intelligence Platform • "
    "Portfolio Project • "
    "Rule-based risk intelligence system"
)

st.caption(
    "This project is for educational and portfolio "
    "purposes and is not an official emergency warning system."
)