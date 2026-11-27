# Trending News Tracker

Collects the last 24 hours of news from 36 sources, groups it into **Worldwide / India / Bangalore**,
sorts it into 14 topics (including Compliance), ranks every story with a 0-100 trending score,
and publishes a web page that refreshes every 2 hours.

## What's in this folder

| File | What it does |
|---|---|
| `news_tracker.py` | Fetches the news, sorts, scores and builds the page |
| `.github/workflows/update-news.yml` | GitHub Actions job that runs the script and saves the page to `public/` |
| `requirements.txt` | Python package needed (`feedparser`) |
| `docs/news_tracker_flowchart.pptx` | One-slide flowchart explaining how it works |

## Run it on your computer

```
pip install -r requirements.txt
python news_tracker.py
```
Then open `news_report.html` in a browser.

## How the live version works

1. **cron-job.org** calls the GitHub API every 2 hours to start the workflow
   (POST to `https://api.github.com/repos/<user>/<repo>/actions/workflows/update-news.yml/dispatches`
   with body `{"ref":"main"}` and a fine-grained token with Actions: Read and write).
2. **GitHub Actions** runs `news_tracker.py` and commits `public/index.html` and `public/news.json`.
3. **Cloudflare Pages** (connected to the repo, output directory `public`, no build command)
   publishes the new page automatically.

Update times (IST): 1:53, 3:53, 5:53, 7:53, 9:53, 11:53 - AM and PM.

## Trending score (0-100)

Score = 100 × (0.30 Coverage + 0.20 Recency + 0.15 Google searches + 0.15 Momentum
+ 0.07 Regional spread + 0.05 Persistence + 0.05 Major source + 0.03 Watch keywords)

- **Hot** = 65+, **Rising** = 50-64
- Stories about deaths, accidents, disasters or violence are tagged **Sensitive** and hidden by **Brand-safe only**
- Tune weights in `SCORE_WEIGHTS` (they must add up to 1.0)

## Common changes

- **Add a source:** add a line to `FEEDS` - `("Name", "RSS url", "Optional category")`.
  For websites without a feed, use a Google News search URL (see the Inc42 or FATF lines).
- **Add a topic:** add a name and keyword list to `CATEGORIES`. `word*` matches any ending.
- **Change how far back:** `HOURS_BACK`.

## Limits to remember

- Cloudflare free plan: **500 builds/month, shared across all projects**. Every 2 hours ≈ 372/month.
- The GitHub token used by cron-job.org **expires** - renew it before the date shown on GitHub.
- Never put tokens in these files. Keep them only in cron-job.org / GitHub Secrets.
