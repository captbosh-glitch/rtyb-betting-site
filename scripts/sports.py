"""
Sport registry: the one place every sport RTYB covers is defined.

The build (build_site.py) generates each sport's pages from this list:
/{slug}/games, /{slug}/stats, /{slug}/trends, /{slug}/teams and
/{slug}/teams/{team-slug}, plus the sport selector in the top nav. Adding a
sport means adding an entry here, not copying pages.

Field reference
  key            short id used in code and data files ("nfl")
  label          what people see in headers, nav and titles ("NCAAF")
  slug           URL folder ("college-football" -> /college-football/)
  sport_type     "period" (NHL), "spread" (football / basketball), "baseball" (MLB)
  segments       the bet windows tracked, in display order; each has a key,
                 a label, a short tag for chips and cards, and its markets
  season_start   month (1-12) the season starts, for "Soon" / return-month labels
  sections       URL folder for each section; only NHL's Stats differs
                 (its page lives at /nhl/1st-period-stats/)
"""

SPREAD_MARKETS = ['ATS', 'ML', 'Total']

SPORTS = [
    {
        'key': 'nhl', 'label': 'NHL', 'slug': 'nhl', 'sport_type': 'period',
        'segments': [
            {'key': '1p', 'label': '1st Period', 'tag': '1P', 'markets': ['ML', 'O/U 1.5', 'BTTS']},
        ],
        'season_start': 10,
        'sections': {'games': 'games', 'stats': '1st-period-stats', 'trends': 'trends', 'teams': 'teams'},
    },
    {
        'key': 'nfl', 'label': 'NFL', 'slug': 'nfl', 'sport_type': 'spread',
        'segments': [
            {'key': '1q', 'label': '1st Quarter', 'tag': '1Q', 'markets': SPREAD_MARKETS},
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 9,
    },
    {
        'key': 'nba', 'label': 'NBA', 'slug': 'nba', 'sport_type': 'spread',
        'segments': [
            {'key': '1q', 'label': '1st Quarter', 'tag': '1Q', 'markets': SPREAD_MARKETS},
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 10,
    },
    {
        'key': 'wnba', 'label': 'WNBA', 'slug': 'wnba', 'sport_type': 'spread',
        'segments': [
            {'key': '1q', 'label': '1st Quarter', 'tag': '1Q', 'markets': SPREAD_MARKETS},
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 5,
    },
    {
        'key': 'mlb', 'label': 'MLB', 'slug': 'mlb', 'sport_type': 'baseball',
        'segments': [
            {'key': '1i', 'label': '1st Inning', 'tag': 'NRFI', 'markets': ['NRFI/YRFI']},
            {'key': 'f5', 'label': 'First Five Innings', 'tag': 'F5', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 3,
    },
    {
        'key': 'ncaaf', 'label': 'NCAAF', 'slug': 'college-football', 'sport_type': 'spread',
        'segments': [
            {'key': '1q', 'label': '1st Quarter', 'tag': '1Q', 'markets': SPREAD_MARKETS},
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 8,
    },
    {
        'key': 'ncaab', 'label': 'NCAAB', 'slug': 'college-basketball', 'sport_type': 'spread',
        'segments': [
            {'key': '1h', 'label': '1st Half', 'tag': '1H', 'markets': SPREAD_MARKETS},
        ],
        'season_start': 11,
    },
]

DEFAULT_SECTIONS = {'games': 'games', 'stats': 'stats', 'trends': 'trends', 'teams': 'teams'}
SECTION_LABELS = {'games': 'Games', 'stats': 'Stats', 'trends': 'Trends', 'teams': 'Teams'}
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']

for _s in SPORTS:
    _s.setdefault('sections', dict(DEFAULT_SECTIONS))

BY_KEY = {s['key']: s for s in SPORTS}


def section_path(sport, section):
    """Root-relative URL for a sport's section, e.g. ('nfl', 'stats') -> /nfl/stats/."""
    s = BY_KEY[sport] if isinstance(sport, str) else sport
    return f"/{s['slug']}/{s['sections'][section]}/"


def segment_summary(sport):
    """'1st Quarter and 1st Half' -- for page descriptions."""
    labels = [seg['label'] for seg in sport['segments']]
    return labels[0] if len(labels) == 1 else ', '.join(labels[:-1]) + ' and ' + labels[-1]
