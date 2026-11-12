# RTYB — Run to Your Bets

Static site on GitHub Pages, built by `scripts/build_site.py` and rebuilt by the
refresh job (`.github/workflows/refresh.yml`) every 10 minutes. Tests:
`python3 -m unittest discover -s tests`.

## Sport families

- Every page change applies to every sport through the shared config
  (`scripts/sports.py`: `FAMILY`, `FAMILY_MARKETS`, `calendar`) and the shared
  templates, in the same session. Never build a feature for one sport only.
- Period family: NHL, MLB. Spread family: NBA, WNBA, NCAAB, NFL, NCAAF.
- 3-way ML exists for NHL only (no 3-way tab, record or data anywhere else,
  including MLB's F5).
  Weekly: NFL, NCAAF (date bars, calendars and day records become weeks).
- If a change can't apply to a sport (missing data, or a market that doesn't
  exist there), say so in the summary instead of skipping it silently.
- Hidden sports (`launched: False`) stay out of menus and noindexed, but get
  every new layout so they're ready the day they're switched on. Off-season
  sports must render from last season's data.

## Naming rule (every page)

- Pro sports (NHL, NBA, WNBA, NFL, MLB): desktop shows the team nickname
  (Lightning, Celtics); mobile shows the abbreviation (TB, BOS).
- College sports (NCAAB, NCAAF): desktop shows the school name (Kentucky,
  Arizona), never the nickname; mobile shows the school abbreviation (UK, ARIZ).
- Inside cards, odds rows and records: abbreviations on every device.
- Every team shows its logo (scripts/fetch_sport_logos.py also fetches the
  non-Division I opponents'). No logo: a small colored badge with the
  abbreviation.
- Green means "best price" everywhere on the site and nothing else
  (`--best` in template.html; wins and positive units use `--good`, blue).
