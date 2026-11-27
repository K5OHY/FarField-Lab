# Developer guide

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

### Optional keys for your own copy

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

## Help inside the app

The **Help and README** page in the app opens with the same four tasks as the home page, then has one tab for each part of this README (My spots, Compare antennas, Band conditions, Log analysis, Troubleshooting, Deep dive), with the long explanations folded closed. The sidebar has a link to the README and code on GitHub.

## Files

| File | Purpose |
| --- | --- |
| `web.py` | The Streamlit app's entry point: page setup and navigation |
| `views/` | One file per page: `spots_view.py` (My spots), `compare_view.py` (comparing antennas), `conditions_view.py` (Band conditions), `compare_page.py`, `inputs.py` (the sidebar choices and loading both spots pages share), `test_link.py` (a whole test in a link), `help_view.py` (Help and README) |
| `ui_common.py` | Settings, colours, constants and small helpers shared by the pages |
| `data_sources.py` | Getting spots: the RBN download and pasted rows, WSPR from wspr.live, the skimmer list |
| `live_rbn.py` | Today's RBN spots: from a live collector elsewhere (the address is `LIVE_RBN_URL` in the settings), or, when the app runs on your own computer, from a collector it starts inside itself |
| `collector/` | The live collector: `rbn_service.py` stays connected to RBN's live feed on an always-on machine and answers "the spots of this callsign today"; `setup_vm.sh` and `SETUP.md` put it on a free Google Cloud machine; `rbn_listen.py` is a one-off tool that counts the feed's rate |
| `simulate_validation.py` | Simulated tests with a known antenna difference, run through the program's own analysis, to check how often the summary is right, wrong and how often the 95% range holds the truth |
| `docs/METHODOLOGY.md` | The technical methodology: every rule and number behind a summary, how it was checked, and its limits |
| `disk_cache.py` | Remembers days that are over (the RBN file, WSPR spots and who was on the band), so each is fetched once and wspr.live's limit of 20 requests a minute is not used up on repeats |
| `maps.py` | The interactive map of who heard you |
| `charts.py` | The charts and tables for comparisons and the session report |
| `pdfs.py` | Builds the PDF reports from those charts and tables |
| `compare_stats.py` | The A/B maths and the plain-English summary |
| `report_pdf.py` | Lays out the PDF reports |
| `tests/` | Automated checks of the calculations and the pages. Run them with `python run_tests.py` (in parallel: about a minute and a half; `--quick` leaves out the slow Compare page tests, and `python run_tests.py openings core` runs only the tests whose name contains those words) or, one process at a time, `python -m unittest discover -s tests -v`; set `RBN_TEST_NETWORK=1` to include the ones that use the internet |
| `rbn_data.py` | Skimmer list, callsign location lookup, grid conversion |
| `wspr_data.py` | Fetches WSPR spots |
| `world_map.py` | Draws the world map centred on your station |
| `session_report.py` | Builds the session report: timeline, band-by-hour grid, scorecard and regions |
| `conditions.py` | Band conditions: nearby WSPR stations restated for your power and mode |
| `dashboard.py` | The HTML for the Band conditions dashboard: band tiles, sun strip, region grids and highlights |
| `log_check.py`, `log_check_html.py`, `views/log_view.py` | The Log analysis page:
| `space_weather.py` | Current space weather from NOAA and a short plain reading of it; Kp, flux and flares for a past session (GFZ Potsdam, NOAA, the NASA HEK) |
| `log_space.py`, `log_space_html.py` | The Log page's space weather card: the facts (sun, flares, Kp, logged activity, sentences) and its layout |
| `ionosphere.py` | MUF and foF2 near you from the nearest working ionosondes (GIRO data via KC2G) |
| `example_data.py`, `examples/`, `build_examples.py` | The examples open saved copies of the real data (spots, where the station is, and for WSPR who was on the band), so they appear at once; `build_examples.py` refreshes them from the internet |
| `world_land.npz`, `build_world_mask.py` | The land/ocean grid the map is drawn from, and the one-off script that built it |
| `spotter_coords.csv` | Cached skimmer locations (updated automatically) |
| `cty.dat` | Country prefixes from [country-files.com](https://www.country-files.com), for the approximate-location fallback |
| `rbn_to_csv.py` | Refreshes the skimmer list now |
| `Update_spotters.py` | Older helper, not needed |
| `requirements.txt` | Python packages |
| `settings.json` | Your saved settings (local, never committed) |

## Data sources and thanks

Thanks to **Dale, N3HXZ** ([n3hxz.net](https://www.n3hxz.net/)) for the long-test method (relative gain, linear-power averaging and long alternating blocks) behind the Linear average and Relative gain views, and for his testing and feedback.

Space weather comes from [NOAA's Space Weather Prediction Center](https://www.swpc.noaa.gov/). The MUF and foF2 come from ionosonde data collected by [GIRO](https://giro.uml.edu/) (University of Massachusetts Lowell) and republished by Andrew KC2G at [prop.kc2g.com](https://prop.kc2g.com/).

[Natural Earth](https://www.naturalearthdata.com/) (public domain world outlines for the map), [Reverse Beacon Network](https://www.reversebeacon.net/), [wspr.live](https://wspr.live/) and [WSPRnet](https://wsprnet.org/), [callook.info](https://callook.info), [HamDB](https://hamdb.org), [HamQTH.com](https://www.hamqth.com) (data provided by HamQTH.com: where stations outside North America are, by call area, or by home when a HamQTH API key is set as the secret `HAMQTH_API_KEY`), [country-files.com](https://www.country-files.com), Esri and OpenStreetMap map tiles. Built with [Streamlit](https://streamlit.io/), [Folium](https://python-visualization.github.io/folium/), [pandas](https://pandas.pydata.org/), [Matplotlib](https://matplotlib.org/) and [GeographicLib](https://geographiclib.sourceforge.io/).

## License

MIT License.
