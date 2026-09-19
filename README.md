# Hypixel Bedwars Stats Tracker

**TL;DR:** A Python and Flask app that saves snapshots of Hypixel Bedwars player stats and shows them in a browser dashboard, so you can track how you and your friends improve over time. You need a [Hypixel API key](#get-a-hypixel-api-key).

```
git clone https://github.com/dancingstreetlight/bedwars_pipeline.git
cd bedwars_pipeline
python -m pip install -r requirements.txt
python server.py
```

Then open http://127.0.0.1:8000, paste your API key, enter a username, and press **Fetch latest stats**.

Track Hypixel Bedwars stats for you and your friends, and see how they change over time.

Every time you fetch, the app saves a snapshot of each player's stats. Because Hypixel only exposes current numbers, those snapshots are the only way to build a history. The dashboard turns them into a leaderboard, progress charts, and a data quality report.

Individual player data is stored in `bedwars_pipeline\data\raw`

## Features

* Leaderboard with level, games played, win rate, WLR, FKDR, KDR and BBLR. Click any column header to sort.
* Bar chart to compare players on any metric.
* History tab with a line chart per player and a table of what changed between snapshots.
* Data quality tab showing how many snapshots passed validation and which were quarantined.
* Works from the browser or the command line.
* Plain HTML, CSS and JavaScript frontend. No frontend frameworks.

## What you need

* Python 3 (3.10 or newer recommended)
* A Hypixel API key
* An internet connection (the charts load Chart.js from a CDN)

## Get a Hypixel API key

1. Go to https://developer.hypixel.net and sign in with your Hypixel account.
2. Create a key from the dashboard.
3. Read their current rules and rate limits. Keys, limits and policies can change, and development keys may expire, so check the site if requests start failing.

## Install

Clone the repo and install the dependencies.

```
git clone https://github.com/dancingstreetlight/bedwars_pipeline.git
cd bedwars_pipeline
python -m pip install -r requirements.txt
```

On Mac or Linux, use `python3` in place of `python`.


## Run the dashboard

```
python server.py
```

Open http://127.0.0.1:8000 in your browser.

1. Enter one or more Minecraft usernames (up to 10, separated by spaces, commas or new lines).
2. Press **Fetch latest stats**.
3. Come back later, play some games, and fetch again. The History tab fills in once a player has two or more snapshots.

The server only listens on your own machine. It is built for local use and has no login, so do not expose it to the internet.

## Use it from the command line

The dashboard is optional. The pipeline runs on its own:

```
python pipeline.py ingest Name1 Name2
python pipeline.py transform
```

`ingest` saves fresh snapshots. `transform` rebuilds the clean and metrics layers and prints a table sorted by FKDR. To build a real history without opening the page, schedule the `ingest` command with Windows Task Scheduler or cron.

## What the metrics mean

| Metric | Formula |
| --- | --- |
| WLR | wins divided by losses |
| FKDR | final kills divided by final deaths |
| KDR | kills divided by deaths |
| BBLR | beds broken divided by beds lost |
| Win rate | wins divided by games played |

If the denominator is zero, it is treated as 1, which is the usual Bedwars convention.

## How it works

```
Mojang API + Hypixel API
        |
   Raw:     untouched JSON snapshots, one file per player per fetch (append only)
        |
   Clean:   flattened, typed rows. Duplicates removed. Bad rows quarantined.
        |
   Metrics: lifetime stats and change between snapshots
        |
   Flask JSON API  ->  HTML / CSS / JavaScript dashboard
```

This is the same layered idea that data platforms call Bronze, Silver and Gold (the medallion pattern). Keeping the raw data means you can fix a cleaning rule or add a metric later and rebuild everything without calling the API again.

Files are written to:

```
data/raw/<player uuid>/<timestamp>.json
data/clean/bedwars_snapshots.parquet
data/clean/quarantine.parquet
data/metrics/player_summary.parquet
data/metrics/player_progress.parquet
```

### Data quality rules

A snapshot is quarantined, not silently dropped, if:

* the player UUID is missing,
* any counter is negative or unreadable,
* wins are greater than games played.

## Project layout

```
pipeline.py        Raw, clean and metrics logic. Also a command line tool.
server.py          Flask server: serves the frontend and a small JSON API.
static/            index.html, style.css, app.js (served to the browser as is)
test_pipeline.py   Tests for the pipeline logic
test_server.py     Tests for the API
requirements.txt   Python dependencies
```

The `static` folder is separate from the Python files on purpose. The server only hands out what is inside it, so your code and any local config files are never downloadable from the browser.

## JSON API

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/dashboard` | Everything the page renders: summary, history, progress, data quality |
| POST | `/api/fetch` | Fetch and save snapshots. Body: `{"usernames": ["Name1", "Name2"]}`. Optional header `X-Hypixel-Key`. |
| GET | `/api/config` | Whether the server already has an API key |

## Run the tests

```
python -m pytest
```

The tests cover the metric maths, flattening and validation, and the API routes. Network calls are replaced with stand ins, so no API key is needed.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `pip` is not recognized | Use `python -m pip install -r requirements.txt` (or `py -m pip` on Windows). |
| The page shows 404 | The `static` folder must sit next to `server.py` and contain `index.html`, `style.css` and `app.js`. |
| "No API key" error | Set `HYPIXEL_API_KEY` or paste the key into the page. |
| 403 from Hypixel | The key is invalid or expired. Generate a new one. |
| 429 from Hypixel | You hit the rate limit. Wait a few minutes and fetch fewer players. |
| "Skipped Name: no such Minecraft account" | Check the spelling of the username. |
| Port 8000 already in use | Change the port at the bottom of `server.py`. |
| Charts do not appear | Check your internet connection. The tables still work without it. |

## Limitations

* Only overall Bedwars stats are tracked, not per mode.
* History starts from your first fetch. Older stats are not available from the API.
* Stats can only be fetched for players Hypixel has data for.

## Credits and disclaimer

Data comes from the Hypixel public API and the Mojang API. Charts use [Chart.js](https://www.chartjs.org). This project is not affiliated with or endorsed by Hypixel or Mojang.
