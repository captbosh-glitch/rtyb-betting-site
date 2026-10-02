"""
Merge everything into the final embedded data blob and write the site's
generated pages.

Inputs (all relative to repo root, where this runs from in CI):
  base_data.json          -- static: summary / streaks / gamelog (season stats,
                              baked once from the archived season file; not
                              refetched every run)
  schedule_fresh.json      -- freshly fetched this run by fetch_schedule.py
  schedule_data.json      -- the PREVIOUSLY COMMITTED schedule (if any) --
                              read here (not overwritten by fetch_schedule.py)
                              so closing odds already saved on now-completed
                              games survive even once an odds API stops
                              returning them for a finished game.
  odds_theoddsapi.json    -- fresh 1P moneyline + totals, keyed "date|away|home"
  odds_sportsgameodds.json -- fresh 1P BTTS yes price, same key shape
  template.html           -- shared site shell (head/nav/CSS/JS) with
                              per-page content marked off with
                              <!-- PAGE:<key> --> ... <!-- /PAGE:<key> -->
                              blocks, so one template drives every generated
                              page without duplicating markup or JS. The
                              client JS fetches the shared nhl/data.json
                              blob (below) at load time rather than reading
                              it out of an inline <script> tag.

Output (all static files -- no server, GitHub Pages "deploy from branch,
root" compatible):
  index.html               -- root redirect to /nhl/games/
  nhl/data.json             -- the full merged data blob (summary/streaks/
                              gamelog/schedule/divisions for all teams),
                              written ONCE and fetched by every generated
                              page's client JS, instead of being inlined
                              into each page individually.
  nhl/games/index.html     -- the Games page (landing page)
  nhl/hit-rates/index.html -- the Hit Rates page (formerly "Standings")
  schedule_data.json       -- OVERWRITTEN with the merged result, so the next
                              run's "previous" read carries forward saved odds

nhl/trends/ and nhl/teams/ are NOT built here yet -- phase 2. The nav and
game-card links already point at their final URLs (/nhl/trends/,
/nhl/teams/<slug>/) so they'll light up once those pages exist; a
generic team-slug scheme is used consistently: the team's DATA code,
lowercased (e.g. "TOR" -> "tor").
"""
import html as html_lib
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAGE_BLOCK_RE = re.compile(r'<!--\s*PAGE:(\w+)\s*-->(.*?)<!--\s*/PAGE:\1\s*-->', re.DOTALL)
TEAM_COLOR_RE = re.compile(r"(\w+):\s*'(#[0-9A-Fa-f]{6})'")

PAGE_META = {
    'games': {
        'title': 'RTYB — NHL Games',
        'h1': 'NHL — Games',
        'desc': ('First-period matchups, odds, and season hit rates for every NHL game day. '
                  'Pick a date above to see that day’s card.'),
    },
    'hitrates': {
        'title': 'RTYB — Hit Rates',
        'h1': 'NHL — Hit Rates',
        'desc': ('Historical 1st-period results by team for the 2025–26 season. '
                  'Pick a market, split by home/away, and tap any team for the full trend and game log.'),
    },
    'trends': {
        'title': 'RTYB — Hottest Trends',
        'h1': 'NHL — Hottest Trends',
        'desc': ('Active streaks and extreme season rates across Moneyline, Over-Under 1.5, and BTTS. '
                  'Scoped to tonight’s teams by default.'),
    },
    'teamsindex': {
        'title': 'RTYB — Teams',
        'h1': 'NHL — Teams',
        'desc': 'Every NHL team, grouped by division, with season Over-Under 1.5 and BTTS rates.',
    },
}

# 2025-26 NHL division alignment. Hardcoded here since base_data.json does not
# carry division info and this essentially never changes mid-season (phase 2
# spec explicitly allows this fallback).
TEAM_DIVISIONS = {
    'Atlantic': ['BOS', 'BUF', 'DET', 'FLA', 'MON', 'OTT', 'TB', 'TOR'],
    'Metropolitan': ['CAR', 'CBJ', 'NJ', 'NYI', 'NYR', 'PHI', 'PIT', 'WSH'],
    'Central': ['CHI', 'COL', 'DAL', 'MIN', 'NSH', 'STL', 'UTA', 'WPG'],
    'Pacific': ['ANH', 'CGY', 'EDM', 'LA', 'SJ', 'SEA', 'VAN', 'VGK'],
}


def team_page_meta(code, name):
    return {
        'title': 'RTYB — ' + name,
        'h1': name,
        'desc': ('1st-period Moneyline, Over-Under 1.5, and BTTS rates, home/away splits, last 10 games, '
                  'and current trends for the ' + name + '.'),
    }


def load(path, default):
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return default
    with open(full, encoding='utf-8') as f:
        return json.load(f)


def strip_pages(template, target_page):
    """Keep only the <!-- PAGE:<target_page> --> blocks (unwrapped); drop
    every other page's blocks entirely. Content outside any PAGE block
    (head, nav, footer, shared JS, etc.) is shared and always kept."""
    def repl(m):
        return m.group(2) if m.group(1) == target_page else ''
    return PAGE_BLOCK_RE.sub(repl, template)


def extract_team_true_colors(template):
    """Pull the JS TEAM_TRUE_COLOR map out of template.html so the Python
    build and the client JS never drift out of sync on team brand colors."""
    m = re.search(r'var TEAM_TRUE_COLOR = \{(.*?)\};', template, re.DOTALL)
    if not m:
        return {}
    return dict(TEAM_COLOR_RE.findall(m.group(1)))


def team_slug(code):
    # Team page URL slug scheme (phase 2 must match this exactly):
    # the team's DATA code, lowercased. e.g. "TOR" -> "tor", "NYR" -> "nyr".
    return code.lower()


def build_teams_menu_html(summary, team_colors):
    # Nav dropdown logos: rendered here as static HTML (this menu is built
    # once at build time, not re-rendered client-side), so the correct
    # light/dark variant is picked up -- and kept in sync on a theme
    # toggle -- by the shared updateNavTeamLogos() JS helper in
    # template.html, which matches on the .nav-team-logo[data-code] hook
    # below.
    #
    # IMPORTANT: this <img> deliberately has NO "src" attribute (only
    # data-code). If it had one, the browser starts fetching it the instant
    # the HTML parser creates the tag -- before ANY <script> later in the
    # document gets a chance to run, no matter how early that script calls
    # updateNavTeamLogos(). Since this site is hosted as a GitHub Pages
    # project site under a subpath, a root-relative src baked in here at
    # build time would be wrong (missing that subpath) and there's no way
    # for JS to "fix" it before the wrong request has already fired. Every
    # OTHER part of this site already requires JS anyway (the page is empty
    # without it -- see the "Loading data..." state), so there's no
    # meaningful no-JS case to preserve a static src for; JS sets the real,
    # correctly-prefixed src on first run instead (updateNavTeamLogos(),
    # called unconditionally at script start, not just on theme toggle).
    teams = sorted(summary.items(), key=lambda kv: kv[1]['name'])
    items = []
    for code, info in teams:
        name = html_lib.escape(info['name'])
        items.append(
            '<a class="nav-dropdown-item" href="/nhl/teams/{slug}/">'
            '<span class="team-logo-wrap nav-team-logo-wrap" style="width:20px;height:20px">'
            '<img class="nav-team-logo" data-code="{code}" '
            'width="20" height="20" alt="{name} logo" '
            'onerror="window.rtybLogoFallback(this,\'{code}\',20)"></span>'
            '{name}</a>'.format(
                slug=team_slug(code), name=name, code=code
            )
        )
    items.append('<a class="nav-dropdown-item nav-dropdown-item--all" href="/nhl/teams/">All Teams &rarr;</a>')
    return ''.join(items)


def render_page(template, page_key, teams_menu_html, meta=None, team_code=''):
    out = strip_pages(template, page_key)
    meta = meta or PAGE_META[page_key]
    out = out.replace('__PAGE_TITLE__', meta['title'])
    out = out.replace('__PAGE_H1__', meta['h1'])
    out = out.replace('__PAGE_DESC__', meta['desc'])
    out = out.replace('__NAV_GAMES_CURRENT__', 'aria-current="page"' if page_key == 'games' else '')
    out = out.replace('__NAV_HITRATES_CURRENT__', 'aria-current="page"' if page_key == 'hitrates' else '')
    out = out.replace('__NAV_TRENDS_CURRENT__', 'aria-current="page"' if page_key == 'trends' else '')
    out = out.replace('__NAV_TEAMS_CURRENT__', 'aria-current="page"' if page_key in ('teamsindex', 'team') else '')
    out = out.replace('__TEAMS_MENU_ITEMS__', teams_menu_html)
    out = out.replace('__PAGE_TEAM_CODE__', team_code)
    return out


# NOTE: every href/src in this redirect page is deliberately RELATIVE
# ("nhl/games/", no leading slash) rather than root-relative ("/nhl/games/").
# This site is hosted as a GitHub Pages *project* site under a subpath (e.g.
# /rtyb-betting-site/), not at the domain root, so a root-relative link here
# would resolve to the wrong place entirely (the bare domain root, where
# nothing is published) -- exactly the "no GitHub Pages site here" 404 this
# fix addresses. A relative link always resolves against wherever this file
# itself is actually being served from, so it's correct both here (local
# testing at the domain root) and in production (served under the repo's
# subpath) with no runtime detection needed. Every OTHER page in the site is
# nested one level under /nhl/, where a small JS snippet at the top of
# template.html's <script> block detects the real subpath at runtime instead
# (see SITE_ROOT there) -- this file is the one exception, since it sits at
# the true site root with no "/nhl/" segment in its own URL to detect from.
ROOT_REDIRECT_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0; url=nhl/games/">
<link rel="canonical" href="nhl/games/">
<title>RTYB</title>
<script>location.replace('nhl/games/');</script>
</head>
<body>
<p>Redirecting to <a href="nhl/games/">nhl/games/</a>&hellip;</p>
</body>
</html>
"""


def apply_admin_overrides(merged_games, odds_overrides, results_overrides):
    """Admin-published values (from the Admin page's Matchups Tool / Results
    Tool, committed by the Cloudflare Worker to data_admin/odds_overrides.json
    and data_admin/results_overrides.json) always win over whatever the
    automated odds/schedule fetchers found -- that's the point of publishing
    them by hand. Keyed the same way as odds_theoddsapi.json/
    odds_sportsgameodds.json: "date|away|home".

    Results overrides set awayP1/homeP1 directly -- these are 1st-period
    markets, so a published result is meaningful (and gradeable) the moment
    the admin enters it, independent of whether the full game has finished
    in the NHL's own feed yet."""
    for date_str, games in merged_games.items():
        for i, g in enumerate(games):
            key = f'{date_str}|{g["away"]}|{g["home"]}'
            odds_patch = odds_overrides.get(key)
            results_patch = results_overrides.get(key)
            if not odds_patch and not results_patch:
                continue
            g = dict(g)
            if odds_patch:
                odds = dict(g.get('odds') or {})
                odds.update(odds_patch)
                g['odds'] = odds
            if results_patch:
                g['awayP1'] = results_patch.get('awayP1')
                g['homeP1'] = results_patch.get('homeP1')
            games[i] = g


def main():
    base = load('base_data.json', {'summary': {}, 'streaks': {}, 'gamelog': {}})
    fresh_schedule = load('schedule_fresh.json', {'gameCounts': {}, 'games': {}})
    prev_schedule = load('schedule_data.json', {'gameCounts': {}, 'games': {}})
    odds_oddsapi = load('odds_theoddsapi.json', {})
    odds_sgo = load('odds_sportsgameodds.json', {})
    odds_overrides = load('data_admin/odds_overrides.json', {})
    results_overrides = load('data_admin/results_overrides.json', {})

    prev_games_by_id = {}
    for date_str, games in prev_schedule.get('games', {}).items():
        for g in games:
            if g.get('id') is not None:
                prev_games_by_id[g['id']] = g

    merged_games = {}
    for date_str, games in fresh_schedule.get('games', {}).items():
        merged_list = []
        for g in games:
            key = f'{date_str}|{g["away"]}|{g["home"]}'
            odds = {}

            oa = odds_oddsapi.get(key)
            if oa:
                if oa.get('ml'):
                    odds['ml'] = oa['ml']
                if oa.get('totals'):
                    odds['totals'] = {
                        line: {'over': prices.get('over'), 'under': prices.get('under')}
                        for line, prices in oa['totals'].items()
                    }
            sgo = odds_sgo.get(key)
            if sgo and sgo.get('btts_yes') is not None:
                odds['btts_yes'] = sgo['btts_yes']
            if sgo and sgo.get('btts_no') is not None:
                odds['btts_no'] = sgo['btts_no']

            # Carry forward previously-saved odds for a now-completed game if
            # this run's odds fetch didn't return anything fresh for it (the
            # normal case once a game has ended -- odds feeds stop covering it).
            if not odds and g.get('id') in prev_games_by_id:
                prev_odds = prev_games_by_id[g['id']].get('odds')
                if prev_odds:
                    odds = prev_odds

            if odds:
                g = dict(g)
                g['odds'] = odds
            merged_list.append(g)
        merged_games[date_str] = merged_list

    # If this run had no fresh schedule at all (e.g. schedule_fresh.json
    # missing, as in a local/manual build), fall back to the previously
    # committed schedule so the site still has data to render.
    if not merged_games and prev_schedule.get('games'):
        merged_games = prev_schedule['games']
        merged_game_counts = prev_schedule.get('gameCounts', {})
    else:
        merged_game_counts = fresh_schedule.get('gameCounts') or prev_schedule.get('gameCounts', {})

    # Applied unconditionally, after either path above, so admin-published
    # odds/results always take effect -- including on a local/manual build
    # with no fresh schedule fetch.
    apply_admin_overrides(merged_games, odds_overrides, results_overrides)

    merged_schedule = {
        'gameCounts': merged_game_counts,
        'games': merged_games,
    }

    # Persist the merged schedule so the NEXT run's "previous" read has
    # today's closing odds saved on it. Location/shape unchanged -- other
    # scripts depend on this.
    with open(os.path.join(ROOT, 'schedule_data.json'), 'w', encoding='utf-8') as f:
        json.dump(merged_schedule, f, separators=(',', ':'))

    full_data = dict(base)
    full_data['schedule'] = merged_schedule
    # Restrict divisions to teams actually present in base_data.json's summary
    # (keeps the Teams page grid in sync if a team code ever changes).
    known_codes = set(base.get('summary', {}).keys())
    full_data['divisions'] = {
        div: [c for c in codes if c in known_codes]
        for div, codes in TEAM_DIVISIONS.items()
    }
    data_json = json.dumps(full_data, separators=(',', ':'))

    template_path = os.path.join(ROOT, 'template.html')
    with open(template_path, encoding='utf-8') as f:
        template = f.read()

    team_colors = extract_team_true_colors(template)
    teams_menu_html = build_teams_menu_html(full_data.get('summary', {}), team_colors)

    games_html = render_page(template, 'games', teams_menu_html)
    hitrates_html = render_page(template, 'hitrates', teams_menu_html)
    trends_html = render_page(template, 'trends', teams_menu_html)
    teamsindex_html = render_page(template, 'teamsindex', teams_menu_html)

    nhl_dir = os.path.join(ROOT, 'nhl')
    games_dir = os.path.join(ROOT, 'nhl', 'games')
    hitrates_dir = os.path.join(ROOT, 'nhl', 'hit-rates')
    trends_dir = os.path.join(ROOT, 'nhl', 'trends')
    teams_dir = os.path.join(ROOT, 'nhl', 'teams')
    os.makedirs(nhl_dir, exist_ok=True)
    os.makedirs(games_dir, exist_ok=True)
    os.makedirs(hitrates_dir, exist_ok=True)
    os.makedirs(trends_dir, exist_ok=True)
    os.makedirs(teams_dir, exist_ok=True)

    # The full merged data blob is written ONCE to a single shared static
    # file (rather than inlined into every generated page -- that used to
    # balloon each page to ~550-575KB and the whole site to ~20MB, and the
    # auto-refresh workflow re-commits it every 10 minutes). Every page's
    # client JS fetches this same file at load time instead. It's referenced
    # by every page as "/nhl/data.json" -- like every other internal link in
    # this file, that's root-relative, not a true relative path, since this
    # is a shared file stamped onto pages at different folder depths. It
    # works because template.html's client JS detects the real GitHub Pages
    # project-site subpath at runtime (SITE_ROOT) and prefixes it before
    # fetching -- see the comment at the top of that file's <script> block.
    with open(os.path.join(nhl_dir, 'data.json'), 'w', encoding='utf-8') as f:
        f.write(data_json)

    with open(os.path.join(games_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(games_html)
    with open(os.path.join(hitrates_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(hitrates_html)
    with open(os.path.join(trends_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(trends_html)
    with open(os.path.join(teams_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(teamsindex_html)
    with open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(ROOT_REDIRECT_HTML)

    team_bytes = 0
    for code, info in full_data.get('summary', {}).items():
        slug = team_slug(code)
        meta = team_page_meta(code, info['name'])
        team_html = render_page(template, 'team', teams_menu_html, meta=meta, team_code=code)
        team_dir = os.path.join(teams_dir, slug)
        os.makedirs(team_dir, exist_ok=True)
        with open(os.path.join(team_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(team_html)
        team_bytes += len(team_html)

    print(f"wrote index.html (redirect), nhl/data.json ({len(data_json)} bytes), "
          f"nhl/games/index.html ({len(games_html)} bytes), "
          f"nhl/hit-rates/index.html ({len(hitrates_html)} bytes), "
          f"nhl/trends/index.html ({len(trends_html)} bytes), "
          f"nhl/teams/index.html ({len(teamsindex_html)} bytes), "
          f"{len(full_data.get('summary', {}))} nhl/teams/<slug>/index.html pages ({team_bytes} bytes total), "
          f"and schedule_data.json ({sum(len(v) for v in merged_games.values())} games)")


if __name__ == '__main__':
    main()
