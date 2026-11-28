# Run it yourself

## Run it locally

You need [Python 3.9+](https://www.python.org/downloads/). These steps install the main branch, the version that is live. The `beta` branch has newer changes that are still being tested.

When you run it yourself, days that have already ended are remembered in a folder (in your computer's temporary folder, or the folder named by the `RBN_CACHE_DIR` setting), up to about 400 MB, so loading the same day again does not download it again. Anything from the last hour is always fetched fresh.

**Windows (PowerShell).** Set it up once:

```bash
git clone https://github.com/K5OHY/FarField-Lab.git
cd FarField-Lab
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Then start it from the project folder:

```bash
.venv\Scripts\streamlit run web.py
```

Use exactly that command. Plain `streamlit run web.py` can fail with "not recognized" unless the virtual environment is activated, because the packages live inside `.venv`. If `python` is not found, try `py -m venv .venv`.

**macOS / Linux.**

```bash
git clone https://github.com/K5OHY/FarField-Lab.git
cd FarField-Lab
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run web.py
```

Next time, just run the last command again. Open http://localhost:8501 if the browser does not open, and stop the app with Ctrl+C (close the browser tab first if it hangs).

**Today's spots, built in.** While the app is open on your own computer it also listens to RBN's live feed by itself, so My spots can show today. The first time, the sidebar asks for your own callsign to log in with and remembers it (nothing connects until you give it; set `LIVE_RBN_CALL` to give it without being asked), and it only has the spots from when the app started: the page says when it began listening and where it lost its connection, and a restart the same day carries on. The spots are kept for 48 hours in a small file in your local app-data folder (not in the project folder). It is on by default; set `LIVE_RBN_LOCAL=0` to switch it off. To use a collector on another machine instead, set `LIVE_RBN_URL` (see [collector/SETUP.md](../collector/SETUP.md)).

The skimmer list refreshes itself every 24 hours, from RBN's node list and, for any skimmer RBN's page could not give (or when it cannot be read from the server), from [HamQTH.com](https://www.hamqth.com)'s copy of it (data provided by HamQTH.com); a skimmer that has since dropped off is kept. To force it: `.venv\Scripts\python rbn_to_csv.py` (macOS/Linux: `.venv/bin/python rbn_to_csv.py`).

## Update your copy

When the app has changed, update your copy from the project folder:

```bash
git pull
.venv\Scripts\python -m pip install -r requirements.txt
```

On macOS or Linux the second line is `.venv/bin/python -m pip install -r requirements.txt`. It only matters when the list of packages changed, and running it every time does no harm. Then **stop the app with Ctrl+C and start it again**. Refreshing the browser alone does not load changed code.

- **Which version you get.** If you cloned it with the steps above you are on `main`, the live version, and `git pull` brings you its latest. To try the newer `beta`, run `git checkout beta` and then `git pull`. To come back, run `git checkout main`.
- **Your settings are safe.** `settings.json` and `.streamlit/secrets.toml` are not kept in git, so updating never touches them.
- **If git says local changes would be overwritten** and names `cty.dat` or `spotter_coords.csv`: the app refreshes those two files itself (the country list and the skimmer list). Put the saved copies back with `git checkout -- cty.dat spotter_coords.csv`, run `git pull` again, and the app refreshes them again the next time it needs to.
- **Downloaded a ZIP instead of cloning?** Download the new ZIP into a new folder, copy your `.streamlit/secrets.toml` and `settings.json` across, and run the `pip install` line again from the new folder.

## Optional keys for your own copy

The app works without any key. Two free keys make the Log page a little better, and each one is only used for that:

| Key | What it adds | Without it |
|---|---|---|
| `HAMQTH_API_KEY` | Places a station outside North America at its callbook home instead of the middle of its call area. | It uses the call area, as it always did. |
| `NASA_API_KEY` | The "why" under a geomagnetic storm: which ejections NASA's DONKI links to it. | It uses NASA's shared demo key, which allows only about 10 requests an hour for everyone, so the "why" is often missing and the story says it could not be read. Kp, flux and flares still show. |

**HamQTH.** You need a free HamQTH account ([register here](https://www.hamqth.com/register)). Sign in, open your settings (Modify profile, then Account & privacy), choose **Apps and API keys**, and make a key. Give it a name such as "FarField Lab". It starts with `hqk_`. HamQTH's own description is on its [developers page](https://www.hamqth.com/developers.php). A key does not expire and can be revoked there at any time, and it has the same rights as your password, so treat it like one.

**NASA.** Fill in the "Generate API Key" form at [api.nasa.gov](https://api.nasa.gov). The key is shown at once and emailed to you.

**Where to put them.** Make a file called `secrets.toml` in the `.streamlit` folder of the project (create the folder if it is missing), with one line for each key you have:

```toml
HAMQTH_API_KEY = "paste your HamQTH key here"
NASA_API_KEY = "paste your NASA key here"
```

That file is listed in `.gitignore`, so git never uploads it. Do not put a key in the code, in a commit, in a screenshot or in a message to anyone. Instead of the file you can set an environment variable for one window, for example in PowerShell `$env:NASA_API_KEY = "..."`. Restart the app after adding a key.

To check that a key works without showing it, run `.venv\Scripts\python check_hamqth_key.py` or `.venv\Scripts\python check_nasa_key.py` (macOS/Linux: `.venv/bin/python ...`). Each prints only whether the key was accepted. If you host your own copy on Streamlit Community Cloud, paste the same lines into the app's **Settings, Secrets** box instead of a file.

## Live spots and collectors

RBN publishes a day's file only after the UTC day is over, so **My spots** gets today's spots from a *collector*: a small program that stays connected to RBN's live feed and answers one question, "the spots of this callsign today". There are three ways to have one, and all are free:

| | Where it runs | Who can use it |
|---|---|---|
| **Built into the app** | Your own computer, while the app is open | That copy of the app. Nothing to set up (see *Today's spots, built in* above). |
| **A Raspberry Pi or other Linux box at home** | A small computer you leave on | The app on your home network. About 10 minutes. |
| **Google Cloud, a free e2-micro machine** | Google's data centre, always on | **The website too.** About 20 minutes, once. This is what serves farfieldlab.streamlit.app. |

To point your own copy of the app at a collector elsewhere, set `LIVE_RBN_URL` (and `LIVE_RBN_KEY` if the collector has one) before you start it. Every step, with the commands, is in the [collector setup guide](../collector/SETUP.md).
