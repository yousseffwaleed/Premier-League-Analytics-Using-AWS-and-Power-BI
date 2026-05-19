"""
    Premier League 2024-25 — Fetch + Build Dataset
    API: football-data.org (Free Tier)

    Steps:
        1. Fetch data from API as JSON
        2. Convert JSON to 4 clean CSV files

    Output:
        pl_2024_25_data.json
        csv/matches.csv
        csv/standings.csv
        csv/scorers.csv
        csv/teams.csv

    Setup:
        pip install requests pandas

    Run:
        python fetch_pl_data.py
"""

# Import needed libraries
import os
import time
import requests
import pandas as pd
import boto3
from io import StringIO
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────
API_KEY     = os.environ["API_KEY"]
S3_BUCKET   = os.environ["S3_BUCKET"]
BASE_URL    = "https://api.football-data.org/v4"
HEADERS     = {"X-Auth-Token": API_KEY}
COMPETITION = "PL"
SEASON      = 2024
S3_PREFIX   = f"premier-league/season-2024-25"
s3 = boto3.client("s3")

# Function to call the API with rate limit handling
def api_get(endpoint, params=None):
    response = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=30)
    if response.status_code == 429:
        time.sleep(int(response.headers.get("X-RequestCounter-Reset", 60)))
        response = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=30)
    response.raise_for_status()
    return response.json()

# Function to upload DataFrame as CSV to S3
def upload(df, filename):
    buf = StringIO()
    df.to_csv(buf, index=False)
    s3.put_object(Bucket=S3_BUCKET, Key=f"{S3_PREFIX}/{filename}", Body=buf.getvalue())

# Functions to build DataFrames from API responses
def build_matches(matches):
    rows = []
    for m in matches:
        ft = m["score"]["fullTime"]
        ht = m["score"]["halfTime"]
        hg, ag = ft.get("home"), ft.get("away")
        refs = m.get("referees", [])
        rows.append({
            "match_id":        m["id"],
            "matchweek":       m["matchday"],
            "date":            m["utcDate"][:10],
            "kickoff_utc":     m["utcDate"][11:16],
            "status":          m["status"],
            "home_team":       m["homeTeam"]["name"],
            "home_team_short": m["homeTeam"]["shortName"],
            "home_team_tla":   m["homeTeam"]["tla"],
            "away_team":       m["awayTeam"]["name"],
            "away_team_short": m["awayTeam"]["shortName"],
            "away_team_tla":   m["awayTeam"]["tla"],
            "home_goals_ft":   hg,
            "away_goals_ft":   ag,
            "home_goals_ht":   ht.get("home"),
            "away_goals_ht":   ht.get("away"),
            "total_goals":     (hg + ag) if hg is not None else None,
            "result":          ("H" if hg > ag else "A" if ag > hg else "D") if hg is not None else None,
            "winner":          m["score"]["winner"],
            "duration":        m["score"]["duration"],
            "referee":         refs[0]["name"] if refs else None,
        })
    return pd.DataFrame(rows)

# Build standings DataFrame from API response
def build_standings(standings):
    rows = []
    for group in standings:
        for e in group["table"]:
            rows.append({
                "standing_type":   group["type"],
                "position":        e["position"],
                "team":            e["team"]["name"],
                "team_short":      e["team"]["shortName"],
                "team_tla":        e["team"]["tla"],
                "played":          e["playedGames"],
                "won":             e["won"],
                "drawn":           e["draw"],
                "lost":            e["lost"],
                "goals_for":       e["goalsFor"],
                "goals_against":   e["goalsAgainst"],
                "goal_difference": e["goalDifference"],
                "points":          e["points"],
                "form":            e["form"],
            })
    return pd.DataFrame(rows)

# Build scorers DataFrame from API response
def build_scorers(scorers):
    rows = []
    for rank, s in enumerate(scorers, 1):
        rows.append({
            "rank":           rank,
            "player_name":    s["player"]["name"],
            "nationality":    s["player"]["nationality"],
            "position":       s["player"]["section"],
            "date_of_birth":  s["player"]["dateOfBirth"],
            "team":           s["team"]["name"],
            "team_tla":       s["team"]["tla"],
            "played_matches": s["playedMatches"],
            "goals":          s["goals"],
            "assists":        s["assists"],
            "penalties":      s["penalties"],
            "non_pen_goals":  (s["goals"] or 0) - (s["penalties"] or 0),
        })
    return pd.DataFrame(rows)

# Build teams DataFrame from API response
def build_teams(teams):
    rows = []
    for t in teams:
        coach = t.get("coach", {})
        rows.append({
            "team_name":         t["name"],
            "short_name":        t["shortName"],
            "tla":               t["tla"],
            "stadium":           t["venue"],
            "founded":           t["founded"],
            "colors":            t["clubColors"],
            "website":           t["website"],
            "coach_name":        coach.get("name"),
            "coach_nationality": coach.get("nationality"),
            "crest_url":         t["crest"],
        })
    return pd.DataFrame(rows)

# Main Lambda handler
def lambda_handler(event, context):
    matches   = api_get(f"competitions/{COMPETITION}/matches",   {"season": SEASON})["matches"];   time.sleep(7)
    standings = api_get(f"competitions/{COMPETITION}/standings", {"season": SEASON})["standings"]; time.sleep(7)
    scorers   = api_get(f"competitions/{COMPETITION}/scorers",   {"season": SEASON, "limit": 20})["scorers"]; time.sleep(7)
    teams     = api_get(f"competitions/{COMPETITION}/teams",     {"season": SEASON})["teams"]

    upload(build_matches(matches), "matches.csv")
    upload(build_standings(standings), "standings.csv")
    upload(build_scorers(scorers), "scorers.csv")
    upload(build_teams(teams), "teams.csv")

    return {"statusCode": 200, "body": f"Uploaded 4 CSVs to s3://{S3_BUCKET}/{S3_PREFIX}/"}