# Exchange Telegram Watch

A free, self-updating competitor dashboard for crypto exchange Telegram channels.

- **Dashboard**: plain HTML/JS. No build step. Hosted on Cloudflare Pages.
- **Scraper**: Python, runs every 6 hours on GitHub Actions. It reads public channel previews (`t.me/s/<channel>`), classifies each post (listing, promo, maintenance, downtime, BTC/market…), and pulls BTC/USD prices from CoinGecko.
- **Customer side (optional)**: `scraper/groups.py` counts daily messages and complaint mentions in community groups using your own Telegram account. It stores counts only, never message text or usernames.

Every scraper run commits new data, and Cloudflare redeploys the site automatically.

## 1. Put it on GitHub

1. Create a new repository on github.com. **Private** is fine.
2. Upload all files from this folder, including the hidden `.github` folder. With git:
   ```
   git init && git add . && git commit -m "first commit"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
3. In the repo, go to **Settings → Actions → General → Workflow permissions** and choose **Read and write permissions**. The scraper needs this to commit data.
4. Go to the **Actions** tab, open **Update Telegram data**, and click **Run workflow** once. After it runs, the seed rows are replaced with real scraped posts.

## 2. Host it on Cloudflare Pages

1. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git**, and pick the repo.
2. Framework preset: **None**. Build command: *(leave empty)*. Build output directory: `/`
3. Deploy. You get a `*.pages.dev` link, and each data commit redeploys it.
4. **To keep it private**: Cloudflare **Zero Trust → Access → Applications**. Add your pages.dev domain and allow only your team's emails (free for up to 50 users).

## 3. Optional: read the community groups

1. Get an API ID and hash at https://my.telegram.org → API development tools.
2. On your own computer:
   ```
   pip install telethon
   TG_API_ID=123 TG_API_HASH=abc python scraper/groups.py --login
   ```
   Log in with your phone code. It prints a long **session string**. Treat it like a password.
3. In GitHub, add three secrets under **Settings → Secrets and variables → Actions**: `TG_API_ID`, `TG_API_HASH`, `TG_SESSION`.
4. Join the groups listed as `"type": "group"` in `data/exchanges.json` with that account.

Without these secrets, the step is skipped and everything else still works.

## Incidents: how they handled it, how customers reacted, how it was solved

With the Telegram secrets set, every run looks for **triggers**: a downtime post in the announcement
channel, or a sudden jump in complaints in a community group. For each one it reads the group from
6 hours before to 48 hours after and saves to `data/<exchange>/incidents.json`:

- when customers started complaining, the first official post, the first admin reply in the group, and when it was solved
- complaints per hour, what customers talked about (withdrawals, fear for funds, compensation…) and a few anonymised lines
- every admin reply, tagged as Acknowledged, Reassurance, ETA, Redirect to support, Scam warning or Resolved

**Past incidents** (e.g. the Oct 2026 Binance hack): in Telegram Desktop open the group → ⋮ → Export chat history →
untick media, format **JSON**, dates around the incident. Then on your PC, in the repo folder:
```
python scraper/import_export.py --exchange binance --group binanceexchange --file "C:\path\to\result.json" --title "Oct 2026 hack"
```
Upload the updated `data/binance/incidents.json` to GitHub. Don't upload the export file itself.

## X (Twitter) accounts

`scraper/x_scrape.py` runs once a day (workflow **Update X data**). It saves each exchange's new X posts
(views, likes, replies) and, for downtime posts from the last 7 days, reads the replies underneath to see
how customers reacted and how fast the exchange replied. Accounts are listed under `"x"` in `data/exchanges.json`.

It uses the official X API, which is **pay-per-use** (no free tier): about $0.005 per post read and
$0.01 per account lookup. Each run stops at `X_MAX_READS` posts (default 300, about $1.50), so the
maximum is roughly $45 a month; on quiet days it reads far less.

Setup:
1. Sign up at **console.x.com**, create a project and app, add credits, and **set a spending limit**.
2. Copy the app's **Bearer Token**.
3. In GitHub: Settings → Secrets and variables → Actions → New repository secret → `X_BEARER_TOKEN`.
4. Optional: under the **Variables** tab add `X_MAX_READS` (e.g. `150` to halve the cost).
5. Actions → **Update X data** → Run workflow.

X only allows searching replies from the past 7 days, so reply analysis builds up from the day you start.

## Status pages (free)

`scraper/status.py` reads public status pages (Statuspage format) for exchanges with a `"status_page"` in
`data/exchanges.json` (Coinbase and Kraken so far). Every outage is stored with its updates, time to identify,
time to resolve, longest silence, and whether an ETA was given. Runs with **Update Telegram data**.

## X for one exchange only

To track only Coinbase on X (a few dollars a month): in GitHub, Settings → Secrets and variables → Actions →
**Variables** tab → New variable `X_ONLY` = `coinbase`. Also add the `X_BEARER_TOKEN` secret.

## Adding X posts by hand (free)

Automatic X scraping isn't allowed by X, and the API costs money. The free, allowed route is copying posts by hand
during an outage:
1. Make a Google Sheet with columns: `exchange, date, who, text, link, incident` (see `data/manual/TEMPLATE_x_posts.csv`).
   - `exchange`: id from `data/exchanges.json` (e.g. `coinbase`)
   - `date`: India time, e.g. `2026-11-16 14:30` or `16/11/2026 14:30`
   - `who`: `exchange` for the exchange's own posts and replies, `customer` for everyone else
   - `incident`: the same name for every row from one outage, e.g. `ETH withdrawals Nov 16`
2. File → Download → CSV. Upload it to `data/manual/` in GitHub (Add file → Upload files).
3. Run **Update app reviews and grouping** (or wait for the next scheduled run).

The X section of that exchange's page then shows the incident: how fast the exchange replied, whether it reassured,
gave an ETA and posted a fix, and what customers complained about. Customer posts are also added to the KNN grouping.
Customer names and @handles are removed automatically; don't copy usernames into the sheet anyway.

## Discord announcement channels (free)

A bot can only read servers it was invited to, so exchange announcements are brought into your own server
with Discord's built-in **Follow** button:
1. Discord → **+ Add a Server → Create My Own**, e.g. "Exchange Watch". Make a text channel per exchange, e.g. `#okx`.
2. discord.com/developers/applications → **New Application** → **Bot** → **Reset Token** and copy it.
   On the same page switch on **Message Content Intent** and save.
3. **OAuth2 → URL Generator** → tick `bot`, then permissions **View Channels** and **Read Message History** →
   open the generated link and add the bot to your server.
4. Join the exchange's official server (e.g. OKX), open its announcement channel (megaphone icon) → **Follow** →
   choose your server and `#okx`.
5. In your Discord: User Settings → Advanced → **Developer Mode** on. Right-click `#okx` → **Copy Channel ID**.
6. In `data/exchanges.json`, under OKX: `"discord": [{"channel_id": "PASTE_ID", "label": "OKX #announcements"}]`.
7. GitHub → Settings → Secrets and variables → Actions → new secret `DISCORD_BOT_TOKEN`.

Community chat channels can't be followed. For those, copy messages from an outage and use `data/manual/` (see above).

## Influencer channels

List public influencer Telegram channels in `data/influencers.json`:
`{"handle": "ScalperTrader02", "name": "Scalper Trader Praveen", "exchange": "coindcx", "region": "india", "discussion": null}`
- `exchange`: the exchange they're linked to (shown in the table); `region`: `india` or `global`.
- `discussion`: the @name of the channel's comment group, if it has one (your Telegram account must join it).

Every run saves their posts with views, reactions (by emoji), which exchanges they name, and whether a post has a
referral link. The **Influencers** tab of each region shows this, plus what they posted within 48 hours of an exchange outage.

## Key findings, AI tagging and history

- **Key findings** (first tab of each region): `scraper/insights.py` writes plain-language findings per exchange and
  per region, plus takeaways for your own handling. Runs after every Telegram and grouping run.
- **AI tagging**: `scraper/voice.py` uses a free multilingual model (paraphrase-multilingual-MiniLM-L12-v2) that
  understands English, Hindi and Hinglish by meaning. Example phrases per category live in `data/label_examples.json`;
  add more to improve it. If the model can't load, it falls back to letter-pattern matching automatically.
- **History**: the first run for each group reads back 30 days; after that each run fetches only new messages.
  Chats are kept for 30 days. The first run takes longer (up to ~40 minutes).

## Hour by hour

`scraper/hourly.py` (runs with every Telegram run) sorts the last 7 days of customer messages into hours and
products (futures, options, spot, INR and crypto deposits/withdrawals, P2P, Earn, listings, bots, app, KYC,
fees, rewards) and flags products talked about far more than usual in the last 3 hours. Each exchange page shows
it as a heatmap; click a cell to read what people said. Product keywords are in `PRODUCTS` in `scraper/incidents.py`.
How fresh it is depends on how often the Telegram job runs (every 2 hours is a good balance on a private repo).

## Everyday use (no Claude needed)

| You want to… | Edit |
|---|---|
| Add or remove a channel | `data/exchanges.json`. Set `"scrape": true` for announcement channels |
| Add a new exchange | Add it to `exchanges.json` and create `data/<id>/` with the five JSON files (copy an empty one) |
| Tune how posts are classified | `scraper/categorize.py` → `RULES` (regex, first match wins) |
| Fix one post's category by hand | In `posts.json`, set `"category"` and add `"category_manual": true` so the scraper keeps it |
| Add downtime timelines, ratings, customer quotes, lessons | `events.json`, `scorecard.json`, `voices.json`, `lessons.json` in `data/<id>/` (same fields as the Binance files) |
| Scrape further back in history | Change `--pages 5` in `.github/workflows/scrape.yml` (each page ≈ 20 posts) |

Preview locally: `python -m http.server 8000`, then open http://localhost:8000. Opening `index.html` directly won't load the data.

Run tests: `pip install -r scraper/requirements.txt pytest && pytest scraper/tests`

## Notes and limits

- Only **public channels** have web previews. Groups need the optional step 3.
- Telegram can change its preview HTML. If posts stop appearing, check `parse_page()` in `scraper/scrape.py` and the test fixture.
- CoinGecko's free API is rate-limited. If a run is refused, old prices are kept and the next run fills the gap.
- Coinbase has no official Telegram (only Coinbase Italia), so it is tracked with that channel plus hand-written research.
- If the site is public, everything in `data/` is public too. Use Cloudflare Access to keep it internal.
