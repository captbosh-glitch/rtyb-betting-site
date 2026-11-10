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
Labels need both an edge and profit: strong = strength >= 2 and at least
+0.10u per priced bet; moderate = strength >= 1 and +0.05u per bet; the
rest are weak (a trend with no saved prices goes by strength alone). Weak
trends are shown muted, their bets aren't recommended, and they're left out
of the odds-row highlight, the per-market tallies and the daily record.

Each slate's record counts every recommended bet once, even when two
trends point at it; a bet backed by several trends says "N trends agree".
"""
import math

# Tune here.
RULES = {
    'league_min': 30,        # league trends: decisions (ML / ATS) or games (totals, BTTS)
    'team_rate_min': 15,     # team season-rate trends: same units
    'streak_min': 4,         # team streaks show at this length
    'moderate': 1.0,         # strength cut-offs
    'strong': 2.0,
    'moderate_upb': 0.05,    # ... and units per priced bet
    'strong_upb': 0.10,
    'min_units': 0.5,        # a bettor-side trend with saved prices must be at least this many units up
    'shown': 8,              # league trends kept per slate
}


def strength(rate, base, n):
    """Standard errors between rate and base over n decisions; 0 when it
    can't be computed."""
    if rate is None or not n or base <= 0 or base >= 1:
        return 0.0
    return (rate - base) / math.sqrt(base * (1 - base) / n)


def label(z, units=None, bets=None):
    """'strong' / 'moderate' / 'weak' from strength z and, when the trend
    has saved prices, units per priced bet."""
    a = abs(z)
    upb = units / bets if units is not None and bets else None
    for level in ('strong', 'moderate'):
        if a >= RULES[level] and (upb is None or upb >= RULES[level + '_upb']):
            return level
    return 'weak'


def tooltip():
    """One line on how strength is labelled (the pages' info tip)."""
    R = RULES
    return (f"Strong: {R['strong']:g}+ standard errors past the base rate and +{R['strong_upb']:.2f}u or more per bet. "
            f"Moderate: {R['moderate']:g}+ and +{R['moderate_upb']:.2f}u. Weak: anything less (muted, not a bet).")


def finish_slate(entry, sig):
    """After grading a slate: relabel each trend by today's rule, mark bets
    several trends agree on, and count the record once per bet.
    sig(pick) -> a key that two picks on the same bet share."""
    backers = {}
    for t in entry['trends']:
        t['strength'] = label(t.get('z') or 0, t.get('units'), t.get('priced') or t.get('n'))
        for p in t['games']:
            if t['strength'] != 'weak':
                backers.setdefault(sig(p), []).append(p)
    w = l = 0
    for picks in backers.values():
        for p in picks:
            p['agree'] = len(picks)
        status = picks[0].get('status')
        w += status == 'W'
        l += status == 'L'
    for t in entry['trends']:
        if t['strength'] == 'weak':
            for p in t['games']:
                p.pop('agree', None)
    entry['record'] = {'w': w, 'l': l}


def record_text(w, l, t, push_word='push'):
    """'39–30 (8 push)' -- W–L from the bettor's side, pushes noted."""
    base = f'{w}–{l}'
    return base + (f' ({t} {push_word})' if t else '')


def for_page():
    """The rules the pages need (into each sport's data.json)."""
    return dict(RULES, tip=tooltip())
