# J12 Performance Dashboard

Living Instagram performance dashboard. A scheduled GitHub Action pulls metrics
from the Instagram Graph API once a day, commits them to this repo, and
GitHub Pages serves the dashboard reading directly from that data — no backend
server required.

## Setup (one-time)

### 1. Create the repo
Create `j12ai/performance-dashboard` on GitHub and upload everything in this
folder to the root of the `main` branch (same pattern as `sop-manuals`).

### 2. Add your API credentials as repo secrets
Go to **Settings → Secrets and variables → Actions → New repository secret**
and add:

| Secret name | Value |
|---|---|
| `IG_ACCESS_TOKEN` | Your long-lived Instagram Graph API access token |
| `IG_BUSINESS_ID` | Your Instagram Business Account ID |

Never commit these values directly into any file in the repo — secrets only.

### 3. Enable GitHub Pages
**Settings → Pages → Source → Deploy from a branch → `main` / root (`/`)**.
Your dashboard will be live at:

```
https://j12ai.github.io/performance-dashboard/
```

### 4. Run the Action once manually
**Actions tab → "Fetch Instagram Metrics" → Run workflow.**
This populates `data/videos.json` and `data/history.jsonl` for the first time.
After that, it runs automatically every day at 09:00 UTC (edit the cron
schedule in `.github/workflows/fetch-metrics.yml` if you want a different time).

## Token expiry

Long-lived Instagram tokens expire roughly every 60 days. When the Action
starts failing with an auth error, generate a new token via the Graph API
Explorer / Access Token Debugger and update the `IG_ACCESS_TOKEN` secret.
(A refresh-automation step can be added later if this becomes a hassle.)

## File structure

```
index.html                        → the dashboard itself
data/videos.json                  → latest snapshot per video (dashboard reads this)
data/history.jsonl                → one line per video per day, powers the trend chart
scripts/fetch_metrics.py          → pulls from Graph API, writes the data files
.github/workflows/fetch-metrics.yml → the daily scheduled job
```

## What the dashboard shows

- **Headline stats** — post count, total and *median* reach/views, engagement
  rate, save rate, average watch time. Median matters more than total: it
  describes the typical post rather than being dragged around by one outlier.
- **Top performer** — the best post, with a plain-language reason it stands out
  (e.g. "4.5x the reach of your median post").
- **Grid or table view** — the grid is for scanning thumbnails, the table for
  comparing numbers. Every column sorts. `vs Median` is the quickest read on
  whether a post actually over-performed.
- **Per-post breakdown** — click anything for full metrics, each benchmarked
  against your median, plus a day-over-day trend chart.

Rates use **reach** as the denominator, not views. Reach is unique people, so
an engagement rate built on it can't exceed 100% the way a views-based one can.

## Known limitations

Instagram's Graph API exposes aggregate metrics (views, reach, likes,
comments, shares, saves, average watch time) — it does not expose a
frame-by-frame retention curve. The trend chart shows how each video's
totals grow day over day instead, which is the closest available signal to
"how it's performing over time."

The trend chart needs several daily runs before it has anything to plot. Until
then it shows a single point and says so.

If the API withholds `views` for a post, the dashboard falls back to reach and
says so in a banner rather than quietly presenting reach as views.

## Metric names change

Meta deprecates insight metrics regularly — `plays` and `video_views` were
folded into `views` in January 2025, which silently reduced every view count on
this dashboard to reach until it was fixed. Two defences are now in place:

- The fetcher probes which metrics the API actually accepts and drops just the
  dead ones, instead of letting one bad name fail the whole request.
- It tries the newest Graph API version first and steps back through older ones
  until the account answers, so a version going away doesn't break the job.

Watch the Action logs for `dropping unsupported metric:` — that's the early
warning that a metric name has moved again.

Note: `ig_reels_avg_watch_time` is returned in **milliseconds**; the fetcher
converts it to seconds before writing.

## Next phase (not built yet)

Automated per-video audits (what worked/didn't and why) — pairing this
metrics data against the BLOOM script/storytelling breakdowns to generate
plain-language write-ups per video.
