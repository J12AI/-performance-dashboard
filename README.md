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

## Known limitation

Instagram's Graph API exposes aggregate metrics (views, reach, likes,
comments, shares, saves, average watch time) — it does not expose a
frame-by-frame retention curve. The trend chart shows how each video's
totals grow day over day instead, which is the closest available signal to
"how it's performing over time."

## Next phase (not built yet)

Automated per-video audits (what worked/didn't and why) — pairing this
metrics data against the BLOOM script/storytelling breakdowns to generate
plain-language write-ups per video.
