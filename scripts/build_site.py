"""
Merge everything into the final embedded data blob and write the site's
generated pages.

Inputs (all relative to repo root, where this runs from in CI):
  base_data.json          -- static: team names (from the archived 2025-26
                              season file). Its old season stats are no longer
                              published -- summary / streaks / gamelog are
                              rebuilt every run from this season's graded
                              games (SEASON_START onward), see
                              build_season_stats().
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
  index.html, learn/       -- home page and Learn page (scripts/home.py)
  nhl/data.json             -- the full merged data blob (summary/streaks/
                              gamelog/schedule/divisions for all teams),
                              written ONCE and fetched by every generated
                              page's client JS, instead of being inlined
                              into each page individually.
  nhl/games/index.html     -- the Games page (landing page)
  nhl/1st-period-stats/index.html -- the Stats page (formerly "Hit Rates"/"Standings")
  nhl/hit-rates/index.html -- redirect stub to nhl/1st-period-stats/ (old URL)
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
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import account  # noqa: E402
import league_trends  # noqa: E402
import periods  # noqa: E402
import home  # noqa: E402
import icons  # noqa: E402
import sport_build  # noqa: E402
import trend_rules  # noqa: E402
import sports  # noqa: E402

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
        'title': 'RTYB — Stats',
        'h1': 'NHL — Stats',
        'desc': ('League-wide 1st-period results for the 2026–27 regular season (since Sept. 29): '
                  'home/away, favorites/underdogs, Over 1.5 and BTTS, with units.'),
    },
    'trends': {
        'title': 'RTYB — Trends to Watch',
        'h1': 'NHL — Trends to Watch',
        'desc': ('League trends and team trends for today’s games: 1st-period Moneyline, Total 1.5 and BTTS, from the side to bet.'),
    },
    'teamsindex': {
        'title': 'RTYB — Teams',
        'h1': 'NHL — Teams',
        'desc': ('Every team’s 1st-period record, win % and units this season. '
                  'Pick a market, split by home/away, and tap any team for its full page.'),
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


# First day of the 2026-27 regular season. Stats, trends, team pages and
# the Games-page calendar only cover games from this date on -- anything
# earlier is preseason.
SEASON_START = periods.SEASON_START

# Short opponent names for team-page game logs (same style the archived
# season file used).
TEAM_CITY = {
    'ANH': 'Anaheim', 'BOS': 'Boston', 'BUF': 'Buffalo', 'CGY': 'Calgary',
    'CAR': 'Carolina', 'CHI': 'Chicago', 'COL': 'Colorado', 'CBJ': 'Columbus',
    'DAL': 'Dallas', 'DET': 'Detroit', 'EDM': 'Edmonton', 'FLA': 'Florida',
    'LA': 'Los Angeles', 'MIN': 'Minnesota', 'MON': 'Montreal', 'NSH': 'Nashville',
    'NJ': 'New Jersey', 'NYI': 'NY Islanders', 'NYR': 'NY Rangers', 'OTT': 'Ottawa',
    'PHI': 'Philadelphia', 'PIT': 'Pittsburgh', 'SJ': 'San Jose', 'SEA': 'Seattle',
    'STL': 'St. Louis', 'TB': 'Tampa Bay', 'TOR': 'Toronto', 'UTA': 'Utah',
    'VAN': 'Vancouver', 'VGK': 'Vegas', 'WSH': 'Washington', 'WPG': 'Winnipeg',
}


def build_season_stats(merged_games, team_names):
    """summary / streaks / gamelog for every team, from this season's games
    (SEASON_START onward) that have a 1st-period score -- same shapes the
    archived base_data.json used, so the client JS reads them unchanged."""
    def empty_split():
        return {'gp': 0, 'w': 0, 'l': 0, 't': 0, 'o05': 0, 'o15': 0, 'o25': 0, 'btts': 0}

    summary = {code: {'name': name, 'splits': {'Both': empty_split(), 'Home': empty_split(), 'Away': empty_split()}}
               for code, name in team_names.items()}
    gamelog = {code: [] for code in team_names}

    for date_str in sorted(d for d in merged_games if d >= SEASON_START):
        games = sorted(merged_games[date_str], key=lambda g: g.get('startTimeUTC') or '')
        for g in games:
            if g.get('awayP1') is None or g.get('homeP1') is None:
                continue
            total = g['awayP1'] + g['homeP1']
            btts = g['awayP1'] >= 1 and g['homeP1'] >= 1
            for side, code, opp in (('Away', g['away'], g['home']), ('Home', g['home'], g['away'])):
                if code not in summary:
                    continue
                p1t, p1o = (g['awayP1'], g['homeP1']) if side == 'Away' else (g['homeP1'], g['awayP1'])
                ft, fo = (g.get('awayFinal'), g.get('homeFinal')) if side == 'Away' else (g.get('homeFinal'), g.get('awayFinal'))
                for split in (summary[code]['splits']['Both'], summary[code]['splits'][side]):
                    split['gp'] += 1
                    split['w' if p1t > p1o else 'l' if p1t < p1o else 't'] += 1
                    split['o05'] += total > 0
                    split['o15'] += total > 1
                    split['o25'] += total > 2
                    split['btts'] += btts
                odds = g.get('odds') or {}
                ml = odds.get('ml') or {}
                tot = (odds.get('totals') or {}).get('1.5') or {}
                # Prices for the units math on Stats/team pages: this team's
                # moneyline, the Over 1.5 price and the BTTS Yes price.
                gamelog[code].append({
                    'date': date_str, 'side': side, 'opp': TEAM_CITY.get(opp, opp), 'oppCode': opp,
                    'p1t': p1t, 'p1o': p1o, 'ft': ft, 'fo': fo, 'ot': g.get('ot') or '',
                    'ml': ml.get(code), 'overPrice': tot.get('over'), 'bttsYesPrice': odds.get('btts_yes'),
                    'btts': btts,
                })

    def streak(log, result_fn):
        if not log:
            return None, 0
        last = result_fn(log[-1])
        n = 0
        for e in reversed(log):
            if result_fn(e) != last:
                break
            n += 1
        return last, n

    streaks = {}
    for code, log in gamelog.items():
        st = {}
        for key, fn in (
            ('wl', lambda e: 'W' if e['p1t'] > e['p1o'] else 'L' if e['p1t'] < e['p1o'] else 'T'),
            ('o05', lambda e: 'O' if e['p1t'] + e['p1o'] > 0 else 'U'),
            ('o15', lambda e: 'O' if e['p1t'] + e['p1o'] > 1 else 'U'),
            ('o25', lambda e: 'O' if e['p1t'] + e['p1o'] > 2 else 'U'),
            ('btts', lambda e: 'Y' if e['btts'] else 'N'),
        ):
            st[key + '_result'], st[key + '_streak'] = streak(log, fn)
        streaks[code] = st

    return summary, streaks, gamelog


def team_page_meta(code, name):
    return {
        'title': 'RTYB — ' + name,
        'h1': name,
        'desc': ('1st-period Moneyline, Over 1.5, and BTTS records and units, home/away splits, last 10 games, '
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


# Which nav section each page belongs to (for the sport selector, which keeps
# you on the same section when you switch sports).
PAGE_SECTION = {'games': 'games', 'hitrates': 'stats', 'trends': 'trends', 'teamsindex': 'teams', 'team': 'teams', 'empty': None}

# NHL keeps its exact existing text; other sports get generic versions.
NHL_META_DESC = 'RTYB — Run to Your Bets: NHL 1st-period betting stats and trends.'
NHL_FOOTER = ('RTYB &mdash; 2026&ndash;27 regular season, games from Sept. 29 on. Records reflect 1st-period results only; '
              'ties (periods ending level) count as pushes on the Moneyline market. Not affiliated with the NHL.')


# Filled by build_sport_data() before any page renders: per sport, what
# sport_build.build() returned ({season, games, graded, today}).
SPORT_DATA = {}


def sport_has_data(key):
    """Sports with games loaded; the rest show "Soon" in the selector."""
    return key == 'nhl' or (SPORT_DATA.get(key) or {}).get('season') is not None


def build_sport_data():
    """Grade, total up and write {slug}/data.json for every non-NHL sport
    (scripts/sport_build.py), before any page is rendered."""
    for sp in sports.SPORTS:
        if sp['key'] != 'nhl':
            SPORT_DATA[sp['key']] = sport_build.build(sp, load_teams(sp))


# Filled in main() once NHL's data is merged, before any page renders:
# home.sport_statuses(), so every Sports menu matches the home page.
SPORT_STATUS = {}


def sport_menu_html(current, section):
    items = []
    for sp in sports.SPORTS:
        cur = ' aria-current="true"' if sp['key'] == current['key'] else ''
        st = SPORT_STATUS.get(sp['key'])
        if st:
            soon = (f'<span class="nav-status{" live" if st["live"] else ""}">'
                    f'{"LIVE" if st["live"] else html_lib.escape(st["short"])}</span>')
        else:
            soon = '' if sport_has_data(sp['key']) else '<span class="soon">Soon</span>'
        items.append(f'<a class="nav-dropdown-item" href="{sports.section_path(sp, section)}"{cur}>'
                     f'{icons.sport_icon(sp)}{sp["label"]}{soon}</a>')
    return ''.join(items)


# The PH4 logo: stopwatch + RTY with a leaning B, tagline the same width.
# Geometry from the logo sheet; the B position (132.9) and tagline length
# (94.8) were measured in Barlow Condensed 800. Colors are --logo-* tokens.
LOGO_SVG = (
    '<svg class="logo" viewBox="-8 19 176 72" role="img" aria-label="RTYB — Run to Your Bets">'
    '<g class="lg-ring" stroke-width="3" stroke-linecap="round">'
    '<line x1="-6" y1="46" x2="4" y2="46" opacity="0.6"/><line x1="-3" y1="58" x2="4" y2="58" opacity="0.35"/></g>'
    '<rect class="lg-fill" x="25" y="21" width="10" height="6" rx="2"/>'
    '<line class="lg-ring" x1="45.8" y1="36.2" x2="48.9" y2="33.1" stroke-width="3" stroke-linecap="round"/>'
    '<circle class="lg-ring" cx="30" cy="52" r="22" fill="none" stroke-width="3"/>'
    '<path class="lg-fill" d="M30 52 L30 36 A16 16 0 0 1 43.9 44.0 Z" opacity="0.85"/>'
    '<line class="lg-hand" x1="30" y1="52" x2="40.8" y2="43.0" stroke-width="3" stroke-linecap="round"/>'
    '<circle class="lg-dot" cx="30" cy="52" r="3"/>'
    '<text class="lg-rty" x="62" y="68" font-size="50" letter-spacing="1">RTY</text>'
    '<g transform="translate(132.9 68) skewX(-14)"><text class="lg-b" x="0" y="0" font-size="50">B</text></g>'
    '<text class="lg-tag" x="62" y="87" font-size="13" font-weight="700" textLength="94.8" lengthAdjust="spacingAndGlyphs">'
    'RUN TO YOUR <tspan class="lg-bets" font-weight="800">BETS</tspan></text>'
    '</svg>')


def apply_sport(out, sport, section):
    """Fill the sport-specific placeholders shared by every page."""
    is_nhl = sport['key'] == 'nhl'
    out = out.replace('__META_DESC__', NHL_META_DESC if is_nhl else
                      f'RTYB — Run to Your Bets: {sport["label"]} {sports.segment_summary(sport)} betting stats and trends.')
    out = out.replace('__LOGO_SVG__', LOGO_SVG)
    out = out.replace('__SPORT_ICON__', icons.sport_icon(sport))
    out = out.replace('__PAGE_ICON__', icons.sport_icon(sport))
    out = out.replace('__SPORT_KEY__', sport['key'])
    out = out.replace('__SPORT_LABEL__', sport['label'])
    out = out.replace('__SPORT_MENU_ITEMS__', sport_menu_html(sport, section or 'games'))
    out = out.replace('__BRAND_HREF__', '/')  # the home page (prefixed with SITE_ROOT at load)
    out = out.replace('__ACCOUNT__', account.account_html('/'))
    out = out.replace('__ACCOUNT_JS__', account.ACCOUNT_JS)
    for sec in ('games', 'stats', 'trends', 'teams'):
        out = out.replace(f'__NAV_HREF_{sec.upper()}__', sports.section_path(sport, sec))
    if is_nhl:
        footer = NHL_FOOTER
    elif sport_has_data(sport['key']):
        footer = (f'RTYB &mdash; Run to Your Bets. {sport["label"]} {sports.segment_summary(sport)} results; '
                  'odds-based records count only games with saved odds. Not affiliated with any league.')
    else:
        footer = (f'RTYB &mdash; Run to Your Bets. {sport["label"]} {sports.segment_summary(sport)} coverage is coming soon. '
                  'Not affiliated with any league.')
    out = out.replace('__FOOTER_TEXT__', footer)
    out = out.replace('__DATA_PATH__', f'/{sport["slug"]}/data.json')
    out = out.replace('__SPORT_SLUGS_JSON__', json.dumps([sp['slug'] for sp in sports.SPORTS]))
    return out


# Pages for the other sports don't need NHL's page code (~60 KB of script)
# or a private copy of the styles (~90 KB) -- with hundreds of college team
# pages that would add ~100 MB to the site. They share one stylesheet
# (assets/site.css, written by the build from template.html's <style>) and
# run this small script for the nav, menus and theme toggle.
SHELL_JS = """<script>
(function() {
  'use strict';
  var SPORT_SLUGS = __SPORT_SLUGS_JSON__;
  var SITE_ROOT = (function() {
    var best = -1;
    SPORT_SLUGS.forEach(function(slug) {
      var i = location.pathname.indexOf('/' + slug + '/');
      if (i >= 0 && (best < 0 || i < best)) best = i;
    });
    return best >= 0 ? location.pathname.slice(0, best) : '';
  })();
  if (SITE_ROOT) {
    document.querySelectorAll('a[href^="/"]:not([href^="//"])').forEach(function(a) {
      a.setAttribute('href', SITE_ROOT + a.getAttribute('href'));
    });
  }
  try {
    var saved = localStorage.getItem('rtyb-theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
  } catch (e) {}
  document.getElementById('themeToggle').addEventListener('click', function() {
    var cur = document.documentElement.getAttribute('data-theme');
    var isDark = cur ? cur === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    var next = isDark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('rtyb-theme', next); } catch (e) {}
  });
  var btn = document.getElementById('sportBtn'), menu = document.getElementById('sportMenu');
  btn.addEventListener('click', function(e) {
    e.stopPropagation();
    var opening = !menu.classList.contains('open');
    menu.classList.toggle('open', opening);
    btn.setAttribute('aria-expanded', opening ? 'true' : 'false');
  });
  document.addEventListener('click', function(e) {
    if (!menu.contains(e.target)) { menu.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); }
  });
  var hamburger = document.getElementById('hamburgerBtn'), mainNav = document.getElementById('mainNav');
  hamburger.addEventListener('click', function(e) {
    e.stopPropagation();
    var opening = !mainNav.classList.contains('open');
    mainNav.classList.toggle('open', opening);
    hamburger.setAttribute('aria-expanded', opening ? 'true' : 'false');
  });
})();
</script>"""

STYLE_RE = re.compile(r'<style>\n(.*?)\n</style>', re.S)
MAIN_SCRIPT_START = "<script>\n(function() {\n  'use strict';"


def site_css(template):
    return STYLE_RE.search(template).group(1)


def lighten(html, page_dir):
    """Swap the inline styles for the shared stylesheet and NHL's page code
    for SHELL_JS. page_dir is the page's folder relative to the site root."""
    prefix = '../' * len([p for p in page_dir.split('/') if p])
    html = html.replace('<div class="no-games-note" id="rtybLoadNote">Loading data&hellip;</div>', '', 1)
    html = STYLE_RE.sub(lambda m: f'<link rel="stylesheet" href="{prefix}assets/site.css">', html, count=1)
    shell = SHELL_JS.replace('__SPORT_SLUGS_JSON__', json.dumps([sp['slug'] for sp in sports.SPORTS]))
    if 'id="sportApp"' in html:
        # the sport's Situational Results registry (assets/splits/), if it has one
        key = next((sp['key'] for sp in sports.SPORTS if sp['slug'] == page_dir.split('/')[0]), '')
        if os.path.exists(os.path.join(ROOT, 'assets', 'splits', f'{key}.js')):
            shell += f'\n<script src="{prefix}assets/splits/{key}.js"></script>'
        shell += f'\n<script src="{prefix}assets/sport.js"></script>'
        html = html.replace('<body ', f'<body data-sport-slug="{page_dir.split("/")[0]}" ', 1)
    html = html.replace('__ROOT__/', prefix)   # team logo paths (icons.team_logo)
    start = html.rindex(MAIN_SCRIPT_START)
    end = html.index('</script>', start) + len('</script>')
    return html[:start] + shell + html[end:]


def render_page(template, page_key, teams_menu_html, meta=None, team_code='', sport=None, empty_html='', sport_body=''):
    sport = sport or sports.BY_KEY['nhl']
    out = strip_pages(template, page_key)
    section = PAGE_SECTION.get(page_key) or (meta or {}).get('section')
    out = apply_sport(out, sport, section)
    out = out.replace('__EMPTY_HTML__', empty_html)
    out = out.replace('__SPORT_BODY__', sport_body)
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



def redirect_page_html(relative_target):
    """A tiny redirect stub for a URL that moved -- e.g. the old
    /nhl/hit-rates/ now living at /nhl/1st-period-stats/. `relative_target`
    is relative to the redirect page's own folder (both pages sit one level
    under /nhl/, so a sibling rename is just "../new-slug/"), which keeps
    this correct under GitHub Pages' project-site subpath with no runtime
    detection needed."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0; url={relative_target}">
<link rel="canonical" href="{relative_target}">
<title>RTYB</title>
<script>location.replace('{relative_target}');</script>
</head>
<body>
<p>This page moved. Redirecting to <a href="{relative_target}">{relative_target}</a>&hellip;</p>
</body>
</html>
"""


EMPTY_COPY = {
    'games': ('No {label} games yet', 'odds, results and trends'),
    'stats': ('No {label} stats yet', 'records, hit rates and units'),
    'trends': ('No {label} trends yet', 'streaks and league trends'),
    'teams': ('No {label} teams yet', 'team pages with records and splits'),
}


def empty_state_html(sport, section):
    title, what = EMPTY_COPY[section]
    tags = ''.join(f'<span>{seg["tag"]}</span>' for seg in sport['segments'])
    return (f'<h2>{html_lib.escape(title.format(label=sport["label"]))}</h2>'
            f'<p>{sport["label"]} {sports.segment_summary(sport)} {what} are coming to RTYB soon.</p>'
            f'<div class="empty-tags">{tags}</div>')



# ---------- Teams pages for the non-NHL sports (from data_seed/teams/) ----------
def esc(s):
    return html_lib.escape(s or '', quote=True)


def badge_html(team, size=40, sport_key=None):
    """The team's logo (assets/logos/{sport}/) when cached, else a
    team-color circle with the abbreviation, text color picked for contrast."""
    logo = icons.team_logo(sport_key, team['slug'], size, alt='') if sport_key else ''
    if logo:
        return logo
    color = '#' + (team.get('color') or '5B6674')
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    text = '#111111' if lum > 150 else '#FFFFFF'
    code = esc(team['code'])
    fs = max(10, int(size * (0.36 if len(team['code']) <= 3 else 0.3)))
    return (f'<span class="team-badge" style="width:{size}px;height:{size}px;background:{color};color:{text};'
            f'font-size:{fs}px" aria-hidden="true">{code}</span>')


def short_group(name):
    """'American League East' -> 'AL East'; leaves others alone."""
    return (name or '').replace('American League', 'AL').replace('National League', 'NL')


def team_url(sport, team):
    return f"/{sport['slug']}/teams/{team['slug']}/"


def load_teams(sport):
    doc = load(os.path.join('data_seed', 'teams', f"{sport['key']}.json"), None)
    return doc['teams'] if doc else []


TEAM_FILTER_JS = """<script>
(function() {
  var search = document.getElementById('sportTeamSearch');
  var conf = document.getElementById('sportTeamConf');
  var count = document.getElementById('sportTeamCount');
  var none = document.getElementById('sportTeamNone');
  function apply() {
    var q = (search.value || '').trim().toLowerCase();
    var c = conf ? conf.value : '';
    var shown = 0;
    document.querySelectorAll('[data-team-item]').forEach(function(el) {
      var ok = (!q || el.getAttribute('data-search').indexOf(q) !== -1) && (!c || el.getAttribute('data-conf') === c);
      el.hidden = !ok;
      if (ok) shown++;
    });
    document.querySelectorAll('[data-team-group]').forEach(function(g) {
      g.hidden = !g.querySelector('[data-team-item]:not([hidden])');
    });
    if (count) count.textContent = shown + (shown === 1 ? ' team' : ' teams');
    if (none) none.hidden = shown !== 0;
  }
  search.addEventListener('input', apply);
  if (conf) conf.addEventListener('change', apply);
})();
</script>"""


# Divisions in the order leagues list them (East before Central before
# West); anything else, alphabetical.
DIVISION_ORDER = ['East', 'North', 'Central', 'South', 'West']


def group_order(key):
    conf, group = key
    word = next((w for w in DIVISION_ORDER if group.endswith(' ' + w)), None)
    return (conf, DIVISION_ORDER.index(word) if word else len(DIVISION_ORDER), group)


def teams_index_html(sport, teams):
    college = sport['key'] in ('ncaaf', 'ncaab')
    controls = ('<div class="controls"><div class="control-group">'
                f'<input class="search-box" id="sportTeamSearch" type="search" placeholder="Search team&hellip;" '
                f'aria-label="Search {esc(sport["label"])} teams" style="width:220px">')
    if college:
        confs = sorted({t['conference'] for t in teams if t['conference']})
        opts = ''.join(f'<option value="{esc(c)}">{esc(c)} ({sum(1 for t in teams if t["conference"] == c)})</option>' for c in confs)
        controls += (f'<select class="conf-select" id="sportTeamConf" aria-label="Filter by conference">'
                     f'<option value="">All conferences</option>{opts}</select>')
    controls += f'</div><span class="teams-count" id="sportTeamCount">{len(teams)} teams</span></div>'

    def search_text(t):
        return esc(' '.join(filter(None, [t['name'], t['code'], t.get('short'), t['conference'], t.get('division')])).lower())

    body = ''
    if college:
        letters = {}
        for t in teams:
            letters.setdefault(t['name'][0].upper(), []).append(t)
        for letter in sorted(letters):
            rows = ''.join(
                f'<a class="team-row" href="{team_url(sport, t)}" data-team-item data-search="{search_text(t)}" data-conf="{esc(t["conference"])}">'
                f'{badge_html(t, 34, sport["key"])}<span class="team-row-text"><span class="team-row-name">{esc(t["name"])}</span>'
                f'<span class="team-row-conf">{esc(t["conference"])}</span></span></a>'
                for t in letters[letter])
            body += (f'<div class="letter-group" data-team-group><h2 class="letter-title">{letter}</h2>'
                     f'<div class="team-list">{rows}</div></div>')
    else:
        groups = {}
        for t in teams:
            key = (t['conference'] or '', t.get('division') or t['conference'] or '')
            groups.setdefault(key, []).append(t)
        for (conf, group) in sorted(groups, key=group_order):
            tiles = ''.join(
                f'<a class="team-tile" href="{team_url(sport, t)}" data-team-item data-search="{search_text(t)}" data-conf="{esc(t["conference"])}">'
                f'<span class="team-tile-row">{badge_html(t, 40, sport["key"])}<span class="team-tile-name">{esc(t["name"])}</span></span></a>'
                for t in sorted(groups[(conf, group)], key=lambda x: x['name']))
            body += (f'<div class="division-group" data-team-group><h2 class="division-title">{esc(short_group(group))}</h2>'
                     f'<div class="team-tile-grid">{tiles}</div></div>')
    body += '<div class="teams-empty" id="sportTeamNone" hidden>No teams match that search.</div>'
    return controls + body + TEAM_FILTER_JS


def team_detail_html(sport, team):
    meta = ' · '.join(filter(None, [short_group(team.get('division')), team['conference']]))
    tags = ''.join(f'<span>{esc(seg["tag"])}</span>' for seg in sport['segments'])
    def section(title, msg):
        return f'<h3 class="team-section-title">{title}</h3><div class="section-empty">{msg}</div>'
    no_games = f'No {esc(sport["label"])} games tracked yet.'
    return (f'<a class="sport-team-back" href="/{sport["slug"]}/teams/">&larr; All {esc(sport["label"])} teams</a>'
            f'<div class="sport-team-head">{badge_html(team, 64, sport["key"])}<div><h1>{esc(team["name"])}</h1>'
            f'<div class="sport-team-meta">{esc(meta)}</div></div></div>'
            # assets/sport.js fills these in from data.json once games exist
            + f'<div id="sportApp" data-section="team" data-team="{esc(team["slug"])}">'
            + section('Next Game', 'No upcoming game scheduled yet.')
            + section('Last Game', no_games)
            + section('Season Markets', f'Records and units will appear here once games are graded.<span class="empty-tags">{tags}</span>')
            + section('Home / Away Splits', no_games)
            + section('Current Trends', 'No trends yet.')
            + section('Season Game Log', no_games)
            + '</div>')


SECTION_DESC = {
    'games': '{label} games by date with {segs} odds, scores and results.',
    'stats': '{label} {segs} records: SU, ATS and totals by team, with units.',
    'trends': '{label} League Trends for each slate and current team streaks.',
}


def write_light(template_html_page, page_dir):
    path = os.path.join(ROOT, page_dir)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(lighten(template_html_page, page_dir))


def build_other_sports(template):
    """Pages for every non-NHL sport in the registry. Games / Stats / Trends
    are rendered in the browser by assets/sport.js from {slug}/data.json
    (written by build_sport_data); a sport with no games loaded yet gets a
    clean empty state instead."""
    os.makedirs(os.path.join(ROOT, 'assets'), exist_ok=True)
    with open(os.path.join(ROOT, 'assets', 'site.css'), 'w', encoding='utf-8') as f:
        f.write(site_css(template))
    # The Admin page reads the registry from here (sport menu, segments).
    with open(os.path.join(ROOT, 'assets', 'sports.json'), 'w', encoding='utf-8') as f:
        json.dump([{k: sp[k] for k in ('key', 'label', 'slug', 'sport_type', 'segments', 'schedule')} for sp in sports.SPORTS], f, indent=1)
    written = []
    for sp in sports.SPORTS:
        if sp['key'] == 'nhl':
            continue
        teams = load_teams(sp)
        for section in ('games', 'stats', 'trends', 'teams'):
            label = sports.SECTION_LABELS[section]
            meta = {'title': f'RTYB — {sp["label"]} {label}', 'h1': f'{sp["label"]} — {label}',
                    'desc': f'{sp["label"]} {sports.segment_summary(sp)} {EMPTY_COPY[section][1]}.', 'section': section}
            if section == 'teams' and teams:
                meta['desc'] = (f'Every {sp["label"]} team’s {sports.segment_summary(sp)} record, win % and units this season'
                                + (', by conference' if sp['key'] in ('ncaaf', 'ncaab') else '')
                                + '. Pick a period, market and side, and tap any team for its full page.')
                body = teams_index_html(sp, teams)
                if sport_has_data(sp['key']):
                    # assets/sport.js swaps the plain list for record cards
                    body = f'<div id="sportApp" data-section="teams">{body}</div>'
                html = render_page(template, 'sport', '', meta=meta, sport=sp, sport_body=body)
            elif section != 'teams' and sport_has_data(sp['key']):
                meta['desc'] = SECTION_DESC[section].format(label=sp['label'], segs=sports.segment_summary(sp))
                if section == 'games' and sp.get('schedule') == 'week':
                    meta['desc'] = meta['desc'].replace('games by date', 'games by week')
                body = (f'<div id="sportApp" data-section="{section}"><div class="no-games-note">Loading&hellip;</div>'
                        f'<noscript>This page needs JavaScript.</noscript></div>')
                html = render_page(template, 'sport', '', meta=meta, sport=sp, sport_body=body)
            else:
                html = render_page(template, 'empty', '', meta=meta, sport=sp, empty_html=empty_state_html(sp, section))
            write_light(html, f"{sp['slug']}/{sp['sections'][section]}")
        # one page per team
        for t in teams:
            meta = {'title': f'RTYB — {t["name"]}', 'h1': f'{sp["label"]} — Teams',
                    'desc': f'{sp["label"]} {sports.segment_summary(sp)} records, splits and trends for the {t["name"]}.',
                    'section': 'teams'}
            write_light(render_page(template, 'sport', '', meta=meta, sport=sp, sport_body=team_detail_html(sp, t)),
                        f"{sp['slug']}/teams/{t['slug']}")
        info = SPORT_DATA.get(sp['key']) or {}
        written.append(f"{sp['slug']} ({len(teams)} teams, {info.get('graded', 0)} graded games)")
    return ', '.join(written)


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
    build_sport_data()
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

    # The fetch only covers a rolling window of dates (fetch_schedule.py),
    # so start from every previously saved date and let the fresh window
    # overwrite just its own dates. Otherwise finished games drop off the
    # site (and out of every season record) once they age out of the window.
    merged_games = {d: list(gs) for d, gs in prev_schedule.get('games', {}).items()}
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
            # Period scores saved earlier (or by backfill_periods.py) stay
            # when this fetch didn't produce them for the game.
            prev = prev_games_by_id.get(g.get('id'))
            if prev:
                keep = {k: prev[k] for k in ('awayP1', 'homeP1') + periods.PERIOD_FIELDS if k in prev and k not in g}
                if keep:
                    g = dict(g, **keep)
            merged_list.append(g)
        merged_games[date_str] = merged_list

    # If this run had no fresh schedule at all (e.g. schedule_fresh.json
    # missing, as in a local/manual build), fall back to the previously
    # committed schedule so the site still has data to render.
    merged_game_counts = dict(prev_schedule.get('gameCounts', {}))
    merged_game_counts.update(fresh_schedule.get('gameCounts') or {})

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

    team_names = {code: info['name'] for code, info in base.get('summary', {}).items()}
    summary, streaks, gamelog = build_season_stats(merged_games, team_names)
    full_data = {'summary': summary, 'streaks': streaks, 'gamelog': gamelog}
    # The site only sees this season (schedule_data.json above keeps
    # everything, so saved odds carry forward regardless).
    full_data['schedule'] = {
        'gameCounts': {d: n for d, n in merged_game_counts.items() if d >= SEASON_START},
        'games': {d: gs for d, gs in merged_games.items() if d >= SEASON_START},
    }
    full_data['seasonStart'] = SEASON_START
    # Stats and Trends use this season only (from SEASON_START). The 2025-26
    # backfill (data_seed/nhl_2025_26_games.json, scripts/backfill_2025_26.py)
    # stays in the repo but isn't published; pass it below to bring it back.
    history_games = []

    # League Trends (scripts/league_trends.py): generated here rather than in
    # the browser so each date's list can be stored -- frozen once that
    # date's first game starts -- in league_trends_log.json.
    full_data['leagueTrends'] = league_trends.build(
        history_games, merged_games, SEASON_START, TEAM_DIVISIONS,
        os.path.join(ROOT, 'league_trends_log.json'))
    full_data['leagueTrendsConfig'] = {'shown': league_trends.CONFIG['shown']}
    full_data['trendRules'] = trend_rules.for_page()   # shared thresholds for the pages
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
    SPORT_STATUS.update(home.sport_statuses(template, full_data))

    team_colors = extract_team_true_colors(template)
    teams_menu_html = build_teams_menu_html(full_data.get('summary', {}), team_colors)

    games_html = render_page(template, 'games', teams_menu_html)
    hitrates_html = render_page(template, 'hitrates', teams_menu_html)
    trends_html = render_page(template, 'trends', teams_menu_html)
    teamsindex_html = render_page(template, 'teamsindex', teams_menu_html)

    nhl_dir = os.path.join(ROOT, 'nhl')
    games_dir = os.path.join(ROOT, 'nhl', 'games')
    hitrates_dir = os.path.join(ROOT, 'nhl', '1st-period-stats')
    hitrates_old_dir = os.path.join(ROOT, 'nhl', 'hit-rates')  # old URL -- kept as a redirect stub, see below
    trends_dir = os.path.join(ROOT, 'nhl', 'trends')
    teams_dir = os.path.join(ROOT, 'nhl', 'teams')
    os.makedirs(nhl_dir, exist_ok=True)
    os.makedirs(games_dir, exist_ok=True)
    os.makedirs(hitrates_dir, exist_ok=True)
    os.makedirs(hitrates_old_dir, exist_ok=True)
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
    with open(os.path.join(hitrates_old_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(redirect_page_html('../1st-period-stats/'))
    with open(os.path.join(trends_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(trends_html)
    with open(os.path.join(teams_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(teamsindex_html)

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

    # /nhl/stats/ -> NHL's Stats page, so /{slug}/stats/ works for every sport.
    nhl_stats_alias = os.path.join(ROOT, 'nhl', 'stats')
    os.makedirs(nhl_stats_alias, exist_ok=True)
    with open(os.path.join(nhl_stats_alias, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(redirect_page_html('../1st-period-stats/'))

    other = build_other_sports(template)
    # Home page + Learn, last: they read every sport's data.json.
    home_info = home.build(template, full_data, LOGO_SVG)

    print(f"wrote index.html (home: {home_info['today']} games today, {home_info['trends']} trends), learn/, nhl/data.json ({len(data_json)} bytes), "
          f"nhl/games/index.html ({len(games_html)} bytes), "
          f"nhl/1st-period-stats/index.html ({len(hitrates_html)} bytes), "
          f"nhl/hit-rates/index.html (redirect stub), "
          f"nhl/trends/index.html ({len(trends_html)} bytes), "
          f"nhl/teams/index.html ({len(teamsindex_html)} bytes), "
          f"{len(full_data.get('summary', {}))} nhl/teams/<slug>/index.html pages ({team_bytes} bytes total), "
          f"and schedule_data.json ({sum(len(v) for v in merged_games.values())} games); "
          f"other sports: {other}")


if __name__ == '__main__':
    main()
