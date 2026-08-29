#!/usr/bin/env python3
"""
J12 Performance Dashboard — Instagram metrics fetcher.

Pulls media + insights for the configured Instagram account via the Instagram
Graph API, then writes:
  - data/videos.json   -> latest snapshot per video (what the dashboard reads)
  - data/history.jsonl  -> one row per video per DAY, for trend charts

Required environment variables (set as GitHub Actions secrets):
  IG_ACCESS_TOKEN   - long-lived access token
  IG_BUSINESS_ID    - Instagram account ID

Optional:
  IG_GRAPH_VERSION  - pin a Graph API version (default: auto-detect)

Run manually for testing:
  IG_ACCESS_TOKEN=xxx IG_BUSINESS_ID=xxx python scripts/fetch_metrics.py
"""

import json
import os
import sys
import datetime
from pathlib import Path

import requests

# Tried newest-first at startup; the first one the account answers on wins.
# Metric availability changes between versions, so this is not cosmetic.
GRAPH_VERSION_CANDIDATES = ["v23.0", "v22.0", "v21.0"]
GRAPH_HOST = "https://graph.instagram.com"

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
VIDEOS_JSON = DATA_DIR / "videos.json"
HISTORY_JSONL = DATA_DIR / "history.jsonl"

# `plays` and `video_views` were deprecated in Jan 2025 (v21+) and folded into
# `views`. Requesting a dead metric fails the WHOLE batch, which is what
# silently reduced every "views" number to reach. Metrics are probed once at
# runtime instead of assumed, so a future deprecation degrades one field
# rather than the entire request.
BASE_METRICS = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions"]
VIDEO_METRICS = ["ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]

graph_base = None
_metric_cache = {}


def get_env(name):
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: missing required environment variable {name}", file=sys.stderr)
        sys.exit(1)
    return val


def resolve_graph_base(access_token, ig_business_id):
    """Pick the newest Graph API version this account actually answers on."""
    pinned = os.environ.get("IG_GRAPH_VERSION")
    candidates = [pinned] if pinned else GRAPH_VERSION_CANDIDATES

    for version in candidates:
        base = f"{GRAPH_HOST}/{version}"
        resp = requests.get(
            f"{base}/{ig_business_id}",
            params={"fields": "id", "access_token": access_token},
        )
        if resp.status_code == 200:
            print(f"Using Graph API {version}")
            return base
        print(f"  {version} unavailable ({resp.status_code}), trying older…", file=sys.stderr)

    print("ERROR: no usable Graph API version. Last response:", resp.text, file=sys.stderr)
    sys.exit(1)


def fetch_media_list(access_token, ig_business_id):
    """Fetch the list of media objects for the account."""
    media = []
    url = f"{graph_base}/{ig_business_id}/media"
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
        params = {}  # next_page URL already has all params baked in
    return media


def request_insights(access_token, media_id, metrics):
    """One insights call. Returns (ok, parsed_dict)."""
    resp = requests.get(
        f"{graph_base}/{media_id}/insights",
        params={"metric": ",".join(metrics), "access_token": access_token},
    )
    if resp.status_code != 200:
        return False, {}

    result = {}
    for item in resp.json().get("data", []):
        values = item.get("values", [])
        if values:
            result[item["name"]] = values[0].get("value")
    return True, result


def probe_metrics(access_token, media_id, candidates):
    """Find which of `candidates` this media will actually return.

    Asked one at a time only when the batch fails, so the common path stays a
    single request.
    """
    supported = []
    for metric in candidates:
        ok, _ = request_insights(access_token, media_id, [metric])
        if ok:
            supported.append(metric)
        else:
            print(f"  dropping unsupported metric: {metric}", file=sys.stderr)
    return supported


def fetch_insights(access_token, media_id, media_type, media_product_type):
    """Fetch insight metrics for a single media object."""
    is_video_like = media_type == "VIDEO" or media_product_type in ("REELS", "VIDEO")
    kind = "video" if is_video_like else "other"
    wanted = BASE_METRICS + VIDEO_METRICS if is_video_like else list(BASE_METRICS)

    metrics = _metric_cache.get(kind, wanted)
    ok, result = request_insights(access_token, media_id, metrics)
    if ok:
        _metric_cache.setdefault(kind, metrics)
        return result

    # Batch failed — work out which metrics survive, and remember it so the
    # rest of the run costs one request per media again.
    if kind not in _metric_cache:
        print(f"Probing supported {kind} metrics on {media_id}…", file=sys.stderr)
        supported = probe_metrics(access_token, media_id, wanted)
        if supported:
            _metric_cache[kind] = supported
            ok, result = request_insights(access_token, media_id, supported)
            if ok:
                return result

    print(f"WARN: insights failed for {media_id}", file=sys.stderr)
    return {}


def ms_to_seconds(value):
    """ig_reels_* watch-time metrics come back in milliseconds."""
    if value is None:
        return None
    return round(value / 1000.0, 1)


def load_history():
    """Existing history keyed by (date, media id) so re-runs update in place."""
    rows = {}
    if HISTORY_JSONL.exists():
        with open(HISTORY_JSONL) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows[(row.get("date", "")[:10], row.get("id"))] = row
    return rows


def main():
    global graph_base

    access_token = get_env("IG_ACCESS_TOKEN")
    ig_business_id = get_env("IG_BUSINESS_ID")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    graph_base = resolve_graph_base(access_token, ig_business_id)

    print("Fetching media list...")
    media_list = fetch_media_list(access_token, ig_business_id)
    print(f"Found {len(media_list)} media items.")

    run_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    today = run_timestamp[:10]
    videos = []
    history = load_history()

    for media in media_list:
        media_id = media["id"]
        insights = fetch_insights(
            access_token, media_id, media.get("media_type"), media.get("media_product_type")
        )

        reach = insights.get("reach", 0)
        # Fall back to reach only if `views` is genuinely absent, and record
        # which one we used so the dashboard can label it honestly.
        raw_views = insights.get("views")
        views = raw_views if raw_views is not None else reach

        metrics = {
            "views": views,
            "views_are_reach": raw_views is None,
            "reach": reach,
            "likes": insights.get("likes", 0),
            "comments": insights.get("comments", 0),
            "shares": insights.get("shares", 0),
            "saves": insights.get("saved", 0),
            "interactions": insights.get("total_interactions", 0),
            "avg_watch_time_sec": ms_to_seconds(insights.get("ig_reels_avg_watch_time")),
            "total_watch_time_sec": ms_to_seconds(insights.get("ig_reels_video_view_total_time")),
        }

        videos.append({
            "id": media_id,
            "caption": (media.get("caption") or "")[:280],
            "media_type": media.get("media_type"),
            "media_product_type": media.get("media_product_type"),
            "timestamp": media.get("timestamp"),
            "permalink": media.get("permalink"),
            "thumbnail_url": media.get("thumbnail_url") or media.get("media_url"),
            "metrics": metrics,
            "last_updated": run_timestamp,
        })

        # One row per video per day. A second run on the same day overwrites
        # that day rather than adding a duplicate point to the trend chart.
        history[(today, media_id)] = dict(metrics, date=today, id=media_id)

    # Sort newest first
    videos.sort(key=lambda v: v.get("timestamp") or "", reverse=True)

    with open(VIDEOS_JSON, "w") as f:
        json.dump(videos, f, indent=2)
    print(f"Wrote {len(videos)} videos to {VIDEOS_JSON}")

    with open(HISTORY_JSONL, "w") as f:
        for key in sorted(history, key=lambda k: (k[0], k[1] or "")):
            f.write(json.dumps(history[key]) + "\n")
    print(f"Wrote {len(history)} history rows to {HISTORY_JSONL}")

    if videos and videos[0]["metrics"]["views_are_reach"]:
        print("NOTE: `views` unavailable — showing reach in its place.", file=sys.stderr)


if __name__ == "__main__":
    main()
