#!/usr/bin/env python3
"""
Snapshot public HackerOne profile stats into data/hackerone.json.

HackerOne has no embeddable badge of its own, but its GraphQL endpoint serves
public profile fields without auth. The browser can't call it directly (CORS),
so the numbers are pulled at build time and the badge renders from local JSON.

    python3 scripts/build_hackerone.py [username]
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

USERNAME = sys.argv[1] if len(sys.argv) > 1 else '0xadham'
ENDPOINT = 'https://hackerone.com/graphql'
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'hackerone.json')

QUERY = """
query ($handle: String!) {
  user(username: $handle) {
    username
    name
    profile_picture(size: medium)
    reputation
    rank
    signal
    impact
    bio
    location
    created_at
  }
}
"""


def fetch():
    payload = json.dumps({'query': QUERY, 'variables': {'handle': USERNAME}}).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Mozilla/5.0 (0xsponge.me profile badge)',
        },
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        body = json.load(r)
    if body.get('errors'):
        raise SystemExit('hackerone graphql error: %s' % body['errors'])
    user = (body.get('data') or {}).get('user')
    if not user:
        raise SystemExit('no such hackerone user: %s' % USERNAME)
    return user


def main():
    user = fetch()
    snapshot = {
        'username': user['username'],
        'profile_url': 'https://hackerone.com/%s?type=user' % user['username'],
        'avatar': user.get('profile_picture'),
        'bio': user.get('bio'),
        'location': user.get('location'),
        'joined': (user.get('created_at') or '')[:10],
        'reputation': user.get('reputation'),
        'rank': user.get('rank'),
        # signal/impact come back as long floats; one decimal is all the badge shows
        'signal': round(user['signal'], 2) if user.get('signal') is not None else None,
        'impact': round(user['impact'], 2) if user.get('impact') is not None else None,
        'updated': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, indent=2)
        f.write('\n')

    print('hackerone: rep %s · rank %s · signal %s · impact %s' % (
        snapshot['reputation'], snapshot['rank'], snapshot['signal'], snapshot['impact']))


if __name__ == '__main__':
    main()
