"""Checks that a HamQTH API key works on this computer, without ever printing the key.

Put the key in a file called .streamlit/secrets.toml in this folder (that file is ignored by git), as one line:
    HAMQTH_API_KEY = "hqk_..."
or set it for this window only:  $env:HAMQTH_API_KEY = "hqk_..."
Then run:  python check_hamqth_key.py            (or with some callsigns:  python check_hamqth_key.py JM8QGN JA1SKE)
"""
import sys

import callbook

CALLS = sys.argv[1:] or ["JM8QGN", "JA1SKE", "JH3EUJ", "OK2CQR"]

if not callbook.api_key():
    sys.exit("No key found. Put HAMQTH_API_KEY in .streamlit/secrets.toml (see the top of this file) and run it again.")
print(f"A key is set ({len(callbook.api_key())} characters; it is not shown).")
for call in CALLS:
    area = callbook.area_of(call)
    home = callbook.home_of(call)
    if callbook._KEY_REFUSED:
        sys.exit("HamQTH refused the key (wrong, mistyped or revoked). Make a new one in HamQTH and try again.")
    print(f"{call:8}  area: {area['where'] if area else 'not found':32}  home: " + (f"grid {home['where']} ({home['lat']:.2f}, {home['lon']:.2f})" if home else "no profile (the area is used)"))
