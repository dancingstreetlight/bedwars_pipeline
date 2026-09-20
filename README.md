# Hypixel Bedwars Stats Tracker

**TL;DR:**

A Python and Flask app that pulls Hypixel Bedwars stats and shows them in a browser dashboard. Look up players instantly, or tick **Save snapshot** to keep a history and track how you and your friends improve over time. You need a [Hypixel API key](#get-a-hypixel-api-key).

[Demo](https://bedwars-pipeline.vercel.app/) (outdated already but should give you a general understanding)

Open your terminal then paste these commands

```
git clone https://github.com/dancingstreetlight/bedwars_pipeline.git
cd bedwars_pipeline
python -m pip install -r requirements.txt
python server.py
```

Then open http://127.0.0.1:8000, paste your API key, enter a username, and press **Fetch latest stats**.

## Two ways to fetch

The **Save snapshot to the data folder** checkbox decides what happens when you press Fetch.

| Mode | Checkbox | What happens |
| --- | --- | --- |
| Live view | Unticked (default) | Stats are fetched and shown right away. Nothing is written to disk, and a page refresh clears them. |
| Saved snapshot | Ticked | Stats are shown and a snapshot is saved to `data/`. It survives refreshes and builds up history over time. |

Hypixel only exposes current numbers, so saved snapshots are the only way to build a history. Progress over time (the History tab and the change between snapshots) needs saved snapshots. Live view is best for a quick check on a player.

In live view, looking up the same player again within 2 minutes reuses the last result from memory, which keeps you under the Hypixel rate limit.

Individual player data is stored in `bedwars_pipeline/data/raw` only when you save.

## Features

* Leaderboard with level, games, wins, losses, win rate, WLR, final kills, final deaths, FKDR, kills, deaths, KDR, beds broken, beds lost and BBLR. Every stat shows the raw total as well as the ratio. Click any column header to sort.
* Game mode buttons to switch every table and chart between Overall, Solo, Doubles, 3s and 4s.
* Bar chart to compare players on any metric.
* History tab with a line chart per player and a table of what changed between snapshots (saved snapshots only).
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

1. Paste your Hypixel API key. The page needs it every time, and it is only sent to your own local server, never stored.
2. Enter one or more Minecraft usernames (up to 10, separated by spaces, commas or new lines).
3. Tick **Save snapshot to the data folder** if you want to keep the result. Leave it unticked for a live view only.
4. Press **Fetch latest stats**.
5. Use the game mode buttons (Overall, Solo, Doubles, 3s, 4s) to switch between modes.

To build a history, tick the checkbox, come back later, play some games, and fetch again. The History tab fills in once a player has two or more saved snapshots.

The server only listens on your own machine. It is built for local use and has no login, so do not expose it to the internet.

## Use it from the command line

The dashboard is optional. The pipeline runs on its own, and the command line always saves snapshots. It reads your key from the `HYPIXEL_API_KEY` environment variable:

```
export HYPIXEL_API_KEY=your_key_here     (Windows PowerShell: $env:HYPIXEL_API_KEY="your_key_here")
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

If the denominator is zero, it is treated as 1, which is the usual Bedwars convention. The raw totals (wins, losses, final kills and so on) are shown next to each ratio.

## Game modes

Stats are split using Hypixel's per mode fields:

| Button | Hypixel mode |
| --- | --- |
| Overall | All Bedwars modes combined |
| Solo | Solo (8 teams of 1) |
| Doubles | Doubles (8 teams of 2) |
| 3s | Trios (4 teams of 3) |
| 4s | Fours (4 teams of 4) |

Level is the same in every mode, because Hypixel only keeps one Bedwars level per player. Other variants such as 4v4, Rush and Ultimate are not split out.

## How it works

```
Mojang API + Hypixel API
        |
        +--- Live view (checkbox off) ---> clean and metrics in memory ---> dashboard
        |
   Raw:     untouched JSON snapshots, one file per player per fetch (append only)
        |     (saved only when the checkbox is ticked)
        |
   Clean:   flattened, typed rows. Duplicates removed. Bad rows quarantined.
        |
   Metrics: lifetime stats and change between snapshots
        |
   Flask JSON API  ->  HTML / CSS / JavaScript dashboard
```

This is the same layered idea that data platforms call Bronze, Silver and Gold (the medallion pattern). Keeping the raw data means you can fix a cleaning rule or add a metric later and rebuild everything without calling the API again.

Live view runs the same cleaning and metrics logic, but only in memory, so nothing is written.

Files are written to the following paths, and only when you save a snapshot:

```
data/raw/<player uuid>/<timestamp>.json
data/clean/bedwars_snapshots.parquet
data/clean/quarantine.parquet
data/metrics/player_summary.parquet
data/metrics/player_progress.parquet
```

The metrics files cover Overall stats. The other game modes are calculated from the clean snapshots each time the page loads.

### Data quality rules

A snapshot is quarantined, not silently dropped, if:

* the player UUID is missing,
* any counter (overall or in any game mode) is negative or unreadable,
* wins are greater than games played, overall or in any game mode.

The Data quality tab shows the results for whatever you are currently viewing: your saved snapshots, or the latest live fetch.

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

Both fetch routes need the header `X-Hypixel-Key` and a body like `{"usernames": ["Name1", "Name2"]}`.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/dashboard` | Everything the page renders from saved data: per mode summary, history and progress, plus data quality |
| POST | `/api/fetch` | Fetch and save snapshots to the data folder |
| POST | `/api/live` | Fetch and return the dashboard data without writing anything to disk |

## Run the tests

```
python -m pytest
```

The tests cover the metric maths, flattening and validation, game mode splitting, live view (including that it writes no files), and the API routes. Network calls are replaced with stand ins, so no API key is needed.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `pip` is not recognized | Use `python -m pip install -r requirements.txt` (or `py -m pip` on Windows). |
| The page shows 404 | The `static` folder must sit next to `server.py` and contain `index.html`, `style.css` and `app.js`. |
| "Enter your Hypixel API key" | Paste the key into the API key box on the page. The dashboard does not read the environment variable. |
| 403 from Hypixel | The key is invalid or expired. Generate a new one. |
| 429 from Hypixel | You hit the rate limit. Wait a few minutes and fetch fewer players. |
| "Skipped Name: no such Minecraft account" | Check the spelling of the username. |
| "Nothing could be fetched" | Every name failed. The message lists the reason for each one. |
| History tab is empty or has one point | History needs saved snapshots. Tick **Save snapshot** and fetch at least twice. |
| Stats vanish when the page refreshes | You used live view. Tick **Save snapshot** to keep them. |
| Port 8000 already in use | Change the port at the bottom of `server.py`. |
| Charts do not appear | Check your internet connection. The tables still work without it. |

## Limitations

* Game modes covered are Overall, Solo, Doubles, 3s and 4s. Other variants are not tracked.
* History starts from your first saved snapshot. Older stats are not available from the API.
* Live view has no history, since nothing is saved.
* Stats can only be fetched for players Hypixel has data for.

## Credits and disclaimer

Data comes from the Hypixel public API and the Mojang API. Charts use [Chart.js](https://www.chartjs.org). This project is not affiliated with or endorsed by Hypixel or Mojang.
