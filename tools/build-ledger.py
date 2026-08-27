#!/usr/bin/env python3
"""Regenerate the shipping ledger from a repository's git history.

Publishes only date, change type, and scope — never ticket numbers or commit
titles, which belong to the source repository.

    python3 tools/build-ledger.py <repo-path> <author-email> [--branch origin/master]
"""
import argparse, json, pathlib, re, subprocess, sys

# Order matters: a subject is labelled by the first pattern it matches. Housekeeping
# verbs are checked before the feature verbs so that routine changes are not counted
# as features.
KEYWORDS = [
    (r'\bfix|\bbroken|\bregression|\bescape|\bbreaks?\b', 'fix'),
    (r'\badd\b|\bimplement|\bbuild\b|\bsupport\b|\bsurface\b|\bwire up\b|\bshow\b|\bdisplay\b|\benable\b|\bcreate\b', 'feat'),
    (r'\bdocument|\bdocs\b', 'docs'),
    (r'\brename\b|\balign\b|\bhousekeeping|\brefactor|\bcleanup|\bupdate\b|\bscope\b|\bdefault\b|\bignore\b|\bparse\b|\baccept\b', 'chore'),
    (r'\bspec\b|\btest\b', 'test'),
]
KNOWN = {'feat', 'fix', 'chore', 'docs', 'refactor', 'perf', 'security', 'test'}
SCOPE_HINTS = ['ticket', 'automation', 'notification', 'survey', 'review', 'import',
               'user', 'saved view', 'custom field', 'portal', 'inbox', 'media', 'location']


def classify(subject):
    """Return (type, scope) for a commit subject."""
    m = re.match(r'^([a-zA-Z]+)\(([^)]+)\)!?:', subject)
    if m:
        typ, scope = m.group(1).lower(), m.group(2).lower()
    else:
        body = re.sub(r'^([A-Z]+-[\d\s+A-Z-]*):\s*', '', subject).lower()
        typ = next((t for pat, t in KEYWORDS if re.search(pat, body)), 'feat')
        scope = next((s.replace(' ', '-') for s in SCOPE_HINTS if s in body), 'general')
    if typ not in KNOWN:
        typ = 'chore'
    scope = {'ticketing': 'tickets', 'ticket': 'tickets', 'automation': 'automations'}.get(scope, scope)
    return typ, scope


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('repo')
    ap.add_argument('author')
    ap.add_argument('--branch', default='origin/master')
    args = ap.parse_args()

    out = subprocess.run(
        ['git', '-C', args.repo, 'log', args.branch, f'--author={args.author}',
         '--pretty=%ad|%s', '--date=short'],
        capture_output=True, text=True, check=True).stdout

    rows = []
    for line in out.splitlines():
        if '|' not in line:
            continue
        date, subject = line.split('|', 1)
        if not re.search(r'\(#\d+\)\s*$', subject):   # squash-merged PRs only
            continue
        typ, scope = classify(subject)
        rows.append({'d': date, 't': typ, 's': scope})

    if not rows:
        sys.exit('No merged pull requests found — check the branch and author.')
    rows.sort(key=lambda r: r['d'])

    root = pathlib.Path(__file__).resolve().parent.parent
    payload = json.dumps(rows, separators=(',', ':'))
    (root / 'data' / 'ledger.json').write_text(payload)

    app = root / 'app.js'
    app.write_text(re.sub(r'const PRS = .*?;\n', f'const PRS = {payload};\n',
                          app.read_text(), count=1, flags=re.S))

    print(f'{len(rows)} pull requests → data/ledger.json + app.js')


if __name__ == '__main__':
    main()
