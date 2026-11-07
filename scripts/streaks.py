"""
Streaks (/streaks/): every team's current run of MIN_STREAK or more straight
results in its sport's first segment (the 1st period, quarter, half or
inning), one list per market, split into hot (wins, covers, overs, YRFI,
BTTS yes) and cold (losses, failed covers, unders, NRFI, BTTS no).

Built from streaks the builds already compute, newest game first, where a
push or tie ends a streak: NHL's in nhl/data.json (build_site.py) and every
other sport's data.json "streaks" (sport_build.team_streaks). Only sports
in season with games in the coming week are shown.
"""
import html
import json
import os

import home
import icons
import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_STREAK = 4   # "more than 3"
SHOWN = 10       # rows per list before "Show all"

# result -> (hot?, the word in "7 game OVER streak"); ATS gets its own words
WORDS = {'W': (True, 'WIN'), 'L': (False, 'LOSS'), 'Over': (True, 'OVER'), 'O': (True, 'OVER'),
         'Under': (False, 'UNDER'), 'U': (False, 'UNDER'), 'YRFI': (True, 'YRFI'), 'NRFI': (False, 'NRFI'),
         'Y': (True, 'BTTS YES'), 'N': (False, 'BTTS NO')}
ATS_WORDS = {'W': (True, 'COVER'), 'L': (False, 'NO-COVER')}


def esc(s):
    return html.escape('' if s is None else str(s), quote=True)


def nhl_lists(nhl_data, colors):
    """{market: [row]} for the NHL's 1st period."""
    names = {c: v.get('name', c) for c, v in (nhl_data.get('summary') or {}).items()}
    out = {'wl': [], 'o15': [], 'btts': []}
    for code, st in (nhl_data.get('streaks') or {}).items():
        for m in out:
            kind, n = st.get(f'{m}_result'), st.get(f'{m}_streak') or 0
            if n >= MIN_STREAK and kind in WORDS:
                out[m].append({'name': names.get(code, code), 'code': code, 'color': f'#{colors[code]}' if colors.get(code) else None,
                               'href': f'nhl/teams/{code.lower()}/', 'n': n, 'kind': kind})
    return out


def sport_lists(sp, doc):
    """{market: [row]} for one other sport's first segment."""
    k = sp['segments'][0]['key']
    teams = dict(doc.get('otherTeams') or {}, **(doc.get('teams') or {}))
    out = {}
    for slug, found in (doc.get('streaks') or {}).items():
        t = teams.get(slug) or {}
        for s in found:
            if s['seg'] != k or s['n'] < MIN_STREAK:
                continue
            color = t.get('color')
            out.setdefault(s['market'], []).append({
                'name': t.get('name') or slug, 'code': t.get('code') or (t.get('short') or slug).upper(),
                'color': f'#{color.lstrip("#")}' if color else None,
                'href': f'{sp["slug"]}/teams/{slug}/' if slug in (doc.get('teams') or {}) else None,
                'n': s['n'], 'kind': s['kind']})
    return out


def markets(sp):
    """[(key, pill label, what it measures)] for a sport's first segment."""
    seg = sp['segments'][0]
    low = seg['label'].lower()
    if sp['key'] == 'nhl':
        return [('wl', 'Moneyline', 'Who wins the 1st period (a tied period ends a streak)'),
                ('o15', 'O/U 1.5', 'Combined 1st-period goals over or under 1.5'),
                ('btts', 'BTTS', 'Both teams score in the 1st period')]
    if seg['key'] == '1i':
        return [('rfi', 'YRFI / NRFI', 'A run scored in the 1st inning (YRFI) or not (NRFI)')]
    unit = 'runs' if sp['sport_type'] == 'baseball' else 'points'
    out = [('su', 'Moneyline', f'Who wins the {low}, straight up')] if sports.has_ml(seg) else []
    return out + [('ats', 'ATS', f'{seg["label"]} result against the spread'),
                  ('tot', 'O/U', f'Combined {low} {unit} vs the posted total')]


def streak_list(rows, hot, market, depth):
    title, icon = ('Hot Streaks', '&#128293;') if hot else ('Cold Streaks', '&#10052;')
    words = ATS_WORDS if market == 'ats' else WORDS
    rows = sorted((r for r in rows if words.get(r['kind'], (None,))[0] is hot), key=lambda r: (-r['n'], r['name']))
    items = ''
    for i, r in enumerate(rows, 1):
        name = (f'<a href="{depth}{r["href"]}">{esc(r["name"])}</a>' if r['href'] else esc(r['name']))
        style = f' style="--team:{esc(r["color"])}"' if r['color'] else ''
        items += (f'<li class="sk-row{" sk-extra" if i > SHOWN else ""}"{style}><span class="sk-rank">#{i}</span>'
                  f'<span class="sk-team"><span class="sk-name">{name}</span>'
                  f'<span class="sk-sub">{esc(r["code"])} &bull; {r["n"]} game {words[r["kind"]][1]} streak</span></span>'
                  f'<span class="sk-n">{r["n"]}</span></li>')
    body = (f'<ol class="sk-list">{items}</ol>' + (f'<button class="sk-all" type="button">Show all {len(rows)}</button>' if len(rows) > SHOWN else '')
            if rows else f'<p class="sk-empty">No {"hot" if hot else "cold"} streaks of {MIN_STREAK}+ games right now.</p>')
    return (f'<div class="sk-card {"hot" if hot else "cold"}"><h3><span class="sk-icon" aria-hidden="true">{icon}</span>{title}</h3>'
            f'{body}</div>')


def build(nhl_data, colors, live, depth='../'):
    """The page body. live: sport keys in season."""
    sport_pills, panels = '', ''
    first = None
    for sp in sports.SPORTS:
        if sp['key'] not in live:
            continue
        if sp['key'] == 'nhl':
            lists = nhl_lists(nhl_data, colors)
        else:
            path = os.path.join(ROOT, sp['slug'], 'data.json')
            lists = sport_lists(sp, json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {})
        first = first or sp['key']
        on = sp['key'] == first
        sport_pills += (f'<button class="seg-btn" type="button" data-sport="{sp["key"]}" aria-pressed="{str(on).lower()}">'
                        f'{icons.sport_icon(sp)}{esc(sp["label"])}</button>')
        ms = markets(sp)
        # open on the first market that has a streak
        start = next((i for i, (m, _, _) in enumerate(ms) if lists.get(m)), 0)
        mkt_pills = ''.join(f'<button class="seg-btn" type="button" data-mkt="{m}" aria-pressed="{str(i == start).lower()}">{esc(lbl)}</button>'
                            for i, (m, lbl, _) in enumerate(ms))
        cards = ''.join(
            f'<div class="sk-mkt" data-mkt="{m}"{"" if i == start else " hidden"}><p class="sk-desc">{esc(desc)}</p>'
            f'<div class="sk-grid">{streak_list(lists.get(m, []), True, m, depth)}{streak_list(lists.get(m, []), False, m, depth)}</div></div>'
            for i, (m, lbl, desc) in enumerate(ms))
        panels += (f'<section class="sk-sport" data-sport="{sp["key"]}"{"" if on else " hidden"}>'
                   f'<h2>{esc(sp["label"])} &middot; {esc(sp["segments"][0]["label"])}</h2>'
                   f'<div class="seg-toggle sk-mkts">{mkt_pills}</div>{cards}</section>')
    if not first:
        return '<section class="hp-sec sk"><h1>Streaks</h1><p class="hp-empty">No sports are in season right now.</p></section>'
    return (f'<section class="hp-sec sk"><h1>Streaks</h1>'
            f'<p class="lead">Teams on a run of {MIN_STREAK} or more straight results in the opening segment: the 1st period, quarter, half or inning. '
            f'Counted from each team&rsquo;s most recent game; a push or tie ends a streak. Spreads and totals count games with saved odds.</p>'
            f'<div class="seg-toggle sk-sports">{sport_pills}</div>{panels}</section>{JS}')


JS = '''<script>
(function () {
  var root = document.querySelector('.sk');
  if (!root) return;
  root.addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    if (b.classList.contains('sk-all')) {
      b.parentNode.querySelectorAll('.sk-extra').forEach(function (r) { r.classList.remove('sk-extra'); });
      b.remove();
      return;
    }
    var key = b.dataset.sport ? 'sport' : b.dataset.mkt ? 'mkt' : null;
    if (!key) return;
    var scope = key === 'sport' ? root : b.closest('.sk-sport');
    b.parentNode.querySelectorAll('button').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
    scope.querySelectorAll(key === 'sport' ? '.sk-sport' : '.sk-mkt').forEach(function (p) {
      p.hidden = p.dataset[key] !== b.dataset[key];
    });
  });
})();
</script>'''


def write(template, nhl_data, logo_svg, now_utc=None):
    """streaks/index.html, with the site nav."""
    from datetime import datetime, timedelta, timezone
    now_utc = now_utc or datetime.now(timezone.utc)
    today = now_utc.astimezone(home.ET).date().isoformat()
    by_sport, _ = home.collect(template, nhl_data)
    status = [(sp,) + home.sport_status(sp, by_sport.get(sp['key'], {}), today) for sp in sports.SPORTS]
    # in season with games coming up: a season that just ended (still LIVE on
    # the home page for two weeks, for playoff gaps) would show stale streaks
    soon = (now_utc.astimezone(home.ET).date() + timedelta(days=7)).isoformat()
    live = {s[0]['key'] for s in status if s[2] and any(today <= d <= soon for d in by_sport.get(s[0]['key'], {}))}
    body = build(nhl_data, home.nhl_colors(template), live)
    page = home.page('RTYB — Streaks', 'Hot and cold streaks of 4+ games in the 1st period, quarter, half and inning, for every sport in season.',
                     body, status, depth='../').replace('__LOGO_SVG__', logo_svg)
    os.makedirs(os.path.join(ROOT, 'streaks'), exist_ok=True)
    with open(os.path.join(ROOT, 'streaks', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(page)
    return {'sports': len(live)}
