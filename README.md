# Portfolio

A single static page. No framework, no build step, no dependencies.

```
index.html      markup
styles.css      tokens + layout
app.js          draws the shipping ledger; PR data is inlined
data/ledger.json  source data, generated from git history
tools/build-ledger.py  regenerates ledger.json + the inlined copy in app.js
```

## Run it

Any static server, or just open `index.html` — the chart data is inlined, so it
works from `file://` too.

```bash
python3 -m http.server 8000
```

## Refreshing the shipping ledger

The chart is generated from real git history, not hand-maintained. Point the
script at a repo and an author email:

```bash
python3 tools/build-ledger.py /path/to/repo you@example.com
```

It writes `data/ledger.json` and rewrites the `PRS` constant at the top of
`app.js`.

Only dates, change types, and scopes are published — no ticket numbers and no
commit titles, since those belong to a private employer repo.

## Deploying

Settings → Pages → deploy from `main` / root. It is plain static files, so
anywhere else works too.
