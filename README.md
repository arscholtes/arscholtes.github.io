# Portfolio

A single static page. No framework, no build step, no dependencies.

```
index.html      markup
styles.css      tokens + layout
app.js          draws the shipping ledger; PR data is inlined
data/ledger.json  source data, generated from git history
tools/build-ledger.py  regenerates ledger.json + the inlined copy in app.js
posts/          blog posts, in Markdown
blog/           the blog, generated from posts/ by tools/build-blog.py
```

## Run it

Any static server, or just open `index.html` — the chart data is inlined, so it
works from `file://` too.

```bash
python3 -m http.server 8000
```

## The blog

Posts are Markdown files in `posts/`, one per post. The file name is the post's address, so
`posts/carrot-olive-oil.md` becomes `/blog/carrot-olive-oil/`. Each starts with:

```
---
title: Why the carrot page says add olive oil
date: 2026-11-17
summary: One line for the blog's front page and its feed.
---
```

Then rebuild. Everything in `blog/` is generated, so edit the post, never the page:

```bash
python3 tools/build-blog.py
```

It writes a page per post, `blog/index.html` (newest first) and `blog/feed.xml` (RSS). A YouTube
link on a line of its own becomes the video. Pushing to `master` publishes, so a post goes live
when its commit lands there.

Tests: `python3 -m unittest`

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
