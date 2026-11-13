"""
The Daily: published recaps, previews and columns.

Pieces are Markdown files with a front-matter block, in content/published/
(the admin's Publish button moves them there from content/drafts/ or
content/columns/):

  ---
  title: "NHL First Period Betting Recap — Nov 24, 2026"
  sport: nhl            (recaps and previews)
  kind: recap           recap | preview | column
  date: 2026-11-24
  slug: why-the-first-period   (columns; else the file name)
  ---
  **The hook line.** Then the body...

Pages: /daily/ (everything, newest first), /{sport slug}/recap/{date}/,
/{sport slug}/preview/{date}/ and /column/{slug}/. Every sport in
scripts/sports.py can have them; football's are weekly (the Weekend Recap
and the Week Preview). The latest recap and preview also show on the home
page's Daily section, the sport's hub (scripts/hub.py) and the top of its
Matchups page (inject_arena).
"""
import html
import json
import os
import re
from datetime import date

import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLISHED = os.path.join(ROOT, 'content', 'published')
KIND = {'recap': ('The Morning Run', 'recap'), 'preview': ('On Tap', 'preview'), 'column': ('Running Tab', 'column')}
WEEKLY_KIND = {'recap': 'Weekend Recap', 'preview': 'Week Preview'}
FOOT = '<p class="dp-21">21+ only. Gambling problem? Call 1-800-GAMBLER.</p>'


def esc(s):
    return html.escape('' if s is None else str(s), quote=True)


def parse(text):
    """(front matter dict, body) of a Markdown file."""
    meta, body = {}, text
    m = re.match(r'---\n(.*?)\n---\n?', text, re.S)
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            if ':' not in line:
                continue
            k, v = line.split(':', 1)
            v = v.strip()
            try:
                v = json.loads(v) if v[:1] in '"[{' else v
            except ValueError:
                pass
            meta[k.strip()] = v
    return meta, body.strip()


def inline(s):
    s = esc(s)
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])', r'<em>\1</em>', s)
    s = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+|/[^)\s]*)\)', r'<a href="\2">\1</a>', s)
    return s


def to_html(md):
    """Paragraphs, headings, simple lists, bold, italic and links -- what
    the drafts and columns use."""
    out = []
    for block in re.split(r'\n\s*\n', md.strip()):
        lines = block.strip().splitlines()
        if not lines:
            continue
        h = re.match(r'(#{2,3})\s+(.*)', lines[0])
        if h and len(lines) == 1:
            n = len(h.group(1))
            out.append(f'<h{n}>{inline(h.group(2))}</h{n}>')
        elif all(re.match(r'[-*]\s+', x) for x in lines):
            items = [inline(re.sub(r'^[-*]\s+', '', x)) for x in lines]
            out.append('<ul>' + ''.join(f'<li>{x}</li>' for x in items) + '</ul>')
        else:
            out.append(f'<p>{inline(" ".join(x.strip() for x in lines))}</p>')
    return '\n'.join(out)


def plain(md):
    return re.sub(r'[*_#`]|\[([^\]]+)\]\([^)]*\)', lambda m: m.group(1) or '', md).strip()


def hook_and_teaser(body):
    """The bold first line (the headline on cards) and the next sentence."""
    m = re.match(r'\*\*(.+?)\*\*\s*', body)
    hook = m.group(1).strip() if m else None
    rest = plain(body[m.end():] if m else body)
    first = re.match(r'(.+?[.!?])(\s|$)', rest)
    teaser = (first.group(1) if first else rest)[:200]
    return hook, teaser


def load():
    """Published pieces, newest first."""
    out = []
    if not os.path.isdir(PUBLISHED):
        return out
    for name in sorted(os.listdir(PUBLISHED)):
        if not name.endswith('.md'):
            continue
        with open(os.path.join(PUBLISHED, name), encoding='utf-8') as f:
            meta, body = parse(f.read())
        kind = meta.get('kind') or ('column' if name.startswith('column-') else None)
        if kind not in KIND:
            continue
        day = str(meta.get('date') or '')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            continue
        sport = meta.get('sport') if kind != 'column' else None
        if kind != 'column' and sport not in sports.BY_KEY:
            continue
        slug = re.sub(r'[^a-z0-9-]+', '-', str(meta.get('slug') or name[:-3].replace('column-', '')).lower()).strip('-')
        path = f'column/{slug}/' if kind == 'column' else f"{sports.BY_KEY[sport]['slug']}/{kind}/{day}/"
        hook, teaser = hook_and_teaser(body)
        out.append({'kind': kind, 'sport': sport, 'date': day, 'slug': slug, 'path': path, 'body': body,
                    'title': meta.get('title') or hook or name[:-3], 'hook': hook, 'teaser': teaser})
    out.sort(key=lambda p: (p['date'], {'column': 2, 'preview': 1, 'recap': 0}[p['kind']]), reverse=True)
    return out


def nice_date(day):
    return date.fromisoformat(day).strftime('%A, %B %-d, %Y')


def kicker(p):
    if not p['sport']:
        return KIND[p['kind']][0]
    sp = sports.BY_KEY[p['sport']]
    name = WEEKLY_KIND[p['kind']] if sp.get('schedule') == 'week' else KIND[p['kind']][0]
    return f"{name} &middot; {sp['label']}"


def card(p, href, label=None):
    return (f'<a class="hd-card dp-card" href="{href}"><span class="hd-kicker">{label or kicker(p)}</span>'
            f'<b>{esc(p["hook"] or p["title"])}</b><span class="muted">{esc(p["teaser"])}</span>'
            f'<span class="dp-more">Read the {KIND[p["kind"]][1]} &rarr;</span></a>')


def latest(pieces, kind, sport=None):
    return next((p for p in pieces if p['kind'] == kind and (sport is None or p['sport'] == sport)), None)


def home_cards(pieces):
    """Up to three cards for the home page: the newest recap, preview and column."""
    out = []
    for kind in ('recap', 'preview', 'column'):
        p = latest(pieces, kind)
        if p:
            out.append(card(p, p['path']))
    return out


def write_pages(page, status, logo_svg, pieces=None):
    """Every piece's own page, and the /daily/ index. `page` is home.page."""
    pieces = load() if pieces is None else pieces
    for p in pieces:
        depth = '../' * p['path'].count('/')
        body = (f'<article class="hp-sec dp-piece"><span class="hd-kicker">{kicker(p)}</span>'
                f'<h1>{esc(p["title"])}</h1><p class="dp-date">{nice_date(p["date"])}</p>'
                f'<div class="dp-body">{to_html(p["body"])}</div>{FOOT}'
                f'<p class="dp-back"><a href="{depth}daily/">&larr; More from The Daily</a></p></article>')
        desc = (p['hook'] + ' ' if p['hook'] else '') + p['teaser']
        out = page(f"{p['title']} | RTYB", desc[:300], body, status, depth=depth).replace('__LOGO_SVG__', logo_svg)
        os.makedirs(os.path.join(ROOT, p['path']), exist_ok=True)
        with open(os.path.join(ROOT, p['path'], 'index.html'), 'w', encoding='utf-8') as f:
            f.write(out)
    if pieces:
        rows = ''.join(f'<li><a href="../{p["path"]}"><span class="hd-kicker">{kicker(p)} &middot; {esc(date.fromisoformat(p["date"]).strftime("%b %-d"))}</span>'
                       f'<b>{esc(p["title"])}</b><span class="muted">{esc(p["hook"] or p["teaser"])}</span></a></li>' for p in pieces)
        body = (f'<section class="hp-sec dp-index"><h1>The Daily</h1>'
                f'<p class="lead">The Morning Run (yesterday&rsquo;s recap), On Tap (today&rsquo;s preview) and the Running Tab column, '
                f'for every sport we cover. Newest first.</p><ul class="dp-list">{rows}</ul></section>')
    else:
        body = ('<section class="hp-sec hd-soon"><h1>The Daily</h1>'
                '<p class="lead">Coming soon: The Morning Run (yesterday&rsquo;s recap), On Tap (today&rsquo;s preview) and the weekly '
                'Running Tab column, for every sport we cover.</p><p><a href="../">Back to today&rsquo;s games</a></p></section>')
    out = page('RTYB — The Daily', 'Recaps, previews and the weekly column from RTYB, for first-period, first-quarter and first-half bettors.',
               body, status, depth='../').replace('__LOGO_SVG__', logo_svg)
    os.makedirs(os.path.join(ROOT, 'daily'), exist_ok=True)
    with open(os.path.join(ROOT, 'daily', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(out)
    return len(pieces)


def arena_html(pieces, sport, today):
    """The latest preview and recap for one sport, as two cards."""
    out = []
    weekly = sports.BY_KEY[sport].get('schedule') == 'week'
    for kind, when in (('preview', "today's preview"), ('recap', 'yesterday')):
        p = latest(pieces, kind, sport)
        if not p:
            continue
        name = WEEKLY_KIND[kind] if weekly else KIND[kind][0]
        label = f"{name} &middot; {when if p['date'] == today and not weekly else esc(date.fromisoformat(p['date']).strftime('%b %-d'))}"
        out.append(card(p, '/' + p['path'], label))
    return f'<div class="dp-arena">{"".join(out)}</div>' if out else ''


def inject_arena(sport_dirs, today, pieces=None):
    """Put the cards at the top of each sport's Matchups page, under its menu.
    sport_dirs: {sport: Matchups page dir}."""
    pieces = load() if pieces is None else pieces
    for sport, d in sport_dirs.items():
        path = os.path.join(ROOT, d, 'index.html')
        cards = arena_html(pieces, sport, today)
        if not cards or not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as f:
            page = f.read()
        if 'class="dp-arena"' in page:
            continue
        m = re.search(r'<nav class="sn"[^>]*>.*?</nav>', page, re.S)
        if not m:
            continue
        page = page[:m.end()] + f'<div class="dp-arena-wrap">{cards}</div>' + page[m.end():]
        with open(path, 'w', encoding='utf-8') as f:
            f.write(page)
