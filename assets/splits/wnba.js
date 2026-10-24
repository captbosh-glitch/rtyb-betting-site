/* WNBA Situational Results registry (rows in assets/splits/basketball.js):
   no divisions, East vs. West or altitude; Commissioner's Cup instead of the
   NBA Cup; "Since last season" by default (small sample). */
window.RTYB_SPLITS = window.RTYB_SPLITS || {};
window.RTYB_SPLITS.wnba = window.RTYB_BASKETBALL({
  defaultSeason: 'since',
  cup: { label: 'Commissioner’s Cup games', short: 'Comm. Cup', def: 'Commissioner’s Cup games.', re: /Commissioner/i },
});
