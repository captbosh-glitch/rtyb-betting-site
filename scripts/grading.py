"""
Grading engine for the non-NHL sports: turns a game's line score plus the
odds saved in the admin (data_admin/odds/{sport}.json) into a result for
every segment + market. No I/O here -- build_site.py feeds it games and
odds and stores what comes back; tests/test_grading.py covers the rules.

Units match NHL's (template.html winUnits/betUnits): 1 unit = $100 staked.
A win pays at the price (-110 -> +0.91u, +150 -> +1.5u), a loss is -1u,
and pushes, ties and No Action are 0u. A market with no saved price gets
units None -- left out of unit totals rather than counted as 0 or a loss.

Input game (as the loaders build it):
  {"away_ls": [..], "home_ls": [..],   points / runs per period or inning
   "periods_done": n}                  periods (MLB: full innings, both
                                       halves) that are finished; a final
                                       game counts every period played
   "final": bool}                      the game is over (or called): MLB
                                       segments it never reached are No
                                       Action instead of "not yet graded"

Output per segment (None when the segment isn't finished yet):
  spread sports  {"su":    {"away": {result, units}, "home": {...}},   W / L / T
                  "ats":   {"away": {...}, "home": {...}} | None,      W / L / P
                  "total": {"over": {...}, "under": {...}, "line", "points"} | None,
                  "score": {"away", "home"}}                            O-side W / L / P
  MLB "1i"       {"nrfi_yrfi": {"yrfi": {...}, "nrfi": {...}}, "runs", "score"}  W / L, or NA
  MLB "f5"       like a spread segment (su / ats / total), or every market NA

Results: W, L, P (push), T (tie, SU / ML only), NA (No Action).
"""

DEFAULT_PRICE = -110

# Periods that make up each segment. NCAAB plays halves, so its 1st half is
# period 1; football and the other basketball leagues play quarters.
SEGMENT_PERIODS = {
    'ncaab': {'1h': 1},
    'default': {'1q': 1, '1h': 2},
}


def win_units(price):
    """Profit on a 1-unit stake that wins at American odds `price`."""
    if price is None or price == 0:
        return None
    return 100 / abs(price) if price < 0 else price / 100


def bet_units(result, price):
    if result == 'L':
        return -1.0
    if result in ('P', 'T', 'NA'):
        return 0.0
    if result == 'W':
        u = win_units(price)
        return None if u is None else round(u, 4)
    return None


def side(result, price, priced=True):
    """One side of a bet. priced=False means no odds were saved: the result
    still stands (e.g. SU from a backfilled score) but units are None."""
    return {'result': result, 'units': bet_units(result, price) if priced else None}


def flip(result):
    return {'W': 'L', 'L': 'W'}.get(result, result)


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def segment_score(game, n_periods):
    """Away / home points over the first n periods, or None if they aren't
    all finished (or the line score is missing a value)."""
    if (game.get('periods_done') or 0) < n_periods:
        return None
    a, h = game.get('away_ls') or [], game.get('home_ls') or []
    if len(a) < n_periods or len(h) < n_periods:
        return None
    a, h = a[:n_periods], h[:n_periods]
    if any(num(x) is None for x in a + h):
        return None
    return {'away': sum(a), 'home': sum(h)}


def grade_su(score, ml):
    """Straight up: W / L / T, with ML units when a moneyline was saved."""
    diff = score['away'] - score['home']
    away = 'W' if diff > 0 else 'L' if diff < 0 else 'T'
    priced = bool(ml) and num(ml.get('away')) is not None and num(ml.get('home')) is not None
    return {
        'away': side(away, ml.get('away') if priced else None, priced),
        'home': side(flip(away), ml.get('home') if priced else None, priced),
    }


def grade_ats(score, ats):
    """Against the spread: away line added to the away score. Prices default
    to -110. A 0.5 line can't push; a tie goes to the +0.5 side."""
    if not ats or not ats.get('away') or num(ats['away'].get('line')) is None:
        return None
    margin = score['away'] + ats['away']['line'] - score['home']
    away = 'W' if margin > 0 else 'L' if margin < 0 else 'P'
    pa = ats['away'].get('price')
    ph = (ats.get('home') or {}).get('price')
    return {
        'away': side(away, DEFAULT_PRICE if pa is None else pa),
        'home': side(flip(away), DEFAULT_PRICE if ph is None else ph),
    }


def grade_total(score, total):
    """Over / Under: a whole-number line can push."""
    if not total or num(total.get('line')) is None:
        return None
    pts = score['away'] + score['home']
    over = 'W' if pts > total['line'] else 'L' if pts < total['line'] else 'P'
    po, pu = total.get('over'), total.get('under')
    return {
        'over': side(over, DEFAULT_PRICE if po is None else po),
        'under': side(flip(over), DEFAULT_PRICE if pu is None else pu),
        'line': total['line'],
        'points': pts,
    }


def grade_spread_segment(score, odds):
    odds = odds or {}
    return {
        'su': grade_su(score, odds.get('ml') or {}),
        'ats': grade_ats(score, odds.get('ats')),
        'total': grade_total(score, odds.get('total')),
        'score': score,
    }


def no_action_spread(odds):
    """F5 when fewer than 5 innings were played: every market is NA (0u)."""
    odds = odds or {}
    na = {'result': 'NA', 'units': 0.0}
    return {
        'su': {'away': dict(na), 'home': dict(na)},
        'ats': {'away': dict(na), 'home': dict(na)} if odds.get('ats') else None,
        'total': ({'over': dict(na), 'under': dict(na), 'line': odds['total'].get('line'), 'points': None}
                  if odds.get('total') else None),
        'score': None,
        'no_action': True,
    }


def grade_first_inning(game, odds):
    """NRFI / YRFI. No pushes. Graded once the bottom of the 1st is done;
    a game called before that is No Action."""
    m = ((odds or {}).get('nrfi_yrfi')) or {}
    priced = num(m.get('yrfi')) is not None and num(m.get('nrfi')) is not None
    score = segment_score(game, 1)
    if score is None:
        if game.get('final'):
            na = {'result': 'NA', 'units': 0.0}
            return {'nrfi_yrfi': {'yrfi': dict(na), 'nrfi': dict(na)}, 'runs': None, 'score': None, 'no_action': True}
        return None
    runs = score['away'] + score['home']
    yrfi = 'W' if runs > 0 else 'L'
    return {
        'nrfi_yrfi': {
            'yrfi': side(yrfi, m.get('yrfi'), priced),
            'nrfi': side(flip(yrfi), m.get('nrfi'), priced),
        },
        'runs': runs,
        'score': score,
    }


def grade_first_five(game, odds):
    score = segment_score(game, 5)
    if score is None:
        return no_action_spread(odds) if game.get('final') else None
    return grade_spread_segment(score, odds)


def grade_game(sport_key, sport_type, segments, game, odds_game):
    """Every segment of one game. `segments` are the registry's segment keys;
    `odds_game` is the admin entry for this game (or None)."""
    seg_odds = (odds_game or {}).get('segments') or {}
    out = {}
    for seg in segments:
        odds = seg_odds.get(seg)
        if sport_type == 'baseball':
            out[seg] = grade_first_inning(game, odds) if seg == '1i' else grade_first_five(game, odds)
        else:
            periods = SEGMENT_PERIODS.get(sport_key, SEGMENT_PERIODS['default'])[seg]
            score = segment_score(game, periods)
            out[seg] = grade_spread_segment(score, odds) if score else None
    return out
