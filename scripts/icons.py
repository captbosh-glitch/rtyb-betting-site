"""
Sport icons: the field marks from the logo sheet (the B3 frame with each
sport's markings -- hockey, football, basketball; baseball's diamond drawn
to match). One color, currentColor, so they follow the theme; the CSS
class .sport-icon sizes and colors them (template.html).

  sport_icon('nhl')  -> inline <svg>, or '' for a sport with no icon
"""
import sports

# Frame from the logo sheet: 66 x 44 at (8, 22); center (41, 44).
FX, FY, FW, FH = 8, 22, 66, 44
MX, MY = FX + FW / 2, FY + FH / 2


def _frame(rx=10):
    return f'<rect x="{FX}" y="{FY}" width="{FW}" height="{FH}" rx="{rx}" fill="none" stroke-width="3.8"/>'


def _ln(x1, y1, x2, y2, w=3, op=1):
    o = f' opacity="{op}"' if op != 1 else ''
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke-width="{w}"{o}/>'


def _circ(r, w=3, fill='none'):
    return f'<circle cx="{MX}" cy="{MY}" r="{r}" fill="{fill}" stroke-width="{w}"/>'


# Kept to a few heavy lines so they read at nav size (about 22px wide).
def hockey():
    blue = _ln(28, FY, 28, FY + FH, 3, 0.55) + _ln(54, FY, 54, FY + FH, 3, 0.55)
    return _frame(15) + blue + _ln(MX, FY, MX, FY + FH, 3.4) + _circ(8.5)


def football():
    ez = (f'<rect x="{FX + 2}" y="{FY + 2}" width="9" height="{FH - 4}" rx="7" fill="currentColor" stroke="none" opacity="0.45"/>'
          f'<rect x="{FX + FW - 11}" y="{FY + 2}" width="9" height="{FH - 4}" rx="7" fill="currentColor" stroke="none" opacity="0.45"/>')
    yards = ''.join(_ln(x, FY, x, FY + FH, 2.4, 0.6) for x in (29.5, 52.5))
    return _frame() + ez + yards + _ln(MX, FY, MX, FY + FH, 3.4)


def basketball():
    keys = (f'<rect x="{FX}" y="{MY - 8}" width="13" height="16" fill="none" stroke-width="3"/>'
            f'<rect x="{FX + FW - 13}" y="{MY - 8}" width="13" height="16" fill="none" stroke-width="3"/>')
    return _frame() + _ln(MX, FY, MX, FY + FH, 3) + _circ(8) + keys


def baseball():
    # Home plate at the bottom, foul lines out to the corners, the outfield
    # wall arcing across the top, and a big infield diamond with its bases.
    home, first, second, third = (MX, 63), (MX + 13, 50), (MX, 37), (MX - 13, 50)
    fouls = _ln(home[0], home[1], FX + 3, FY + 15, 2.6, 0.6) + _ln(home[0], home[1], FX + FW - 3, FY + 15, 2.6, 0.6)
    wall = f'<path d="M{FX + 3} {FY + 15} Q{MX} {FY - 4} {FX + FW - 3} {FY + 15}" fill="none" stroke-width="2.6" opacity="0.6"/>'
    diamond = (f'<path d="M{home[0]} {home[1]} L{first[0]} {first[1]} L{second[0]} {second[1]} L{third[0]} {third[1]} Z" '
               f'fill="currentColor" fill-opacity="0.22" stroke-width="3.2" stroke-linejoin="round"/>')
    bases = ''.join(f'<rect x="{x - 3}" y="{y - 3}" width="6" height="6" fill="currentColor" stroke="none" '
                    f'transform="rotate(45 {x} {y})"/>' for x, y in (first, second, third))
    return _frame() + wall + fouls + diamond + bases


ICONS = {'hockey': hockey, 'football': football, 'basketball': basketball, 'baseball': baseball}

# Which field each league gets.
SPORT_ICON = {'nhl': 'hockey', 'nfl': 'football', 'ncaaf': 'football',
              'nba': 'basketball', 'wnba': 'basketball', 'ncaab': 'basketball', 'mlb': 'baseball'}


def sport_icon(sport, cls=''):
    key = sport if isinstance(sport, str) else sport['key']
    kind = SPORT_ICON.get(key)
    if not kind:
        return ''
    return (f'<svg class="sport-icon{" " + cls if cls else ""}" viewBox="5 18 72 52" fill="none" stroke="currentColor" '
            f'stroke-linecap="round" aria-hidden="true" focusable="false">{ICONS[kind]()}</svg>')


assert set(SPORT_ICON) == {s['key'] for s in sports.SPORTS}, 'every sport in sports.py needs an icon'
