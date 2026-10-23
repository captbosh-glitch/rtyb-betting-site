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
import icons
import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo('America/New_York')
PRICE = '[PRICE]'   # Premium price placeholder until it's set
TODAY_SHOWN = 6
RESULTS_SHOWN = 6
TRENDS_SHOWN = 5

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


def units_cell(u):
    """'Yesterday' units, after the record: red when negative, green when
    positive."""
    if not u:
        return ''
    cls = ' neg' if u.startswith('-') else ' pos' if u.startswith('+') else ''
    return f'<span class="ln-u{cls}">{esc(u)}</span>'


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
                'ml': ml, 'total15': tot,
                'href': 'nhl/games/',
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

def nhl_recap(games):
    """'Yesterday' lines for NHL: 1P favorites and Over 1.5."""
    done = [g for g in games if g['state'] == 'final' and g['segScore']]
    if not done:
        return []
    w = l = t = 0
    units, priced, over = 0.0, 0, 0
    for g in done:
        a, h = g['segScore']
        over += (a + h) >= 2
        ml = g['ml']
        pa, ph = ml.get(g['away']['code']), ml.get(g['home']['code'])
        if pa is None or ph is None or implied(pa) == implied(ph):
            continue
        fav_away = implied(pa) > implied(ph)
        mine, theirs = (a, h) if fav_away else (h, a)
        price = pa if fav_away else ph
        priced += 1
        if mine > theirs:
            w += 1
            units += win_units(price)
        elif mine < theirs:
            l += 1
            units -= 1
        else:
            t += 1
    lines = []
    if priced:
        lines.append(('NHL', '1st-period favorites', f'{w}-{l}-{t}', fmt_units(units)))
    lines.append(('NHL', '1st-period Over 1.5', f'{over} of {len(done)}', None))
    return lines


def sport_recap(label, segs, games):
    done = [g for g in games if g['segFinal'] and not g['res'].get('na')]
    if not done:
        return []
    k = done[0]['segKey']
    if k == '1i':
        n = sum(1 for g in done if g['res'].get('rfi') == 'N')
        return [(label, 'NRFI', f'{n} of {len(done)}', None)]
    hw = sum(1 for g in done if g['res'].get('su') == 'L')
    hl = sum(1 for g in done if g['res'].get('su') == 'W')
    ht = len(done) - hw - hl
    seg = next((s for s in segs if s['key'] == k), {})
    return [(label, f"Home teams, {seg.get('label', '').lower()} (SU)", f'{hw}-{hl}-{ht}', None)]


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


def trend_row(t, label):
    picks = ''.join(f'<span class="ht-pick">{esc(p["label"])}</span>' for p in (t.get('games') or [])[:6])
    more = len(t.get('games') or []) - 6
    if more > 0:
        picks += f'<span class="ht-pick muted">+{more} more</span>'
    units = f' &middot; {fmt_units(t["units"])}' if t.get('units') is not None else ''
    return (f'<div class="ht-row"><div class="ht-head"><span class="ht-sport">{esc(label)}</span>'
            f'<span class="ht-tag">{esc(t.get("market"))}</span></div>'
            f'<div class="ht-sentence">{esc(t["sentence"])}</div>'
            f'<div class="ht-rec">{esc(t.get("record"))}{units}</div><div class="ht-picks">{picks}</div></div>')


def nav_html(status, depth=''):
    """Desktop nav + the phone menu. status: [(sport, chip, live)]."""
    sport_items = ''.join(
        f'<a class="hn-sport-item" href="{depth}{sports.section_path(sp, "games").lstrip("/")}">'
        f'<span class="hn-sport-name">{icons.sport_icon(sp)}{esc(sp["label"])}</span><span class="hn-badge{" live" if live else ""}">{"LIVE" if live else esc(short)}</span></a>'
        for sp, chip, live, short in status)
    return f'''
<header class="hn">
  <div class="hn-inner">
    <a class="brand" href="{depth or './'}" aria-label="RTYB home">__LOGO_SVG__</a>
    <nav class="hn-links" aria-label="Main">
      <div class="hn-drop">
        <button class="hn-link hn-drop-btn" id="hnSportsBtn" aria-expanded="false" aria-haspopup="true">Sports <span aria-hidden="true">&#9662;</span></button>
        <div class="hn-drop-menu" id="hnSportsMenu">{sport_items}</div>
      </div>
      <a class="hn-link" href="{depth}#today">Today</a>
      <a class="hn-link" href="{depth}#trends">Trends to Watch</a>
      <a class="hn-link" href="{depth}learn/">Learn</a>
    </nav>
    <div class="hn-right">
      <a class="hn-link hn-signin" href="{depth}#premium">Sign in</a>
      <a class="hn-premium" href="{depth}#premium">Go Premium</a>
      {account.account_html(depth)}
      <button class="theme-toggle" id="themeToggle" type="button" aria-label="Toggle light/dark theme">&#9681;</button>
      <button class="hn-burger" id="hnBurger" type="button" aria-label="Open menu" aria-expanded="false" aria-controls="hnMenu">
        <span></span><span></span><span></span></button>
    </div>
  </div>
</header>
<div class="hm" id="hnMenu" hidden>
  <div class="hm-head">
    <a class="brand" href="{depth or './'}" aria-label="RTYB home">__LOGO_SVG__</a>
    <button class="hm-close" id="hnClose" type="button" aria-label="Close menu">&times;</button>
  </div>
  <div class="hm-body">
    <button class="hm-acc" id="hmSportsBtn" type="button" aria-expanded="true" aria-controls="hmSports">Sports <span aria-hidden="true">&#9662;</span></button>
    <div class="hm-sports" id="hmSports">{sport_items}</div>
    <div class="hm-label">Everything</div>
    <a class="hm-item" href="{depth}#today">Today</a>
    <a class="hm-item" href="{depth}#trends">Trends to Watch</a>
    <a class="hm-item" href="{depth}learn/">Learn</a>
    <a class="hm-item hm-signin" href="{depth}#premium">Sign in</a>
    <button class="hm-item hm-theme" id="hmTheme" type="button">Light / dark theme</button>
  </div>
  <a class="hm-premium" href="{depth}#premium">Go Premium</a>
</div>'''


FOOTER = '''
<footer class="hf">
  <div class="hf-inner">
    <p class="hf-rg"><b>21+ only.</b> Gambling problem? Call <a href="tel:18004262537">1-800-GAMBLER</a>. Please bet responsibly.</p>
    <p class="hf-small">RTYB &mdash; Run to Your Bets is for information and entertainment. Not affiliated with any league or sportsbook.
    Records and units are for tracking only; past results don&rsquo;t predict future ones.</p>
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
  document.getElementById('hmTheme').addEventListener('click', toggleTheme);
  // Sports dropdown (desktop)
  var sBtn = document.getElementById('hnSportsBtn'), sMenu = document.getElementById('hnSportsMenu');
  sBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    var open = !sMenu.classList.contains('open');
    sMenu.classList.toggle('open', open);
    sBtn.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('click', function(e) {
    if (!sMenu.contains(e.target)) { sMenu.classList.remove('open'); sBtn.setAttribute('aria-expanded', 'false'); }
  });
  // Full-screen menu (phones)
  var menu = document.getElementById('hnMenu'), burger = document.getElementById('hnBurger');
  function setMenu(open) {
    menu.hidden = !open;
    burger.setAttribute('aria-expanded', String(open));
    document.body.classList.toggle('hm-open', open);
    if (open) document.getElementById('hnClose').focus(); else burger.focus();
  }
  burger.addEventListener('click', function() { setMenu(true); });
  document.getElementById('hnClose').addEventListener('click', function() { setMenu(false); });
  document.addEventListener('keydown', function(e) { if (e.key === 'Escape' && !menu.hidden) setMenu(false); });
  menu.querySelectorAll('a').forEach(function(a) { a.addEventListener('click', function() { setMenu(false); }); });
  var acc = document.getElementById('hmSportsBtn'), accBody = document.getElementById('hmSports');
  acc.addEventListener('click', function() {
    var open = acc.getAttribute('aria-expanded') !== 'true';
    acc.setAttribute('aria-expanded', String(open));
    accBody.hidden = !open;
  });
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
  // Email signup: there's no list behind it yet, so nothing is sent or stored.
  var form = document.getElementById('premiumForm');
  if (form) form.addEventListener('submit', function(e) {
    e.preventDefault();
    var msg = document.getElementById('premiumMsg');
    var endpoint = form.getAttribute('data-endpoint');
    if (!endpoint) { msg.textContent = 'Signups open soon — check back shortly.'; return; }
  });
})();
</script>'''


def page(title, desc, body, status, depth=''):
    css = f'<link rel="stylesheet" href="{depth}assets/site.css"><link rel="stylesheet" href="{depth}assets/home.css">'
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>'
            f'<meta name="description" content="{esc(desc)}">{FONTS}{css}</head>'
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
    if recent:
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
    for sp in sports.SPORTS:
        chip, live, short = sport_status(sp, by_sport.get(sp['key'], {}), today)
        status.append((sp, chip, live, short))

    # today: every sport's games today, by start time
    today_games = sorted((g for k in by_sport for g in by_sport[k].get(today, [])),
                     key=lambda g: (g.get('start') or '', g['label']))
    # yesterday: the latest date before today with finals in any sport
    past = sorted({d for k in by_sport for d in by_sport[k] if d < today
                   and any(g['state'] == 'final' for g in by_sport[k][d])})
    yday = past[-1] if past else None
    yday_games = sorted((g for k in by_sport for g in by_sport[k].get(yday, []) if g['state'] == 'final'),
                        key=lambda g: (g.get('start') or '')) if yday else []
    recap = []
    if yday:
        recap += nhl_recap(by_sport['nhl'].get(yday, []))
        for sp in sports.SPORTS:
            if sp['key'] != 'nhl':
                recap += sport_recap(sp['label'], sp['segments'], by_sport[sp['key']].get(yday, []))

    # trends to watch today: NHL's log plus each sport's, best first
    trends = []
    try:
        log = json.load(open(os.path.join(ROOT, 'league_trends_log.json'), encoding='utf-8'))
        trends += [('NHL', t) for t in (log.get(today) or {}).get('trends', [])]
    except (OSError, ValueError):
        pass
    for sp in sports.SPORTS:
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

    if recap:
        rows = ''.join(f'<div class="ln-row"><span class="ln-sport">{esc(s)}</span><span class="ln-what">{esc(w)}</span>'
                       f'<span class="ln-val"><span class="ln-rec">{esc(r)}</span>{units_cell(u)}</span></div>'
                       for s, w, r, u in recap[:6])
        last = (f'<div class="ln-card"><div class="ln-head"><span>Yesterday on RTYB</span><span>{esc(day_label(yday))}</span></div>'
                f'{rows}<div class="ln-foot">{len(yday_games)} games graded &middot; <a href="#results">See results</a></div></div>')
    else:
        last = '<div class="ln-card"><div class="ln-head"><span>Yesterday on RTYB</span></div><p class="muted">No graded games yet.</p></div>'

    hero = (f'<section class="hh"><div class="hh-copy"><h1><span class="hh-a">The first</span> <span class="hh-b">period.</span><br><span class="hh-a">The first</span> <span class="hh-b">quarter.</span><br><span class="hh-a">The first</span> <span class="hh-b">inning.</span></h1>'
            f'<p>Records, results and trends for the opening segment of every game &mdash; NHL, NBA, WNBA, MLB and NCAA sports.</p>'
            f'<div class="hh-cta"><a class="btn-primary" href="#today">Today&rsquo;s games</a>'
            f'<a class="btn-ghost" href="#premium">Go Premium</a></div></div>{last}</section>')

    def grid(games, kind, gid):
        if not games:
            return ''
        cards = ''.join(game_card(g, kind).replace('class="hc-card"', 'class="hc-card is-extra"', 1) if i >= TODAY_SHOWN else game_card(g, kind)
                        for i, g in enumerate(games))
        more = (f'<button class="btn-ghost hp-more" type="button" data-expand="{gid}">All {len(games)} games &rarr;</button>'
                if len(games) > TODAY_SHOWN else '')
        return f'<div class="hc-grid" id="{gid}">{cards}</div>{more}'

    today_html = (f'<section class="hp-sec" id="today"><div class="hp-head"><h2>Today</h2>'
                    f'<span class="muted">{esc(day_label(today))} &middot; {len(today_games)} game{"s" if len(today_games) != 1 else ""}</span></div>'
                    + (grid(today_games, 'today', 'todayGrid') or '<p class="hp-empty">No games on the board today.</p>') + '</section>')
    results_html = ''
    if yday_games:
        results_html = (f'<section class="hp-sec" id="results"><div class="hp-head"><h2>Yesterday&rsquo;s results</h2>'
                        f'<span class="muted">{esc(day_label(yday))}</span></div>{grid(yday_games, "results", "resultsGrid")}</section>')

    if trends:
        first = trend_row(trends[0][1], trends[0][0])
        rest = ''.join(trend_row(t, s) for s, t in trends[1:TRENDS_SHOWN])
        locked = ''
        if rest:
            n = len(trends) - 1
            locked = (f'<div class="ht-locked"><div class="ht-blur" aria-hidden="true">{rest}</div>'
                      f'<div class="ht-overlay"><div class="ht-lock-card"><div class="ht-lock-title">{n} more Trends to Watch today</div>'
                      f'<p>Every angle, every sport, graded nightly.</p><a class="btn-primary" href="#premium">Go Premium</a></div></div></div>')
        trends_html = (f'<section class="hp-sec" id="trends"><div class="hp-head"><h2>Trends to Watch today</h2>'
                       f'<span class="muted">League-wide angles on today&rsquo;s games</span></div>{first}{locked}</section>')
    else:
        trends_html = ('<section class="hp-sec" id="trends"><div class="hp-head"><h2>Trends to Watch today</h2></div>'
                       '<p class="hp-empty">No trends clear the bar for today&rsquo;s games yet.</p></section>')

    premium = (f'<section class="hpp" id="premium"><div class="hpp-inner"><div>'
               f'<span class="hpp-kicker">RTYB Premium</span><h2>Every trend. Every sport. {esc(PRICE)}/mo.</h2>'
               f'<ul><li>All Trends to Watch, every night</li><li>Advanced stats and splits by segment</li>'
               f'<li>Units and records for every market</li></ul></div>'
               f'<form class="hpp-form" id="premiumForm" data-endpoint="" novalidate>'
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
    body = (f'{chip_row}{hero}{today_html}{results_html}{trends_html}{premium}{learn_html}')
    home = page('RTYB — Run to Your Bets', 'First period, first quarter and first inning betting stats, results and trends for NHL, NFL, NBA, WNBA, MLB and college.',
                body, status).replace('__LOGO_SVG__', logo_svg)
    with open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(home)

    learn_page = page('RTYB — Learn', 'How first-segment bets work: spreads, moneylines, totals, NRFI, First Five and units.',
                      LEARN_BODY, status, depth='../').replace('__LOGO_SVG__', logo_svg)
    os.makedirs(os.path.join(ROOT, 'learn'), exist_ok=True)
    with open(os.path.join(ROOT, 'learn', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(learn_page)
    return {'today': len(today_games), 'yesterday': len(yday_games), 'trends': len(trends)}


LEARN_LINKS = [
    ('segments', 'First-segment bets', 'Why the 1st period, quarter, half and inning.'),
    ('ats', 'Spread (ATS)', 'Covering, pushes and the -110 price.'),
    ('su', 'Moneyline and SU', 'Straight-up records, ties and prices.'),
    ('totals', 'Totals (O/U)', 'Overs, unders and whole-number pushes.'),
    ('nrfi', 'NRFI / YRFI and F5', 'Baseball’s first inning and first five.'),
    ('units', 'Units', 'How RTYB counts profit and loss.'),
]

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
  <h2 id="responsible">Bet responsibly</h2>
  <p>Only bet what you can afford to lose. If gambling stops being fun, call 1-800-GAMBLER for free, confidential help.</p>
</section>'''
