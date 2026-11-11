"""
Email signup: the Running Tab newsletter, through Beehiiv's embed forms.

Pages mark where a signup box goes with a placeholder (box(spot)); seo.finish
calls fill() on every built page, which swaps each placeholder for the
Beehiiv form. Spots: 'tab' (the home page's Running Tab / Premium section)
and 'footer' (every page).

Beehiiv's loader can show a given form only once per page (a second copy of
the same form never sizes itself), so when two spots on a page share a form
ID, the first spot in PRIORITY gets the form and the others become a "Get
the Tab" link to it. To give a spot its own form (and its own signup count
in Beehiiv, i.e. signups by source), make another form in Beehiiv and put
its ID in FORMS.

The home page's blurred trends unlock with a link to the form. When the
form reports a signup (the 'beehiiv:submitted' message), SIGNUP_JS marks
the browser as signed up: the trends unblur and every box shows "Check your
inbox to confirm." Beehiiv's own cookie hides its forms after a signup, so
the same note shows on later visits.

How the form looks (colors, button text, the header) is set in Beehiiv's
form builder, not here.
"""
import re

FORMS = {
    'tab': 'b098ab61-d396-49f3-b728-65bdf6b509d0',
    'footer': 'b098ab61-d396-49f3-b728-65bdf6b509d0',
}
PRIORITY = ('tab', 'footer')
PUBLICATION = '472a073a-28e9-4b25-9c4e-ff1a9bfe239d'   # Beehiiv's id for RTYB (from the form's config)
LOADER = 'https://subscribe-forms.beehiiv.com/v3/loader.js'
ATTRIBUTION = '<script type="text/javascript" async src="https://subscribe-forms.beehiiv.com/attribution.js"></script>'
DONE = 'You&rsquo;re on the Running Tab list. New signup? Check your inbox to confirm.'

SIGNUP_JS = '''<script>
(function() {
  var KEY = 'rtyb-tab', COOKIE = 'bhv_%s_subscribed=';
  function signedUp() {
    try { if (localStorage.getItem(KEY)) return true; } catch (e) {}
    return document.cookie.indexOf(COOKIE) >= 0;
  }
  function apply() {
    document.documentElement.classList.add('rt-subbed');
    document.querySelectorAll('.ht-blur').forEach(function(el) { el.removeAttribute('aria-hidden'); });
  }
  window.addEventListener('message', function(e) {
    if (e.origin !== 'https://subscribe-forms.beehiiv.com' || !e.data || e.data.type !== 'beehiiv:submitted') return;
    try { localStorage.setItem(KEY, '1'); } catch (x) {}
    apply();
  });
  if (signedUp()) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply); else apply();
  }
})();
</script>''' % PUBLICATION


def box(spot):
    return f'<!--signup:{spot}-->'


def embed(spot):
    return (f'<div class="rt-signup" id="signup-{spot}"><div class="rt-form">'
            f'<script async src="{LOADER}" data-beehiiv-form="{FORMS[spot]}"></script></div>'
            f'<p class="rt-done" role="status">{DONE}</p></div>')


def fill(page_html):
    spots = re.findall(r'<!--signup:([a-z]+)-->', page_html)
    if not spots:
        return page_html
    placed = {}   # form id -> spot that shows it
    for spot in sorted(set(spots), key=lambda s: PRIORITY.index(s) if s in PRIORITY else len(PRIORITY)):
        placed.setdefault(FORMS[spot], spot)
    for spot in set(spots):
        owner = placed[FORMS[spot]]
        html = embed(spot) if owner == spot else (
            f'<p class="rt-jump"><a href="#signup-{owner}">Get the Running Tab &uarr;</a></p>')
        page_html = page_html.replace(box(spot), html, 1)
    return page_html
