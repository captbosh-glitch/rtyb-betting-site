"""
Shared trend rules for every sport: how strong a trend is, the minimum
samples before one shows, and how records read from the bettor's side.

Used at build time by league_trends.py (NHL) and sport_build.py (NFL,
NCAAF, NBA, WNBA, MLB). The same numbers go into each sport's data.json as
"trendRules", so the pages (NHL in template.html, the rest in
assets/sport.js) apply exactly these thresholds to team trends too.

Strength = how far a trend's rate sits from its base rate, in standard
errors:  (rate - base) / sqrt(base * (1 - base) / n)
  base = 50% for moneyline / ATS sides, the league rate for totals and BTTS;
  n    = decisions (W + L; ties and pushes don't count).
Labels: weak < 1, moderate 1-2, strong >= 2. Weak trends are shown muted
and left out of the odds-row highlight and the per-market tallies.
"""
import math

# Tune here.
RULES = {
    'league_min': 30,        # league trends: decisions (ML / ATS) or games (totals, BTTS)
    'team_rate_min': 15,     # team season-rate trends: same units
    'streak_min': 4,         # team streaks show at this length
    'moderate': 1.0,         # strength cut-offs
    'strong': 2.0,
    'min_units': 0.5,        # a bettor-side trend with saved prices must be at least this many units up
    'shown': 8,              # league trends kept per slate
}


def strength(rate, base, n):
    """Standard errors between rate and base over n decisions; 0 when it
    can't be computed."""
    if rate is None or not n or base <= 0 or base >= 1:
        return 0.0
    return (rate - base) / math.sqrt(base * (1 - base) / n)


def label(z):
    a = abs(z)
    if a >= RULES['strong']:
        return 'strong'
    if a >= RULES['moderate']:
        return 'moderate'
    return 'weak'


def record_text(w, l, t, push_word='push'):
    """'39–30 (8 push)' -- W–L from the bettor's side, pushes noted."""
    base = f'{w}–{l}'
    return base + (f' ({t} {push_word})' if t else '')


def for_page():
    """The rules the pages need (into each sport's data.json)."""
    return dict(RULES)
