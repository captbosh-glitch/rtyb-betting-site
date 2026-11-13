"""
Sport registry: the one place every sport RTYB covers is defined.

The build (build_site.py) generates each sport's pages from this list:
/{slug}/matchups, /{slug}/stats, /{slug}/trends, /{slug}/teams and
/{slug}/teams/{team-slug}, plus the sport selector in the top nav. Adding a
sport means adding an entry here, not copying pages.

Field reference
  key            short id used in code and data files ("nfl")
  label          what people see in headers, nav and titles ("NCAAF")
  slug           URL folder ("college-football" -> /college-football/)
  sport_type     "period" (NHL), "spread" (football / basketball), "baseball" (MLB)
  segments       the bet windows tracked, in display order; each has a key,
                 a label, a short tag for chips and cards, and its markets
                 (a segment without 'ML' shows no moneyline / SU anywhere:
                 game cards, stats, teams, trends, picks, home, admin)
  season_start   month (1-12) the season starts, for "Soon" / return-month labels
  sections       URL folder for each section (the same for every sport)
  schedule       "day" (default) or "week": football's Matchups page and Admin
                 go week by week (ESPN's weeks: Week 1.., Wild Card, Bowls)
  launched       True = shown on the site (nav, home, Picks, Streaks).
                 False = hidden: its data is still fetched, graded and built,
                 its pages still load by URL (noindexed), but nothing links
                 to them. Turning a sport on is this one line.
"""

SPREAD_MARKETS = ['ATS', 'ML', 'Total']
NO_ML_MARKETS = ['ATS', 'Total']

SPORTS = [
    {
        'key': 'nhl', 'label': 'NHL', 'slug': 'nhl', 'sport_type': 'period',
        'launched': True,
        'segments': [
            {'key': '1p', 'label': '1st Period', 'tag': '1P', 'markets': ['ML', 'O/U 1.5', 'BTTS']},
        ],
        'season_start': 10,
        'sections': {'games': 'matchups', 'stats': 'stats', 'trends': 'trends', 'odds': 'odds', 'teams': 'teams'},
    },
    {
        'key': 'nfl', 'label': 'NFL', 'slug': 'nfl', 'sport_type': 'spread', 'schedule': 'week',
        'launched': False,
        'segments': [
            {'key': '1q', 'label': '1st Quarter', 'tag': '1Q', 'markets': SPREAD_MARKETS},
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 9,
    },
    {
        'key': 'nba', 'label': 'NBA', 'slug': 'nba', 'sport_type': 'spread',
        'launched': True,
        'segments': [
            {'key': '1q', 'label': '1st Quarter', 'tag': '1Q', 'markets': SPREAD_MARKETS},
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 10,
    },
    {
        'key': 'wnba', 'label': 'WNBA', 'slug': 'wnba', 'sport_type': 'spread',
        'launched': False,
        'segments': [
            {'key': '1q', 'label': '1st Quarter', 'tag': '1Q', 'markets': SPREAD_MARKETS},
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 5,
    },
    {
        'key': 'mlb', 'label': 'MLB', 'slug': 'mlb', 'sport_type': 'baseball',
        'launched': False,
        'segments': [
            {'key': '1i', 'label': '1st Inning', 'tag': 'NRFI', 'markets': ['NRFI/YRFI']},
            {'key': 'f5', 'label': 'First Five Innings', 'tag': 'F5', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 3,
    },
    {
        'key': 'ncaaf', 'label': 'NCAAF', 'slug': 'college-football', 'sport_type': 'spread', 'schedule': 'week',
        'launched': False,
        'segments': [
            {'key': '1q', 'label': '1st Quarter', 'tag': '1Q', 'markets': SPREAD_MARKETS},
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 8,
    },
    {
        'key': 'ncaab', 'label': 'NCAAB', 'slug': 'college-basketball', 'sport_type': 'spread',
        'launched': False,
        'segments': [
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 11,
    },
]

# 'odds' is the book-by-book comparison page (Unabated feed). The 'games'
# section is the Matchups page (/{slug}/matchups/; /{slug}/games/ forwards).
DEFAULT_SECTIONS = {'games': 'matchups', 'stats': 'stats', 'trends': 'trends', 'odds': 'odds', 'teams': 'teams'}
SECTION_LABELS = {'games': 'Matchups', 'stats': 'Stats', 'trends': 'Trends', 'odds': 'Odds', 'teams': 'Teams'}
OLD_SECTION_DIRS = {'games': 'games'}   # moved sections: old folder -> a forwarding stub
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']

for _s in SPORTS:
    _s.setdefault('sections', dict(DEFAULT_SECTIONS))
    _s.setdefault('schedule', 'day')

def has_ml(seg):
    """Whether a segment tracks the moneyline (SU); one with NO_ML_MARKETS doesn't."""
    return 'ML' in (seg.get('markets') or ['ML'])


# ---- Sport families (see CLAUDE.md) --------------------------------------
# Pages are driven from these, never from per-sport copies: a page change
# applies to every sport in the same session.
#
#   period  NHL, MLB: Yes/No style markets (BTTS, YRFI / NRFI)
#   spread  NBA, WNBA, NCAAB, NFL, NCAAF: Spread, Total, Moneyline
#
# calendar: 'daily', or 'weekly' (NFL, NCAAF: the date bar, calendar and
# day records become weeks).
# markets: the Odds / Trends / Stats tabs in order, as (segment, feed key,
# label, kind). kind 'yn' = a two-row Over/Yes over Under/No market (top row
# is always Over / Yes); 'ml3' = 3-way (away, Tie, home); 'side' = away/home.
# A market only shows where there's data for it.
FAMILY = {'nhl': 'period', 'mlb': 'period',
          'nba': 'spread', 'wnba': 'spread', 'ncaab': 'spread', 'nfl': 'spread', 'ncaaf': 'spread'}
# 3-way ML is NHL only (CLAUDE.md)
SPREAD_FAMILY_MARKETS = [('ats', 'Spread', 'side'), ('total', 'Total', 'yn'), ('ml', 'Moneyline', 'side')]
FAMILY_MARKETS = {
    'nhl': [('1p', 'ml', 'Moneyline', 'side'), ('1p', 'total', 'Total 1.5', 'yn'), ('1p', 'btts', 'BTTS', 'yn'),
            ('1p', 'ml3', '3-way ML', 'ml3')],
    'mlb': [('1i', 'rfi', 'NRFI/YRFI', 'yn'), ('f5', 'ml', 'F5 Moneyline', 'side'), ('f5', 'ats', 'F5 Run Line', 'side'),
            ('f5', 'total', 'F5 Total', 'yn')],
}
# Yes/No labels per yn market (top row first)
YES_NO = {'total': ('Over', 'Under'), 'btts': ('Yes', 'No'), 'rfi': ('YRFI', 'NRFI')}
# the words each sport uses for its segments
SEGMENT_WORDS = {'1p': '1st period', '1i': '1st inning', 'f5': 'First 5', '1q': '1st quarter', '1h': '1st half'}

for _s in SPORTS:
    _s['family'] = FAMILY[_s['key']]
    _s['calendar'] = 'weekly' if _s.get('schedule') == 'week' else 'daily'
    _s['family_markets'] = FAMILY_MARKETS.get(_s['key']) or [
        (seg['key'], m, label, kind) for seg in _s['segments'] for m, label, kind in SPREAD_FAMILY_MARKETS
        if m != 'ml' or has_ml(seg)]

BY_KEY = {s['key']: s for s in SPORTS}
# the sports shown on the site, in nav order
LAUNCHED = [s for s in SPORTS if s.get('launched')]


def is_launched(key):
    return bool(BY_KEY.get(key, {}).get('launched'))


def section_path(sport, section):
    """Root-relative URL for a sport's section, e.g. ('nfl', 'stats') -> /nfl/stats/."""
    s = BY_KEY[sport] if isinstance(sport, str) else sport
    return f"/{s['slug']}/{s['sections'][section]}/"


def segment_summary(sport):
    """'1st Quarter and 1st Half' -- for page descriptions."""
    labels = [seg['label'] for seg in sport['segments']]
    return labels[0] if len(labels) == 1 else ', '.join(labels[:-1]) + ' and ' + labels[-1]
