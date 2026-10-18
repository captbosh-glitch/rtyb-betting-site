"""
League icons: the sport's ball in full color -- puck (NHL), football (NFL,
NCAAF), basketball (NBA, WNBA, NCAAB), baseball (MLB). Colors are CSS
classes on the --ball-* tokens in template.html, so the outlines can change
with the theme (a black puck needs a light rim on dark; a white baseball
needs a gray edge on light).

  sport_icon('nhl')  -> inline <svg>, or '' for a sport with no icon

Also the team-logo markup shared by the build (team lists, team pages,
home page): logo_html() shows the light logo, and the dark-background
version when there is one, switched by CSS with the theme (.tlogo in
template.html), so it works on static pages.
"""
import json
import os

import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOGO_INDEX = {}


def logo_index(sport_key):
    """{slug: {"dark": bool}} from assets/logos/{sport}/index.json."""
    if sport_key not in _LOGO_INDEX:
        path = os.path.join(ROOT, 'assets', 'logos', sport_key, 'index.json')
        _LOGO_INDEX[sport_key] = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    return _LOGO_INDEX[sport_key]


def logo_html(light_src, dark_src, size, alt=''):
    """Team logo at `size` px; dark_src (or None) is shown on dark themes."""
    style = f'width:{size}px;height:{size}px'
    if not dark_src:
        return f'<span class="tlogo" style="{style}"><img src="{light_src}" alt="{alt}" loading="lazy"></span>'
    return (f'<span class="tlogo" style="{style}"><img class="tl-light" src="{light_src}" alt="{alt}" loading="lazy">'
            f'<img class="tl-dark" src="{dark_src}" alt="{alt}" loading="lazy"></span>')


def team_logo(sport_key, slug, size, root='__ROOT__/', alt=''):
    """Logo markup for a non-NHL team, or '' when it has no cached logo.
    `root` prefixes the asset path (pages swap __ROOT__/ for their depth)."""
    info = logo_index(sport_key).get(slug)
    if info is None:
        return ''
    base = f'{root}assets/logos/{sport_key}/{slug}'
    return logo_html(f'{base}.png', f'{base}-dark.png' if info.get('dark') else None, size, alt)


def puck():
    ticks = ''.join(f'<line x1="{x}" y1="15.2" x2="{x}" y2="20.6"/>' for x in (5, 8.7, 12.4, 16, 19.6, 23.3, 27))
    return ('<ellipse class="bi-puck-side" cx="16" cy="21" rx="14.5" ry="6"/>'
            '<rect class="bi-puck-side" x="1.5" y="12" width="29" height="9"/>'
            f'<g class="bi-puck-grip" stroke-width="1" stroke-linecap="round">{ticks}</g>'
            '<ellipse class="bi-puck-top" cx="16" cy="12" rx="14.5" ry="6"/>'
            '<ellipse class="bi-puck-shine" cx="12" cy="10.6" rx="5.5" ry="1.8"/>'
            '<path class="bi-rim" d="M1.5 12 V21 A14.5 6 0 0 0 30.5 21 V12" fill="none" stroke-width="1"/>')


def football(stripes=True):
    laces = ''.join(f'<line x1="{x}" y1="14.4" x2="{x}" y2="17.6"/>' for x in (12.6, 14.9, 17.1, 19.4))
    # Rotated and scaled up so it fills the same box as the round balls.
    return ('<g transform="rotate(-35 16 16) translate(16 16) scale(1.16) translate(-16 -16)">'
            # light outline under the leather (like the puck's rim) so it shows on dark
            '<path class="bi-leather-rim" d="M2.5 16 Q16 3 29.5 16 Q16 29 2.5 16 Z" fill="none" stroke-width="2.4" stroke-linejoin="round"/>'
            '<path class="bi-leather" d="M2.5 16 Q16 3 29.5 16 Q16 29 2.5 16 Z" stroke-width="1" stroke-linejoin="round"/>'
            + ('<path class="bi-stripe" d="M7.2 11.4 Q8.7 16 7.2 20.6 M24.8 11.4 Q23.3 16 24.8 20.6" fill="none" stroke-width="1.4"/>' if stripes else '') +
            f'<g class="bi-lace" stroke-width="1.2" stroke-linecap="round"><line x1="11.3" y1="16" x2="20.7" y2="16"/>{laces}</g>'
            '</g>')


def basketball():
    return ('<circle class="bi-basketball" cx="16" cy="16" r="13" stroke-width="1.1"/>'
            '<g class="bi-seam" fill="none" stroke-width="1.3" stroke-linecap="round">'
            '<line x1="16" y1="3" x2="16" y2="29"/><line x1="3" y1="16" x2="29" y2="16"/>'
            '<path d="M7.2 6.4 Q12.5 16 7.2 25.6"/><path d="M24.8 6.4 Q19.5 16 24.8 25.6"/></g>')


def pro_football():
    # NFL balls have no white stripes; college balls (NCAAF) do.
    return football(stripes=False)


def college_basketball():
    # Same seams as the NBA ball, two-tone like college game balls: lighter
    # side panels (outside the curved seams), deeper orange in the middle.
    return ('<circle class="bi-cbb-dark" cx="16" cy="16" r="13"/>'
            '<path class="bi-cbb-light" d="M7.2 6.4 Q12.5 16 7.2 25.6 A13 13 0 0 1 7.2 6.4 Z"/>'
            '<path class="bi-cbb-light" d="M24.8 6.4 Q19.5 16 24.8 25.6 A13 13 0 0 0 24.8 6.4 Z"/>'
            '<g class="bi-seam" fill="none" stroke-width="1.3" stroke-linecap="round">'
            '<line x1="16" y1="3" x2="16" y2="29"/><line x1="3" y1="16" x2="29" y2="16"/>'
            '<path d="M7.2 6.4 Q12.5 16 7.2 25.6"/><path d="M24.8 6.4 Q19.5 16 24.8 25.6"/></g>'
            '<circle class="bi-cbb-edge" cx="16" cy="16" r="13" fill="none" stroke-width="1.1"/>')


def wnba_basketball():
    # The WNBA ball: the regular basketball turned 90 degrees, so the curved
    # seams run across the top and bottom, bowing out toward the edges, with
    # its panels: white cap, orange band to the center line, white band,
    # orange cap, in about equal bands. (Seam ends sit on the r=13 circle
    # at y=11 and y=21, bowing gently to y=9 and y=23.)
    upper = 'M4 11 Q16 7 28 11'
    lower = 'M4 21 Q16 25 28 21'
    return ('<circle class="bi-wnba-white" cx="16" cy="16" r="13"/>'
            '<path class="bi-wnba-orange" d="M4 11 Q16 7 28 11 A13 13 0 0 1 29 16 L3 16 A13 13 0 0 1 4 11 Z"/>'
            '<path class="bi-wnba-orange" d="M4 21 Q16 25 28 21 A13 13 0 0 1 4 21 Z"/>'
            '<g class="bi-seam" fill="none" stroke-width="1.3" stroke-linecap="round">'
            f'<line x1="3" y1="16" x2="29" y2="16"/><line x1="16" y1="3" x2="16" y2="29"/>'
            f'<path d="{upper}"/><path d="{lower}"/></g>'
            '<circle class="bi-wnba-edge" cx="16" cy="16" r="13" fill="none" stroke-width="1.1"/>')


def baseball():
    return ('<circle class="bi-baseball" cx="16" cy="16" r="13" stroke-width="1.1"/>'
            '<g class="bi-stitch" fill="none" stroke-linecap="round">'
            '<path d="M8.6 5.4 Q14.2 16 8.6 26.6" stroke-width="1"/>'
            '<path d="M23.4 5.4 Q17.8 16 23.4 26.6" stroke-width="1"/>'
            '<path d="M8.6 5.4 Q14.2 16 8.6 26.6" stroke-width="2.6" stroke-dasharray="0.9 1.9" stroke-linecap="butt" opacity="0.9"/>'
            '<path d="M23.4 5.4 Q17.8 16 23.4 26.6" stroke-width="2.6" stroke-dasharray="0.9 1.9" stroke-linecap="butt" opacity="0.9"/>'
            '</g>')


ICONS = {'puck': puck, 'football': football, 'pro_football': pro_football, 'basketball': basketball,
         'college_basketball': college_basketball, 'wnba_basketball': wnba_basketball, 'baseball': baseball}

# Which ball each league gets.
SPORT_ICON = {'nhl': 'puck', 'nfl': 'pro_football', 'ncaaf': 'football',
              'nba': 'basketball', 'wnba': 'wnba_basketball', 'ncaab': 'college_basketball', 'mlb': 'baseball'}


def sport_icon(sport, cls=''):
    key = sport if isinstance(sport, str) else sport['key']
    kind = SPORT_ICON.get(key)
    if not kind:
        return ''
    return (f'<svg class="sport-icon{" " + cls if cls else ""}" viewBox="1 1 30 30" '
            f'aria-hidden="true" focusable="false">{ICONS[kind]()}</svg>')


assert set(SPORT_ICON) == {s['key'] for s in sports.SPORTS}, 'every sport in sports.py needs an icon'
