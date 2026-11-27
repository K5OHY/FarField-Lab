"""Checks that a NASA API key works on this computer, without ever printing the key.

Get a free key at https://api.nasa.gov (the "Generate API Key" form; it is shown at once and emailed). Put it in a file called .streamlit/secrets.toml in this folder (that file is
ignored by git), on its own line:
    NASA_API_KEY = "..."
or set it for this window only:  $env:NASA_API_KEY = "..."
Then run:  python check_nasa_key.py
"""
import requests

import donki

if not donki.key_in_use():
    raise SystemExit("No key found. Put NASA_API_KEY in .streamlit/secrets.toml (see the top of this file) and run it again.")
print(f"A key is set ({len(donki.api_key())} characters; it is not shown).")
resp = requests.get(f"{donki.BASE}/GST", params={"startDate": "2024-05-09", "endDate": "2024-05-12", "api_key": donki.api_key()}, timeout=30)
if resp.status_code in (401, 403):
    raise SystemExit("NASA refused the key (mistyped or not activated yet). Check it at api.nasa.gov and try again.")
resp.raise_for_status()
events = resp.json()
print(f"NASA accepted it: {len(events)} geomagnetic storms listed for 9 to 12 May 2024 (expected 2).")
print(f"Requests allowed an hour: {resp.headers.get('X-RateLimit-Limit', 'not stated')}; left: {resp.headers.get('X-RateLimit-Remaining', 'not stated')}.")
