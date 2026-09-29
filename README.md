# RTYB — Run to Your Bets

NHL 1st-period betting stats and trends, auto-refreshed and published as a
static site via GitHub Pages.

## What's in here

- `base_data.json` — season stats (team records, streaks, full game log) baked
  once from the archived 2025–26 season file. This does **not** get refetched
  automatically; it's the historical foundation the live schedule/odds data
  gets merged onto.
- `template.html` — the site itself (HTML/CSS/JS), with a
  `__RTYB_DATA_JSON__` placeholder where the merged data gets embedded at
  build time.
- `scripts/fetch_schedule.py` — pulls real NHL schedule + 1st-period scores
  from the free public `api-web.nhle.com` API (no key needed).
- `scripts/fetch_odds_theoddsapi.py` — pulls 1st-period Moneyline and
  Over/Under prices from [The Odds API](https://the-odds-api.com).
- `scripts/fetch_odds_sportsgameodds.py` — pulls 1st-period BTTS (both teams
  to score) prices from [SportsGameOdds](https://sportsgameodds.com). See the
  note in that file — the exact market key wasn't confirmed from their public
  docs, so the script scans defensively and logs what it finds. **Check the
  first real Actions run's log** (the "Fetch 1P BTTS odds" step) for a line
  starting `INFO: no BTTS-1P oddID matched` — it lists the real oddID keys
  SportsGameOdds actually returned, which tells you whether the heuristic
  matched correctly or needs a tweak.
- `scripts/build_site.py` — merges everything and writes `index.html`. Also
  rewrites `schedule_data.json`, which is what preserves closing odds on
  games that have already finished (odds feeds stop covering a game once
  it's over, so this snapshot is the only record of what the price was).
- `.github/workflows/refresh.yml` — runs the whole pipeline on a schedule.

## One-time setup

1. **Push this repo to GitHub** (already done if you're reading this from
   there).

2. **Add the two API keys as repo secrets** — Settings → Secrets and
   variables → Actions → New repository secret:
   - `ODDS_API_KEY`
   - `SPORTSGAMEODDS_API_KEY`

   Never put these in a file that gets committed — the workflow reads them
   only as environment variables at run time.

3. **Enable GitHub Pages** — Settings → Pages → Build and deployment →
   Source: **Deploy from a branch** → Branch: **main**, folder **/ (root)**.
   Pages will start serving whatever `index.html` is at the repo root, and
   the workflow keeps that file current.

4. **Run the workflow once manually** to seed everything — Actions tab →
   "Refresh RTYB data and publish" → Run workflow. After that it runs itself
   every 10 minutes for schedule/scores. Odds only refresh once an hour (see
   below) — a manual "Run workflow" always fetches odds too, regardless of
   the clock.

Your live URL will be `https://<your-username>.github.io/<repo-name>/`.

## Notes / known gaps

- **Odds refresh once an hour, not every 10 minutes.** Schedule/scores are
  free and unlimited (the NHL API needs no key), but both odds providers'
  free tiers have a limited request quota, and The Odds API's period-scoped
  markets (`h2h_p1`/`totals_p1`) require one request per game per fetch (see
  `fetch_odds_theoddsapi.py`'s docstring) rather than one bulk request — so
  fetching them every 10 minutes would burn through a month's quota in
  hours. The workflow gates the two odds-fetch steps to only run on the run
  landing in the first 10 minutes after the hour; a manual "Run workflow"
  always fetches odds regardless. Tune the gate in `refresh.yml` (the
  "Decide whether this run also fetches odds" step) once you know your
  actual plan limits.
- **BTTS has no price from The Odds API** — they simply don't offer that
  market for hockey (soccer only). SportsGameOdds is the source for that one
  cell specifically; the season hit-rate context next to it is always live
  regardless of odds availability.
- **Historical odds only exist from whenever this pipeline started running.**
  The schedule snapshot this repo ships with (a short hand-verified window
  around late September 2026) has no saved odds — those cells will show
  "—" until the workflow itself has run while those games were upcoming.
- The schedule fetch covers a rolling ±10 day window from "today" (UTC). Widen
  `WINDOW_DAYS_BACK` / `WINDOW_DAYS_FWD` in `fetch_schedule.py` if you want
  the date picker to reach further.
- GitHub disables scheduled workflows automatically after 60 days with no
  repo activity — a manual commit or a `workflow_dispatch` run re-enables it.
