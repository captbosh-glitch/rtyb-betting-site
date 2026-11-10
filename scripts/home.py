"""
Home page (index.html) and Learn page (learn/index.html), generated at
build time from the same data every sport page uses: NHL's merged data
(build_site.py) and each other sport's {slug}/data.json (sport_build.py).
Static -- the refresh job rebuilds them every run, so "Today" and
"Yesterday" are as fresh as the rest of the site.

Sections, top to bottom: nav (Sports, Today, Trends to Watch, Learn,
Sign in, Go Premium, theme toggle; full-screen menu on phones), sport
chips, hero with "Yesterday on RTYB", Today grid, yesterday's results,
Trends to Watch (first one open, the rest behind the Premium overlay),
Premium + email signup, Learn links, footer.

Colors are the site tokens from assets/site.css (template.html :root).
"""
import html as html_lib
import json
import os
import re
from datetime import date as Date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import account
import daily
import icons
import seo
import nav
import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo('America/New_York')
TODAY_SHOWN = 4    # games a sport in Today
TRENDS_SHOWN = 3   # hottest trends before the email box

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800'
         '&family=Source+Sans+3:wght@400;600;700&family=JetBrains+Mono:wght@500;600;700&display=swap">')


def esc(s):
    return html_lib.escape('' if s is None else str(s), quote=True)


def signed(n):
    if n is None:
        return ''
    n = int(n) if float(n).is_integer() else n
    return f'+{n}' if n > 0 else str(n)


def fmt_units(u):
    return f"{'+' if u > 0 else ''}{u:.2f}u"


def win_units(p):
    return 100 / abs(p) if p < 0 else p / 100


def implied(p):
    return -p / (-p + 100) if p < 0 else 100 / (p + 100)


def time_et(iso):
    t = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ET)
    return t.strftime('%-I:%M %p ET')


def day_label(d):
    return Date.fromisoformat(d).strftime('%a, %b %-d')


def badge(code, color, size=26):
    color = (color or '5B6674').lstrip('#')
    try:
        r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        r = g = b = 91
    text = '#111111' if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else '#FFFFFF'
    code = code or '?'
    fs = max(8, int(size * (0.34 if len(code) <= 3 else 0.27)))
    return (f'<span class="team-badge" style="width:{size}px;height:{size}px;background:#{color};color:{text};'
            f'font-size:{fs}px" aria-hidden="true">{esc(code)}</span>')


# ------------------------------------------------------------------ games

def nhl_colors(template):
    m = re.search(r'TEAM_TRUE_COLOR = \{(.*?)\};', template, re.S)
    return dict(re.findall(r"(\w+): '#([0-9A-Fa-f]{6})'", m.group(1))) if m else {}


def nhl_logo(code):
    """NHL's cached SVGs (fetch_team_logos.py), light and dark."""
    light = os.path.join(ROOT, 'assets', 'logos', f'{code}_light.svg')
    if not os.path.exists(light):
        return ''
    dark = f'assets/logos/{code}_dark.svg' if os.path.exists(os.path.join(ROOT, 'assets', 'logos', f'{code}_dark.svg')) else None
    return icons.logo_html(f'assets/logos/{code}_light.svg', dark, 24)


def nhl_games(nhl_data, colors):
    """NHL schedule in the shape the home page uses."""
    out = {}
    names = {c: v.get('name', c) for c, v in (nhl_data.get('summary') or {}).items()}
    for d, games in ((nhl_data.get('schedule') or {}).get('games') or {}).items():
        for g in games:
            st = g.get('state')
            state = 'final' if st in ('OFF', 'FINAL') else 'in' if st in ('LIVE', 'CRIT') else 'pre'
            o = g.get('odds') or {}
            ml = o.get('ml') or {}
            tot = ((o.get('totals') or {}).get('1.5')) or {}
            p1 = (g.get('awayP1'), g.get('homeP1'))
            out.setdefault(d, []).append({
                'sport': 'nhl', 'label': 'NHL', 'slug': 'nhl', 'start': g.get('startTimeUTC'), 'state': state,
                'away': {'code': g['away'], 'name': names.get(g['away'], g['away']).split()[-1], 'color': colors.get(g['away']),
                         'logo': nhl_logo(g['away'])},
                'home': {'code': g['home'], 'name': names.get(g['home'], g['home']).split()[-1], 'color': colors.get(g['home']),
                         'logo': nhl_logo(g['home'])},
                'score': (g.get('awayFinal'), g.get('homeFinal')) if state != 'pre' else None,
                'seg': '1P', 'segScore': p1 if None not in p1 and state != 'pre' else None,
                'segFinal': state == 'final' and None not in p1,
                'lines': [f"ML {g['away']} {signed(ml.get(g['away']))} · {g['home']} {signed(ml.get(g['home']))}"] if ml.get(g['away']) is not None else [],
                'extra': [f"O/U 1.5 {signed(tot.get('over'))}/{signed(tot.get('under'))}"] if tot.get('over') is not None else [],
                'ml': ml, 'total15': tot, 'btts': (o.get('btts_yes'), o.get('btts_no')),
                'href': f'nhl/games/?date={d}',
            })
    return out


def team_view(doc, slug):
    t = (doc.get('teams') or {}).get(slug)
    if t:
        return {'code': t.get('code'), 'name': t.get('short') or t.get('name'), 'color': t.get('color'),
                'logo': icons.team_logo(doc['sport'], slug, 24, root='')}
    name = (doc.get('otherTeams') or {}).get(slug, slug)
    return {'code': ''.join(w[0] for w in name.split()[:3]).upper(), 'name': name, 'color': None}


def sport_games(doc):
    """One sport's data.json games in the home page shape."""
    out = {}
    seg = (doc.get('segments') or [{}])[0]
    k = seg.get('key')
    for d, games in (doc.get('games') or {}).items():
        for g in games:
            o = (g.get('odds') or {}).get(k) or {}
            res = (g.get('res') or {}).get(k) or {}
            a, h = team_view(doc, g['away']), team_view(doc, g['home'])
            lines = []
            if o.get('nrfi_yrfi'):
                lines.append(f"NRFI {signed(o['nrfi_yrfi'].get('nrfi'))} · YRFI {signed(o['nrfi_yrfi'].get('yrfi'))}")
            if o.get('ats'):
                lines.append(f"{seg.get('tag')} ATS {a['code']} {signed(o['ats']['away']['line'])}")
            if o.get('total'):
                lines.append(f"{seg.get('tag')} O/U {o['total']['line']}")
            out.setdefault(d, []).append({
                'sport': doc['sport'], 'label': doc['label'], 'slug': doc['slug'], 'start': g.get('start'),
                'state': g['state'] if g['state'] in ('pre', 'in', 'final') else 'off', 'away': a, 'home': h,
                'score': (g.get('as'), g.get('hs')) if g['state'] in ('in', 'final') else None,
                'seg': seg.get('tag'), 'segScore': tuple(res['sc']) if res.get('sc') else None,
                'segFinal': bool(res.get('sc')), 'res': res, 'segKey': k,
                'lines': lines, 'extra': [], 'note': g.get('note'),
                'href': f"{doc['slug']}/games/?date={d}",
            })
    return out


# ---------------------------------------------------------------- summary

class Tally:
    """One market's record for a day: W-L(-T) and units over priced bets."""
    def __init__(self, sport, what, ties=True, hits=False):
        self.sport, self.what, self.ties, self.hits = sport, what, ties, hits
        self.w = self.l = self.t = self.priced = 0
        self.units = 0.0

    def add(self, res, units):
        if res == 'W':
            self.w += 1
        elif res == 'L':
            self.l += 1
        else:
            self.t += 1
        if units is not None:
            self.units += units
            self.priced += 1

    def add_price(self, res, price):
        """A bet at an American price (0u on a tie)."""
        self.add(res, None if price is None else win_units(price) if res == 'W' else -1.0 if res == 'L' else 0.0)

    @property
    def n(self):
        return self.w + self.l + self.t

    @property
    def rec(self):
        if self.hits:
            return f'{self.w} of {self.n}'
        return f'{self.w}-{self.l}' + (f'-{self.t}' if self.ties else '')

    @property
    def u(self):
        return round(self.units, 2) if self.priced else None

    @property
    def rate(self):
        return self.w / self.n if self.n else 0


def nhl_records(games):
    """A day's NHL 1st-period records: home teams, favorites, Over 1.5 and
    BTTS Yes, each with units at the saved prices."""
    done = [g for g in games if g['state'] == 'final' and g['segScore']]
    home = Tally('NHL', '1P home teams')
    fav = Tally('NHL', '1P favorites')
    over = Tally('NHL', '1P Over 1.5', hits=True)
    btts = Tally('NHL', '1P BTTS Yes', hits=True)
    for g in done:
        a, h = g['segScore']
        ml = g['ml']
        pa, ph = ml.get(g['away']['code']), ml.get(g['home']['code'])
        home.add_price('W' if h > a else 'L' if h < a else 'T', ph)
        if pa is not None and ph is not None and implied(pa) != implied(ph):
            fav_away = implied(pa) > implied(ph)
            mine, theirs = (a, h) if fav_away else (h, a)
            fav.add_price('W' if mine > theirs else 'L' if mine < theirs else 'T', pa if fav_away else ph)
        over.add_price('W' if a + h >= 2 else 'L', g['total15'].get('over'))
        btts.add_price('W' if a >= 1 and h >= 1 else 'L', g['btts'][0])
    return [x for x in (home, fav, over, btts) if x.n]


def sport_records(label, games):
    """A day's records for a sport from data.json (its first segment):
    home teams SU and ATS, and overs, with units where odds were saved.
    Results are stored from the away side."""
    done = [g for g in games if g['segFinal'] and not g['res'].get('na')]
    if not done:
        return []
    tag = done[0]['seg']
    flip = {'W': 'L', 'L': 'W'}
    su = Tally(label, f'{tag} home teams (SU)')
    ats = Tally(label, f'{tag} home teams (ATS)')
    over = Tally(label, f'{tag} overs', ties=False, hits=True)
    for g in done:
        r, u = g['res'], g['res'].get('u') or {}
        if r.get('su'):
            su.add(flip.get(r['su'], 'T'), (u.get('su') or [None, None])[1])
        if r.get('ats') in ('W', 'L', 'P'):
            ats.add(flip.get(r['ats'], 'T'), (u.get('ats') or [None, None])[1])
        if r.get('tot') in ('O', 'U'):
            over.add('W' if r['tot'] == 'O' else 'L', (u.get('tot') or [None, None])[0])
    return [x for x in (su, ats, over) if x.n]


def units_html(u, cls='ln-u'):
    if u is None:
        return ''
    return f'<span class="{cls}{" neg" if u < 0 else " pos" if u > 0 else ""}">{fmt_units(u) if u else "0.00u"}</span>'


# ------------------------------------------------------------------- html

def game_card(g, kind):
    when = ('Final' if g['state'] == 'final' else 'Live' if g['state'] == 'in'
            else time_et(g['start']) if g.get('start') else '')
    if g['state'] == 'off':
        when = 'Postponed'
    score = (f'<span class="hc-score">{g["score"][0]}&ndash;{g["score"][1]}</span>'
             if g.get('score') and g['score'][0] is not None else '')
    seg = ''
    if g.get('segScore'):
        a, h = g['segScore']
        seg = f'<div class="hc-seg"><span class="hc-tag">{esc(g["seg"])}</span> {a}&ndash;{h}'
        r = g.get('res') or {}
        if r.get('rfi') in ('Y', 'N'):
            seg += f' <span class="hc-chip {"w" if r["rfi"] == "N" else "l"}">{"NRFI" if r["rfi"] == "N" else "YRFI"}</span>'
        seg += '</div>'
    lines = ''.join(f'<div class="hc-line">{esc(x)}</div>' for x in (g.get('lines') or []) + (g.get('extra') or []))
    if kind == 'today' and not lines:
        lines = f'<div class="hc-line muted">{esc(g["seg"])} odds pending</div>'
    team = lambda t: f'<span class="hc-team">{t.get("logo") or badge(t["code"], t["color"], 24)}<span>{esc(t["name"])}</span></span>'
    return (f'<a class="hc-card" href="{esc(g["href"])}">'
            f'<div class="hc-top"><span class="hc-sport">{icons.sport_icon(g["sport"])}{esc(g["label"])}</span><span class="hc-when">{esc(when)}</span></div>'
            f'<div class="hc-teams">{team(g["away"])}<span class="hc-at">@</span>{team(g["home"])}{score}</div>'
            f'{seg if kind == "results" else ""}{lines if kind == "today" else ""}</a>')


PICK_DONE = {'LIVE': 'Live', 'W': 'Hit', 'L': 'Miss', 'P': 'Push', 'NA': 'No action'}


def trend_pick(t, p):
    """A pick chip: a bet only on a non-weak trend before its game starts."""
    done = PICK_DONE.get(p.get('status'))
    muted = done or t.get('strength') == 'weak'
    agree = f' <span class="ht-agree">{p["agree"]} agree</span>' if (p.get('agree') or 0) > 1 else ''
    return (f'<span class="ht-pick{" muted" if muted else ""}">{esc(p["label"])}'
            f'{f" &middot; {done}" if done else ""}{agree}</span>')


def trend_row(t, label):
    picks = ''.join(trend_pick(t, p) for p in (t.get('games') or [])[:6])
    more = len(t.get('games') or []) - 6
    if more > 0:
        picks += f'<span class="ht-pick muted">+{more} more</span>'
    units = f' &middot; {fmt_units(t["units"])}' if t.get('units') is not None else ''
    return (f'<div class="ht-row"><div class="ht-head"><span class="ht-sport">{esc(label)}</span>'
            f'<span class="ht-tag">{esc(t.get("market"))}</span></div>'
            f'<div class="ht-sentence">{esc(t["sentence"])}</div>'
            f'<div class="ht-rec">{esc(t.get("record"))}{units}</div><div class="ht-picks">{picks}</div></div>')


def nav_html(status, depth=''):
    """The shared site nav (scripts/nav.py). status: [(sport, chip, live, short)]."""
    return nav.header(depth, [(sp, live, short) for sp, chip, live, short in status])


FOOTER = '''
<footer class="hf">
  <div class="hf-inner">
    <p class="hf-rg"><b>21+ only.</b> Gambling problem? Call <a href="tel:18004262537">1-800-GAMBLER</a>. Please bet responsibly.</p>
    <p class="hf-small">RTYB &mdash; Run to Your Bets is for information and entertainment. Not affiliated with any league or sportsbook.
    Records and units are for tracking only; past results don&rsquo;t predict future ones.</p>
    <p class="hf-small hf-legal"><a href="__ROOT__privacy/">Privacy</a> &middot; <a href="__ROOT__terms/">Terms</a></p>
  </div>
</footer>'''

PAGE_JS = '''
<script>
(function() {
  'use strict';
  var root = document.documentElement;
  try { var saved = localStorage.getItem('rtyb-theme'); if (saved) root.setAttribute('data-theme', saved); } catch (e) {}
  function toggleTheme() {
    var cur = root.getAttribute('data-theme');
    var isDark = cur ? cur === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    var next = isDark ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('rtyb-theme', next); } catch (e) {}
  }
  document.getElementById('themeToggle').addEventListener('click', toggleTheme);
  // the menus are wired by scripts/nav.py
  // League chips: arrows (and edge fades) when the row is wider than the
  // screen; each arrow shows only when there's more that way.
  var hsRow = document.getElementById('hsRow'), hsWrap = document.getElementById('hsWrap');
  if (hsRow) {
    var prev = hsWrap.querySelector('.prev'), next = hsWrap.querySelector('.next');
    var syncArrows = function() {
      var max = hsRow.scrollWidth - hsRow.clientWidth;
      prev.hidden = hsRow.scrollLeft <= 2;
      next.hidden = hsRow.scrollLeft >= max - 2;
      hsWrap.classList.toggle('fade-l', !prev.hidden);
      hsWrap.classList.toggle('fade-r', !next.hidden);
    };
    var by = function(dir) { hsRow.scrollBy({ left: dir * Math.max(160, hsRow.clientWidth * 0.7), behavior: 'smooth' }); };
    prev.addEventListener('click', function() { by(-1); });
    next.addEventListener('click', function() { by(1); });
    hsRow.addEventListener('scroll', syncArrows, { passive: true });
    window.addEventListener('resize', syncArrows);
    syncArrows();
  }
  // "All N games" expanders
  document.querySelectorAll('[data-expand]').forEach(function(b) {
    b.addEventListener('click', function() {
      document.querySelectorAll('#' + b.getAttribute('data-expand') + ' .is-extra').forEach(function(el) { el.classList.remove('is-extra'); });
      b.remove();
    });
  });
  // Today: show one sport's games (and its "All N games" link) or all
  document.querySelectorAll('[data-hp-sport]').forEach(function(b) {
    b.addEventListener('click', function() {
      var want = b.getAttribute('data-hp-sport');
      document.querySelectorAll('[data-hp-sport]').forEach(function(x) { x.setAttribute('aria-pressed', String(x === b)); });
      document.querySelectorAll('#today [data-sport]').forEach(function(el) {
        el.hidden = want !== 'all' && el.getAttribute('data-sport') !== want;
      });
    });
  });
  // Email signup: there's no list behind it yet, so nothing is sent or stored.
  document.querySelectorAll('form.hp-email').forEach(function(form) {
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      form.querySelector('.hpp-msg').textContent = 'Signups open soon — check back shortly.';
    });
  });
})();
</script>'''


def page(title, desc, body, status, depth='', noindex=False):
    """noindex: reachable by URL but kept out of search (Picks, Streaks)."""
    css = f'<link rel="stylesheet" href="{depth}assets/site.css"><link rel="stylesheet" href="{depth}assets/home.css">'
    robots = '<meta name="robots" content="noindex">' if noindex else ''
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>'
            f'<meta name="description" content="{esc(desc)}">{robots}{FONTS}{css}</head>'
            f'<body class="home">{nav_html(status, depth)}<main class="hp">{body}</main>{FOOTER}{PAGE_JS}{account.ACCOUNT_JS}</body></html>')


# ------------------------------------------------------------------- build

def sport_status(sp, games_by_date, today):
    """(chip text, live?, short label for the menu)."""
    todays = len(games_by_date.get(today, []))
    dates = sorted(games_by_date)
    if not dates:
        month = sports.MONTHS[sp['season_start'] - 1][:3]
        return 'Soon', False, month
    t = Date.fromisoformat(today)
    # In season = games today, or a final within the last two weeks (playoff gaps).
    recent = [d for d in dates if d < today and (t - Date.fromisoformat(d)).days <= 14
              and any(g['state'] == 'final' for g in games_by_date[d])]
    if todays and (recent or any(g['state'] != 'pre' for g in games_by_date[today])):
        return f'{todays} today', True, 'LIVE'
    # an off day mid-season stays LIVE; a season that just ended (no game
    # in the coming week) never does
    if recent and any(today < d <= (t + timedelta(days=7)).isoformat() for d in dates):
        return 'Off today', True, 'LIVE'
    if todays:
        return f'Starts today ({todays})', True, 'LIVE'
    upcoming = [d for d in dates if d > today]
    if upcoming and (Date.fromisoformat(upcoming[0]) - t).days <= 60:
        nd = Date.fromisoformat(upcoming[0])
        return f'Starts {nd.strftime("%b %-d")}', False, nd.strftime('%b %-d')
    month = sports.MONTHS[sp['season_start'] - 1]
    return f'Back in {month[:3]}', False, month[:3]


def collect(template, nhl_data):
    """Every sport's games by date in the home page shape, plus each
    non-NHL sport's data.json."""
    colors = nhl_colors(template)
    by_sport = {'nhl': nhl_games(nhl_data, colors)}
    docs = {}
    for sp in sports.SPORTS:
        if sp['key'] == 'nhl':
            continue
        path = os.path.join(ROOT, sp['slug'], 'data.json')
        doc = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
        docs[sp['key']] = doc
        by_sport[sp['key']] = sport_games(doc) if doc.get('games') is not None and doc.get('segments') else {}
    return by_sport, docs


def sport_statuses(template, nhl_data, now_utc=None):
    """{sport key: {'chip', 'live', 'short'}} -- the same LIVE / date /
    month labels the home page shows, for every page's Sports menu."""
    now_utc = now_utc or datetime.now(timezone.utc)
    today = now_utc.astimezone(ET).date().isoformat()
    by_sport, _ = collect(template, nhl_data)
    out = {}
    for sp in sports.SPORTS:
        chip, live, short = sport_status(sp, by_sport.get(sp['key'], {}), today)
        out[sp['key']] = {'chip': chip, 'live': live, 'short': short}
    return out


def build(template, nhl_data, logo_svg, now_utc=None):
    now_utc = now_utc or datetime.now(timezone.utc)
    today = now_utc.astimezone(ET).date().isoformat()
    by_sport, docs = collect(template, nhl_data)

    status = []
    for sp in sports.LAUNCHED:
        chip, live, short = sport_status(sp, by_sport.get(sp['key'], {}), today)
        status.append((sp, chip, live, short))
    # hidden sports (sports.py 'launched') stay off the home page
    by_sport = {k: v for k, v in by_sport.items() if sports.is_launched(k)}

    # today: every sport's games today, by start time
    today_games = sorted((g for k in by_sport for g in by_sport[k].get(today, [])),
                     key=lambda g: (g.get('start') or '', g['label']))
    # yesterday: the latest date before today with finals in any sport
    past = sorted({d for k in by_sport for d in by_sport[k] if d < today
                   and any(g['state'] == 'final' for g in by_sport[k][d])})
    yday = past[-1] if past else None
    yday_games = sorted((g for k in by_sport for g in by_sport[k].get(yday, []) if g['state'] == 'final'),
                        key=lambda g: (g.get('start') or '')) if yday else []
    # yesterday's records per sport, with units, plus each sport's league-trend record
    records = {}
    if yday:
        for sp in sports.LAUNCHED:
            day = by_sport[sp['key']].get(yday, [])
            records[sp['key']] = nhl_records(day) if sp['key'] == 'nhl' else sport_records(sp['label'], day)
            if sp['key'] == 'nhl':
                try:
                    rec = (json.load(open(os.path.join(ROOT, 'league_trends_log.json'), encoding='utf-8')).get(yday) or {}).get('record')
                except (OSError, ValueError):
                    rec = None
            else:
                rec = (((docs.get(sp['key']) or {}).get('trends') or {}).get(yday) or {}).get('record')
            if rec and rec.get('w', 0) + rec.get('l', 0):
                tr = Tally(sp['label'], 'League trends', ties=False)
                tr.w, tr.l = rec['w'], rec['l']
                records[sp['key']].append(tr)

    # trends to watch today: NHL's log plus each sport's, best first
    trends = []
    try:
        log = json.load(open(os.path.join(ROOT, 'league_trends_log.json'), encoding='utf-8'))
        trends += [('NHL', t) for t in (log.get(today) or {}).get('trends', [])]
    except (OSError, ValueError):
        pass
    for sp in sports.LAUNCHED:
        doc = docs.get(sp['key']) or {}
        key = today
        if doc.get('schedule') == 'week':
            # Football's trends are per week: this week's, if it has games today.
            wk = next((w for w in doc.get('weeks') or [] if w['start'] <= today <= w['end']), None)
            key = wk['key'] if wk and doc.get('games', {}).get(today) else None
        trends += [(sp['label'], t) for t in ((doc.get('trends') or {}).get(key) or {}).get('trends', [])]
    trends.sort(key=lambda x: -(x[1].get('score') or 0))

    # ---- sections
    chips = ''.join(
        f'<a class="hs-chip{" live" if live else ""}" href="{sports.section_path(sp, "games").lstrip("/")}">'
        f'<span class="hs-name">{icons.sport_icon(sp)}{esc(sp["label"])}</span><span class="hs-count">{esc(chip)}</span></a>'
        for sp, chip, live, short in status)

    # hero proof card: yesterday's best result (most units), then 3 more records
    all_recs = [r for sp in sports.LAUNCHED for r in records.get(sp['key'], [])]
    if all_recs:
        ranked = sorted(all_recs, key=lambda r: (-(r.u if r.u is not None else -99), -r.rate, -r.n))
        best = ranked[0]
        rows = ''.join(f'<div class="ln-row"><span class="ln-sport">{esc(r.sport)}</span><span class="ln-what">{esc(r.what)}</span>'
                       f'<span class="ln-val"><span class="ln-rec">{esc(r.rec)}</span>{units_html(r.u)}</span></div>'
                       for r in ranked[1:4])
        last = (f'<div class="ln-card"><div class="ln-head"><span>Yesterday on RTYB</span><span>{esc(day_label(yday))}</span></div>'
                f'<div class="ln-best"><span class="ln-best-what">{esc(best.sport)} &middot; {esc(best.what)}</span>'
                f'<span class="ln-best-rec">{esc(best.rec)}</span>{units_html(best.u, "ln-best-u")}</div>'
                f'{rows}<div class="ln-foot">{len(yday_games)} games graded &middot; <a href="#results">See yesterday&rsquo;s results</a></div></div>')
    else:
        last = '<div class="ln-card"><div class="ln-head"><span>Yesterday on RTYB</span></div><p class="muted">No graded games yet.</p></div>'

    hero = (f'<section class="hh"><div class="hh-copy"><h1><span class="hh-a">The first</span> <span class="hh-b">period.</span><br><span class="hh-a">The first</span> <span class="hh-b">quarter.</span><br><span class="hh-a">The first</span> <span class="hh-b">half.</span></h1>'
            f'<p>Early bets settle fast. Run to yours with the numbers! Odds, stats and trends for every NHL and NBA game.</p>'
            f'<div class="hh-cta"><a class="btn-primary" href="#trends">Today&rsquo;s trends</a>'
            f'<a class="btn-ghost" href="#premium">Get the daily email</a></div>'
            f'<p class="hh-note">Every trend graded. Every record public.</p></div>{last}</section>')

    # today: up to TODAY_SHOWN games a sport (live, then upcoming, then
    # finals), filter chips, and a link to each sport's full slate
    order = {'in': 0, 'pre': 1, 'final': 2, 'off': 3}
    cards, links, today_sports = '', '', []
    for sp in sports.LAUNCHED:
        games = sorted(by_sport[sp['key']].get(today, []), key=lambda g: (order.get(g['state'], 3), g.get('start') or ''))
        if not games:
            continue
        today_sports.append(sp)
        cards += ''.join(game_card(g, 'today').replace('class="hc-card"', f'class="hc-card" data-sport="{sp["key"]}"', 1)
                         for g in games[:TODAY_SHOWN])
        links += (f'<a class="hp-all" data-sport="{sp["key"]}" href="{sports.section_path(sp, "games").lstrip("/")}?date={today}">'
                  f'All {len(games)} {esc(sp["label"])} game{"s" if len(games) != 1 else ""} &rarr;</a>')
    filters = ''
    if len(today_sports) > 1:
        filters = ('<div class="seg-toggle hp-filter" role="group" aria-label="Sport">'
                   '<button class="seg-btn" type="button" data-hp-sport="all" aria-pressed="true">All</button>'
                   + ''.join(f'<button class="seg-btn" type="button" data-hp-sport="{sp["key"]}" aria-pressed="false">{esc(sp["label"])}</button>'
                             for sp in today_sports) + '</div>')
    today_html = (f'<section class="hp-sec" id="today"><div class="hp-head"><h2>Today</h2>'
                  f'<span class="muted">{esc(day_label(today))} &middot; {len(today_games)} game{"s" if len(today_games) != 1 else ""}</span>{filters}</div>'
                  + (f'<div class="hc-grid" id="todayGrid">{cards}</div><div class="hp-alls">{links}</div>' if cards
                     else '<p class="hp-empty">No games on the board today.</p>') + '</section>')

    # yesterday's results: one summary card per sport
    res_cards = ''
    for sp in sports.LAUNCHED:
        recs = records.get(sp['key']) or []
        n = sum(1 for g in yday_games if g['sport'] == sp['key'])
        if not recs or not n:
            continue
        rows = ''.join(f'<div class="ln-row"><span class="ln-what">{esc(r.what)}</span>'
                       f'<span class="ln-val"><span class="ln-rec">{esc(r.rec)}</span>{units_html(r.u)}</span></div>' for r in recs)
        res_cards += (f'<div class="hr-card"><div class="hr-head"><span class="hc-sport">{icons.sport_icon(sp)}{esc(sp["label"])}</span>'
                      f'<span class="muted">{n} game{"s" if n != 1 else ""} graded</span></div>{rows}'
                      f'<a class="hr-link" href="{sports.section_path(sp, "games").lstrip("/")}?date={yday}">All {esc(sp["label"])} results &rarr;</a></div>')
    results_html = ''
    if res_cards:
        results_html = (f'<section class="hp-sec" id="results"><div class="hp-head"><h2>Yesterday&rsquo;s results</h2>'
                        f'<span class="muted">{esc(day_label(yday))}</span></div><div class="hr-grid">{res_cards}</div></section>')

    # hottest trends: the 3 strongest shown, the rest behind an email box
    hot = [x for x in trends if (x[1].get('strength') or 'weak') != 'weak']
    if hot:
        shown = ''.join(trend_row(t, s) for s, t in hot[:TRENDS_SHOWN])
        rest = hot[TRENDS_SHOWN:]
        locked = ''
        if rest:
            locked = (f'<div class="ht-locked"><div class="ht-blur" aria-hidden="true">{"".join(trend_row(t, s) for s, t in rest[:3])}</div>'
                      f'<div class="ht-overlay"><form class="ht-lock-card hp-email" data-source="trends" novalidate>'
                      f'<div class="ht-lock-title">{len(rest)} more trend{"s" if len(rest) != 1 else ""} today</div>'
                      f'<p>Free with your email. Every angle, both sports, graded daily.</p>'
                      f'<div class="hpp-row"><input type="email" placeholder="you@email.com" autocomplete="email" aria-label="Email address">'
                      f'<button class="btn-primary" type="submit">Unlock free</button></div>'
                      f'<p class="hpp-msg" role="status"></p></form></div></div>')
        trends_html = (f'<section class="hp-sec" id="trends"><div class="hp-head"><h2>Hottest trends today</h2>'
                       f'<span class="muted">Records from the side to bet. Ties are pushes.</span>'
                       f'<a class="hp-head-link" href="{sports.section_path(sports.BY_KEY["nhl"], "trends").lstrip("/")}">All trends &rarr;</a></div>'
                       f'<div class="ht-grid">{shown}</div>{locked}</section>')
    else:
        trends_html = ('<section class="hp-sec" id="trends"><div class="hp-head"><h2>Hottest trends today</h2></div>'
                       '<p class="hp-empty">No trends clear the bar for today&rsquo;s games yet.</p></section>')

    pieces = daily.load()
    # the newest recap, preview and column; a placeholder for any not published yet
    slots = {'recap': '<div class="hd-card"><span class="hd-kicker">The Morning Run &middot; recap</span><b>Yesterday&rsquo;s recap lands here each morning.</b><span class="muted">Starting launch week.</span></div>',
             'preview': '<div class="hd-card"><span class="hd-kicker">On Tap &middot; today&rsquo;s preview</span><b>Today&rsquo;s preview lands here before the first game.</b><span class="muted">Starting launch week.</span></div>',
             'column': '<div class="hd-card"><span class="hd-kicker">Running Tab &middot; weekly column</span><b>The first column is on the way.</b><span class="muted">Coming soon.</span></div>'}
    for kind in slots:
        p = daily.latest(pieces, kind)
        if p:
            slots[kind] = daily.card(p, p['path'])
    daily_html = ('<section class="hp-sec" id="daily"><div class="hp-head"><h2>The Daily</h2>'
                  '<span class="muted">Recaps, previews and the weekly column.</span><a class="hp-head-link" href="daily/">Everything in The Daily &rarr;</a></div>'
                  '<div class="hd-grid">' + ''.join(slots.values()) + '</div></section>')

    premium = (f'<section class="hpp" id="premium"><div class="hpp-inner"><div>'
               f'<span class="hpp-kicker">RTYB Premium &middot; coming soon</span><h2>Premium is coming. Get on the list.</h2>'
               f'<ul><li>Plays where several trends point the same way</li><li>Situational splits: rest, back-to-backs, bounce-backs</li>'
               f'<li>Every pick graded in public</li></ul></div>'
               f'<form class="hpp-form hp-email" id="premiumForm" data-source="premium" novalidate>'
               f'<label for="premiumEmail">Get notified when Premium launches</label>'
               f'<div class="hpp-row"><input id="premiumEmail" type="email" placeholder="you@example.com" autocomplete="email">'
               f'<button class="btn-gold" type="submit">Notify me</button></div>'
               f'<p class="hpp-msg" id="premiumMsg" role="status"></p></form></div></section>')

    learn = ''.join(f'<a class="hl-card" href="learn/#{a}"><b>{esc(t)}</b><span>{esc(d)}</span></a>' for a, t, d in LEARN_LINKS)
    learn_html = (f'<section class="hp-sec" id="learn"><div class="hp-head"><h2>Learn</h2></div>'
                  f'<div class="hl-grid">{learn}</div></section>')

    chip_row = (f'<div class="hs-wrap" id="hsWrap">'
                f'<button class="hs-arrow prev" type="button" aria-label="Scroll leagues left" hidden>&lsaquo;</button>'
                f'<div class="hs-row" id="hsRow">{chips}</div>'
                f'<button class="hs-arrow next" type="button" aria-label="Scroll leagues right" hidden>&rsaquo;</button></div>')
    body = (f'{chip_row}{hero}{today_html}{trends_html}{results_html}{daily_html}{premium}{learn_html}')
    home = page('RTYB — Run to Your Bets', 'First period, first quarter and first half betting odds, stats and trends for every NHL and NBA game.',
                body, status).replace('__LOGO_SVG__', logo_svg)
    with open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(home)

    learn_page = page('RTYB — Learn', 'How first-segment bets work: spreads, moneylines, totals, NRFI, First Five and units.',
                      LEARN_BODY, status, depth='../').replace('__LOGO_SVG__', logo_svg)
    os.makedirs(os.path.join(ROOT, 'learn'), exist_ok=True)
    with open(os.path.join(ROOT, 'learn', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(learn_page)
    daily.write_pages(page, status, logo_svg, pieces)
    seo.write_legal(page, status, logo_svg)
    return {'today': len(today_games), 'yesterday': len(yday_games), 'trends': len(trends)}


LEARN_LINKS = [
    ('segments', 'First-segment bets', 'Why the 1st period, quarter, half and inning.'),
    ('ats', 'Spread (ATS)', 'Covering, pushes and the -110 price.'),
    ('su', 'Moneyline and SU', 'Straight-up records, ties and prices.'),
    ('totals', 'Totals (O/U)', 'Overs, unders and whole-number pushes.'),
    ('nrfi', 'NRFI / YRFI and F5', 'Baseball’s first inning and first five.'),
    ('units', 'Units', 'How RTYB counts profit and loss.'),
    ('confidence', 'How confidence works', 'How Today’s Picks are scored, tiered and graded.'),
]


def write_picks(template, nhl_data, logo_svg, body, now_utc=None):
    """picks/index.html around the body from picks.py, with the site nav."""
    now_utc = now_utc or datetime.now(timezone.utc)
    today = now_utc.astimezone(ET).date().isoformat()
    by_sport, _ = collect(template, nhl_data)
    status = [(sp,) + sport_status(sp, by_sport.get(sp['key'], {}), today) for sp in sports.LAUNCHED]
    html = page('RTYB — Today’s Picks', 'Trend-based plays for the first quarter, half, period and inning, ranked by confidence, with every tier’s record public.',
                body, status, depth='../', noindex=True).replace('__LOGO_SVG__', logo_svg)
    os.makedirs(os.path.join(ROOT, 'picks'), exist_ok=True)
    with open(os.path.join(ROOT, 'picks', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)

LEARN_BODY = '''
<section class="hp-sec learn">
  <h1>Learn</h1>
  <p class="lead">RTYB tracks the opening segment of every game. Here&rsquo;s what each market means and how we grade it.</p>
  <h2 id="segments">First-segment bets</h2>
  <p>Instead of the whole game, these bets settle on the first piece of it: the 1st period in the NHL, the 1st quarter or
  1st half in football and basketball, and the 1st inning or first five innings in baseball. They settle fast and
  depend on how teams start, which is what RTYB&rsquo;s records and trends measure.</p>
  <h2 id="ats">Spread (ATS)</h2>
  <p>The favorite gives points and the underdog gets them: &ldquo;Lakers &minus;1.5&rdquo; wins if the Lakers win the
  segment by 2 or more. Records are W-L-P &mdash; a push (P) is when the margin lands exactly on the line, and the bet is
  refunded. Spreads are usually priced at &minus;110 (risk $110 to win $100) unless another price is listed.</p>
  <h2 id="su">Moneyline and SU</h2>
  <p>A moneyline bet is on who wins the segment outright. RTYB shows these records as SU (straight up), W-L-T. A tie
  in the segment is a push for the bet (0 units). Prices: &minus;150 means risk $150 to win $100; +130 means risk $100 to
  win $130.</p>
  <h2 id="totals">Totals (Over / Under)</h2>
  <p>A bet on combined points, goals or runs in the segment. Records are O-U-P. A half-point line (44.5) can&rsquo;t push;
  a whole-number line (44) pushes when the total lands on it exactly.</p>
  <h2 id="nrfi">NRFI / YRFI and First Five (F5)</h2>
  <p>NRFI is &ldquo;no run first inning&rdquo; &mdash; neither team scores in the 1st. YRFI is the opposite. There are no
  pushes; if the 1st inning isn&rsquo;t finished, it&rsquo;s No Action. First Five bets settle on the score after five
  innings: the F5 spread is always 0.5 runs (a tie goes to the +0.5 side), an F5 moneyline tie is a push, and fewer than
  five innings played means No Action.</p>
  <h2 id="units">Units</h2>
  <p>1 unit = $100 risked on every game in a category at the listed price. A loss is &minus;1 unit; a win pays by the
  price (+0.91u at &minus;110). Pushes, ties and No Action are 0. Records that need odds &mdash; spreads, totals,
  favorites and units &mdash; only count games with saved odds, and say how many (&ldquo;based on N games with
  odds&rdquo;).</p>
  <h2 id="confidence">How confidence works (Today&rsquo;s Picks)</h2>
  <p>Every play on <a href="../picks/">Today&rsquo;s Picks</a> starts from a saved line: a moneyline price, a spread or a
  total. For each side, RTYB collects angles from this season&rsquo;s graded games played before it, at <em>today&rsquo;s</em>
  line: the team&rsquo;s record this season, over its last 8 and at this venue, and the opponent&rsquo;s record at its venue
  (for totals, both teams&rsquo; games). Each angle&rsquo;s hit rate is pulled toward 50% by 8 imaginary games, so small samples
  move less, and the angles are averaged by sample size. The <b>edge</b> is that estimate minus the chance the price
  implies (&minus;110 when no price was saved).</p>
  <p>A play needs at least two angles that agree and an edge of 3% or more. <b>A-tier</b>: edge 6%+ on a sample of 15+ with a
  saved price. <b>B-tier</b>: edge 4%+ on 10+. Everything else is <b>C</b>, and a sample under 10 can&rsquo;t rank above C.
  Personalities tag the style of each play (Chalk Eater, Dog Hunter, Streak Rider, Contrarian, Over Lover, Under Grinder,
  Early Bird).</p>
  <p>Plays lock when the game starts and are graded on the saved line and price: wins at the price, losses &minus;1u, pushes
  and tied moneyline segments 0u. Records start from the first day Picks went live; nothing is backfilled.</p>
  <h2 id="responsible">Bet responsibly</h2>
  <p>Only bet what you can afford to lose. If gambling stops being fun, call 1-800-GAMBLER for free, confidential help.</p>
</section>'''
