"""
Per-period NHL scores from a game's goal list, for the Intermission Edge
section (NHL Stats page) and the 1st-period markets.

Two sources, one shape. Both carry the running score after every goal
(awayScore / homeScore are cumulative, not per period):
  /v1/score/{date}            games[].goals[]          -- flat, each goal has "period"
  /v1/gamecenter/{id}/landing summary.scoring[].goals[] -- grouped by period;
                              the period entries have NO score fields of
                              their own (only periodDescriptor + goals)

parse(goals, away_final, home_final, ot) returns the fields saved on each
schedule game:
  awayP1, homeP1, awayP2, homeP2, awayP3, homeP3   goals scored IN that period
  firstGoal2P                                      'away' / 'home' / None (no 2P goal)

Sanity rule (else the 2P / 3P fields are left None and the reason returned):
  regulation:  P1 + P2 + P3 == the final score, for each team
  OT / SO:     final - (P1 + P2 + P3) == 1, both teams together (the OT
               goal or the shootout winner the books add to the score)
"""

# First day of the 2026-27 regular season (build_site.py uses this too).
SEASON_START = '2026-09-29'

PERIOD_FIELDS = ('awayP2', 'homeP2', 'awayP3', 'homeP3', 'firstGoal2P')


def goals_from_score(goals):
    """[(period, awayScore, homeScore), ...] from a /v1/score goals[] list."""
    return [(g.get('period') or (g.get('periodDescriptor') or {}).get('number'),
             g.get('awayScore'), g.get('homeScore')) for g in goals or []]


def goals_from_landing(landing):
    """Same, from a /v1/gamecenter/{id}/landing payload (None if it has no
    scoring summary)."""
    scoring = ((landing or {}).get('summary') or {}).get('scoring')
    if scoring is None:
        return None
    return [((p.get('periodDescriptor') or {}).get('number'), g.get('awayScore'), g.get('homeScore'))
            for p in scoring for g in p.get('goals') or []]


def score_after(goals, period):
    """Running (away, home) score at the end of `period`."""
    a = h = 0
    for p, ga, gh in goals:
        if p is not None and p <= period and ga is not None and gh is not None:
            a, h = ga, gh
    return a, h


def parse(goals, away_final, home_final, ot):
    """(fields, error). fields always has awayP1/homeP1; the 2P / 3P fields
    are None when the sanity rule fails (error says why)."""
    goals = sorted(goals, key=lambda x: (x[0] or 0, (x[1] or 0) + (x[2] or 0)))
    s1, s2, s3 = score_after(goals, 1), score_after(goals, 2), score_after(goals, 3)
    out = {'awayP1': s1[0], 'homeP1': s1[1]}
    p2 = (s2[0] - s1[0], s2[1] - s1[1])
    p3 = (s3[0] - s2[0], s3[1] - s2[1])
    first = None
    prev = s1
    for p, ga, gh in goals:
        if p == 2:
            first = 'away' if ga > prev[0] else 'home'
            break
    err = None
    if away_final is None or home_final is None:
        err = 'no final score'
    elif min(p2 + p3) < 0:
        err = f'negative period score (2P {p2}, 3P {p3})'
    elif ot in ('OT', 'SO'):
        extra = (away_final + home_final) - (s3[0] + s3[1])
        if extra != 1:
            err = f'{ot} game: final {away_final}-{home_final} minus regulation {s3[0]}-{s3[1]} is {extra}, not 1'
    elif s3 != (away_final, home_final):
        err = f'regulation {s3[0]}-{s3[1]} != final {away_final}-{home_final}'
    if err:
        out.update({k: None for k in PERIOD_FIELDS})
    else:
        out.update({'awayP2': p2[0], 'homeP2': p2[1], 'awayP3': p3[0], 'homeP3': p3[1], 'firstGoal2P': first})
    return out, err
