/* NBA Situational Results registry (rows in assets/splits/basketball.js). */
window.RTYB_SPLITS = window.RTYB_SPLITS || {};
window.RTYB_SPLITS.nba = window.RTYB_BASKETBALL({
  divisions: true, eastWest: true, altitude: ['den', 'utah'],
  cup: { label: 'NBA Cup games', short: 'NBA Cup', def: 'NBA Cup group play and knockout games.', re: /NBA Cup/i },
});
