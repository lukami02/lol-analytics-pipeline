# dashboard.py
import os
from urllib.parse import quote

import altair as alt
import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="LoL Analytics", page_icon="🎮", layout="wide")


# --------------------------------------------------------------------------
# API access
# --------------------------------------------------------------------------

@st.cache_data(ttl=600)
def api_get(path: str, params: tuple = ()) -> dict:
    """GET helper. `params` is a tuple of pairs so it is hashable for caching."""
    r = requests.get(f"{API_URL}{path}", params=dict(params), timeout=30)
    r.raise_for_status()
    return r.json()


def load_champions(patch: str, position: str | None, min_games: int) -> pd.DataFrame:
    params = [("patch", patch), ("min_games", min_games), ("limit", 200), ("sort", "games")]
    if position:
        params.append(("position", position))
    df = pd.DataFrame(api_get("/champions", tuple(params))["results"])
    if df.empty:
        return df
    df["win_rate"] *= 100
    df["pick_rate"] *= 100
    return df


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------

st.title("🎮 LoL Analytics")

try:
    patches = api_get("/patches")["patches"]
except requests.RequestException as e:
    st.error(f"API is not reachable at {API_URL}: {e}")
    st.stop()

if not patches:
    st.warning("No data available yet.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    patch = st.selectbox("Patch", patches[::-1], index=0) 
    position = st.selectbox(
        "Position", [None, "TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"],
        format_func=lambda p: "All" if p is None else p.title(),
    )
    min_games = st.slider("Minimum games", 1, 500, 50, step=10)
    st.caption(f"API: {API_URL}")

df = load_champions(patch, position, min_games)

tab_champs, tab_history, tab_players = st.tabs(
    ["Champions", "Champion history", "Top players"]
)


# --------------------------------------------------------------------------
# Tab 1: champions overview
# --------------------------------------------------------------------------

with tab_champs:
    if df.empty:
        st.info("No champions match these filters.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Games", f"{int(df['games'].sum()):,}")
        c3.metric("Avg win rate", f"{df['win_rate'].mean():.1f}%")
        best = df.loc[df["win_rate"].idxmax()]
        c4.metric("Best win rate", f"{best['champion_name']} ({best['win_rate']:.1f}%)")

        st.subheader("Win rate vs pick rate")
        scatter = (
            alt.Chart(df)
            .mark_circle(opacity=0.75)
            .encode(
                x=alt.X("pick_rate:Q", title="Pick rate (%)"),
                y=alt.Y("win_rate:Q", title="Win rate (%)", scale=alt.Scale(zero=False)),
                size=alt.Size("games:Q", legend=None),
                color=alt.Color("position:N", title="Position"),
                tooltip=["champion_name", "position", "games",
                         alt.Tooltip("win_rate:Q", format=".1f"),
                         alt.Tooltip("pick_rate:Q", format=".1f"),
                         alt.Tooltip("kda:Q", format=".2f")],
            )
            .interactive()
        )
        rule = alt.Chart(pd.DataFrame({"y": [50]})).mark_rule(strokeDash=[4, 4]).encode(y="y:Q")
        st.altair_chart(scatter + rule, width="stretch")

        left, right = st.columns(2)
        with left:
            st.subheader("Top 10 by win rate")
            st.dataframe(
                df.nlargest(10, "win_rate")[["champion_name", "position", "games", "win_rate"]],
                hide_index=True, width="stretch",
                column_config={"win_rate": st.column_config.NumberColumn(format="%.1f%%")},
            )
        with right:
            st.subheader("Top 10 by pick rate")
            st.dataframe(
                df.nlargest(10, "pick_rate")[["champion_name", "position", "games", "pick_rate"]],
                hide_index=True, width="stretch",
                column_config={"pick_rate": st.column_config.NumberColumn(format="%.1f%%")},
            )

        st.subheader("Full table")
        st.dataframe(
            df.sort_values("games", ascending=False),
            hide_index=True, width="stretch",
            column_config={
                "win_rate": st.column_config.ProgressColumn(
                    "Win rate", format="%.1f%%", min_value=40, max_value=60),
                "pick_rate": st.column_config.NumberColumn("Pick rate", format="%.2f%%"),
                "kda": st.column_config.NumberColumn("KDA", format="%.2f"),
                "cs_per_min": st.column_config.NumberColumn("CS/min", format="%.1f"),
                "avg_damage": st.column_config.NumberColumn("Avg damage", format="%d"),
                "avg_vision": st.column_config.NumberColumn("Avg vision", format="%.1f"),
            },
        )


# --------------------------------------------------------------------------
# Tab 2: single champion across patches
# --------------------------------------------------------------------------

with tab_history:
    names = sorted(df["champion_name"].unique()) if not df.empty else []
    champion = st.selectbox("Champion", names) if names else None

    if champion:
        hist = pd.DataFrame(api_get(f"/champions/{quote(champion)}")["history"])
        hist["win_rate"] *= 100
        hist["pick_rate"] *= 100
        hist = hist[hist["games"] >= max(10, min_games // 5)]  # hide noisy tiny samples

        metric = st.radio(
            "Metric", ["win_rate", "pick_rate", "kda", "cs_per_min", "avg_damage"],
            horizontal=True,
        )
        chart = (
            alt.Chart(hist)
            .mark_line(point=True)
            .encode(
                x=alt.X("patch:N", sort=patches, title="Patch"),
                y=alt.Y(f"{metric}:Q", scale=alt.Scale(zero=False)),
                color="position:N",
                tooltip=["patch", "position", "games", alt.Tooltip(f"{metric}:Q", format=".2f")],
            )
        )
        st.altair_chart(chart, width="stretch")
        st.dataframe(hist.drop(columns=["champion_name"]), hide_index=True,
                     width="stretch")


# --------------------------------------------------------------------------
# Tab 3: top players
# --------------------------------------------------------------------------

with tab_players:
    # The API caps `limit` at 200, which is exactly the list we want.
    players = pd.DataFrame(api_get("/top-players", (("limit", 200),))["results"])

    if players.empty:
        st.info("No player data available.")
    else:
        players = players.sort_values("rank_position")
        players["riot_id"] = players["riot_id"].fillna("(not in sample)")
        players["win_rate"] *= 100  # NaN stays NaN

        # --- Summary metrics ---
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Snapshot", str(players["snapshot_date"].iloc[0]))
        c2.metric("#1 LP", f"{int(players['league_points'].iloc[0]):,}")
        c3.metric(f"#{len(players)} LP (cutoff)", f"{int(players['league_points'].iloc[-1]):,}")
        c4.metric("Median LP", f"{int(players['league_points'].median()):,}")

        # --- LP curve across the leaderboard ---
        st.subheader("LP by rank")
        lp_chart = (
            alt.Chart(players)
            .mark_area(opacity=0.4, line=True)
            .encode(
                x=alt.X("rank_position:Q", title="Rank"),
                y=alt.Y("league_points:Q", title="LP", scale=alt.Scale(zero=False)),
                tooltip=[
                    alt.Tooltip("rank_position:Q", title="Rank"),
                    alt.Tooltip("riot_id:N", title="Player"),
                    alt.Tooltip("league_points:Q", title="LP"),
                ],
            )
        )
        st.altair_chart(lp_chart, width="stretch")

        # --- Leaderboard table ---
        st.subheader("Leaderboard")
        query = st.text_input("Search player", placeholder="e.g. Faker")
        view = players
        if query:
            view = players[players["riot_id"].str.contains(query, case=False, na=False)]

        st.dataframe(
            view.drop(columns=["puuid", "snapshot_date"]),
            hide_index=True, width="stretch", height=600,
            column_config={
                "rank_position": st.column_config.NumberColumn("Rank", format="%d"),
                "riot_id": "Player",
                "league_points": st.column_config.NumberColumn("LP", format="%d"),
                "games": "Sampled games",
                "win_rate": st.column_config.ProgressColumn(
                    "Sampled win rate", format="%.1f%%", min_value=0, max_value=100),
                "kda": st.column_config.NumberColumn("KDA", format="%.2f"),
                "cs_per_min": st.column_config.NumberColumn("CS/min", format="%.1f"),
                "most_played_champion": "Most played",
            },
        )

        st.subheader("Most played champions among top players")
        counts = players["most_played_champion"].value_counts().head(15).reset_index()
        counts.columns = ["champion", "players"]
        st.altair_chart(
            alt.Chart(counts).mark_bar().encode(
                x=alt.X("players:Q", title="Players"),
                y=alt.Y("champion:N", sort="-x", title=None),
            ),
            width="stretch",
        )
