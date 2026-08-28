#!/usr/bin/env python3
"""
J12 Performance Dashboard — Instagram metrics fetcher.

Pulls media + insights for the configured Instagram Business account via the
Meta Graph API, then writes:
  - data/videos.json   -> latest snapshot per video (what the dashboard reads)
  - data/history.jsonl  -> one line appended per video per run, for trend charts

Required environment variables (set as GitHub Actions secrets):
  IG_ACCESS_TOKEN   - long-lived user access token
  IG_BUSINESS_ID    - Instagram Business Account ID

Run manually for testing:
  IG_ACCESS_TOKEN=xxx IG_BUSINESS_ID=xxx python scripts/fetch_metrics.py
"""

import json
import os
import sys
import datetime
from pathlib import Path

import requests

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
VIDEOS_JSON = DATA_DIR / "videos.json"
HISTORY_JSONL = DATA_DIR / "history.jsonl"

BASE_METRICS = ["reach", "likes", "comments", "shares", "saved"]
VIDEO_METRICS = ["plays", "ig_reels_avg_watch_time", "total_interactions"]


def get_env(name):
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: missing required environment variable {name}", file=sys.stderr)
        sys.exit(1)
    return val


def fetch_media_list(access_token, ig_business_id):
    media = []
    url = f"{GRAPH_BASE}/{ig_business_id}/media"
    params = {
        "fields": "id,caption,media_type,media_product_type,timestamp,permalink,thumbnail_url,media_url",
        "access_token": access_token,
        "limit": 50,
    }
    while url:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()
        media.extend(payload.get("data", []))
        next_page = payload.get("paging", {}).get("next")
        url = next_page
        params = {}
    return media


def fetch_insights(access_token, media_id, media_type, media_product_type):
    metrics = list(BASE_METRICS)
    is_video_like = media_type in ("VIDEO",) or media_product_type in ("REELS", "VIDEO")
    if is_video_like:
        metrics += VIDEO_METRICS

    url = f"{GRAPH_BASE}/{media_id}/insights"
    params = {"metric": ",".join(metrics), "access_token": access_token}
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        params["metric"] = ",".join(BASE_METRICS)
        resp = requests.get(url, params=params)
        if resp.status_code != 200:
            print(f"WARN: insights failed for {media_id}: {resp.text}", file=sys.stderr)
            return {}
    data = resp.json().get("data", [])
    result = {}
    for item in data:
        name = item.get("name")
        values = item.get("values", [])
        if values:
            result[name] = values[0].get("value")
    return result


def load_existing_videos():
    if VIDEOS_JSON.exists():
        with open(VIDEOS_JSON) as f:
            existing = json.load(f)
        return {v["id"]: v for v in existing}
    return {}


def main():
    access_token = get_env("IG_ACCESS_TOKEN")
    ig_business_id = get_env("IG_BUSINESS_ID")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching media list...")
    media_list = fetch_media_list(access_token, ig_business_id)
    print(f"Found {len(media_list)} media items.")

    run_timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    videos = []
    history_lines = []

    for media in media_list:
        media_id = media["id"]
        insights = fetch_insights(
            access_token, media_id, media.get("media_type"), media.get("media_product_type")
        )

        views = insights.get("plays") or insights.get("reach") or 0
        saves = insights.get("saved", 0)
        likes = insights.get("likes", 0)
        comments = insights.get("comments", 0)
        shares = insights.get("shares", 0)
        avg_watch_time = insights.get("ig_reels_avg_watch_time")
        reach = insights.get("reach", 0)

        record = {
            "id": media_id,
            "caption": (media.get("caption") or "")[:280],
            "media_type":
