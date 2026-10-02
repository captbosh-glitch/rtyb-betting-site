# RTYB Admin — setup

The Admin page (Matchups Tool + Results Tool) is a static page (`admin/index.html`)
that talks to a small Cloudflare Worker, which is the only thing that holds your
GitHub token. Same pattern as thebettorline's "Pull now" button, just doing a
direct file commit instead of firing a workflow.

## 1. Where everything goes

```
your-repo/
├── admin/
│   └── index.html              <- the Admin page itself (served at /admin/)
├── data_admin/
│   ├── matchups_draft.json     <- empty {} seed, committed once
│   ├── odds_overrides.json     <- empty {} seed, committed once
│   ├── results_draft.json      <- empty {} seed, committed once
│   └── results_overrides.json  <- empty {} seed, committed once
├── worker/
│   ├── rtyb-admin-worker.js    <- deployed separately, NOT served by GitHub Pages
│   └── wrangler.toml
├── scripts/
│   └── build_site.py           <- updated: merges the two *_overrides.json files
├── template.html                <- updated: pills grade off the 1st-period
│                                    score directly, not full-game FINAL state
└── .github/workflows/refresh.yml <- updated: publishing now also triggers a rebuild
```

Commit and push all of these as normal — `admin/` and `data_admin/` are just
ordinary files GitHub Pages serves like anything else in `nhl/`.

## 2. Deploy the Worker

```
cd worker
npm install -g wrangler      # if you don't have it
wrangler secret put GITHUB_TOKEN     # fine-grained PAT, "Contents: write" only, scoped to THIS repo
wrangler secret put ADMIN_SECRET     # the password you'll type into the Admin page
wrangler deploy
```

`wrangler deploy` prints the Worker's URL (something like
`https://rtyb-admin.<your-subdomain>.workers.dev`). Open `admin/index.html`,
find the line:

```js
var WORKER_URL = "";
```

and paste the URL in there, then commit/push that one-line change.

Also double-check the two constants at the top of `worker/rtyb-admin-worker.js`
match your actual repo:

```js
const REPO_OWNER = "captbosh-glitch";
const REPO_NAME = "rtyb-betting-site"; // <- confirm this is your real repo name
```

## 3. Using it

Go to `your-site.com/admin/` (it's not linked from the nav on purpose — same
reasoning as thebettorline's admin page: there's no real login system behind
it yet, just a shared password, so it's not worth advertising the URL
publicly). Enter the password once per browser session.

- **Matchups Tool**: pick a date, the day's scheduled matchups auto-populate
  with whatever odds are currently live (or your last saved draft). Edit the
  six fields, **Save** to keep a draft without affecting the live site, or
  **Publish** to push it live — it's picked up by the normal site rebuild
  within a minute or two.
- **Results Tool**: same date, enter the Away/Home score **after the 1st
  period**. Publishing here grades the Moneyline/Over-Under 1.5/BTTS markets
  for that game immediately, even if the full game hasn't ended yet in the
  NHL's own feed — these are all 1st-period markets, so that's the point at
  which they're actually decided.

## 4. A couple of things worth knowing

- **Single shared password, no real accounts yet.** This matches where the
  site is today (Guest/Free/Premium are still placeholders; only Admin is
  gated, and it's gated by "knows the password," not a login). If you want
  real per-person admin accounts later, that's a bigger lift — this gets you
  working Save/Publish now without blocking on it.
- **Save vs. Publish**: Save never touches the live site — it just remembers
  what you typed so the form isn't empty next time you open it. Only Publish
  commits to the files the build actually reads.
- **Publishing always wins.** Once you publish odds or a result for a game,
  that value overrides whatever the automated odds/schedule fetchers find for
  it, permanently (until you publish something different). That's
  intentional — it's meant to be the authoritative source once you've set it.
- I couldn't fully end-to-end test the Worker itself (deploying and hitting a
  live Cloudflare Worker isn't something I can do from here) — I did verify
  the GitHub Contents API read-modify-write logic, the request/response
  shapes, and that `build_site.py` correctly merges both override files
  against a local copy of your data. Worth doing one real Save + Publish on a
  low-stakes date first to confirm the whole chain works end to end on your
  side before relying on it.
