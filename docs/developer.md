# Developer guide

## Help inside the app

The **Help** page in the app has one tab for each part: **Start here** (the README's text, so the two say the same, with the four pages one click away), then My spots, Compare antennas, Band conditions, Log analysis, Troubleshooting, **Run it yourself** and About and methodology. They are built from the guide files in `docs/`, with the long explanations folded closed. The sidebar has a link to the README and code on GitHub.

## Files

| File | Purpose |
| --- | --- |
| `web.py` | The Streamlit app's entry point: page setup and navigation |
| `views/` | One file per page: `spots_view.py` (My spots), `compare_view.py` (comparing antennas), `conditions_view.py` (Band conditions), `compare_page.py`, `inputs.py` (the sidebar choices and loading both spots pages share), `test_link.py` (a whole test in a link), `help_view.py` (Help, built from `docs/`) |
| `ui_common.py` | Settings, colours, constants and small helpers shared by the pages |
| `data_sources.py` | Getting spots: the RBN download and pasted rows, WSPR from wspr.live, the skimmer list |
| `live_rbn.py` | Today's RBN spots: from a live collector elsewhere (the address is `LIVE_RBN_URL` in the settings), or, when the app runs on your own computer, from a collector it starts inside itself |
| `collector/` | The live collector: `rbn_service.py` stays connected to RBN's live feed on an always-on machine and answers "the spots of this callsign today"; `setup_vm.sh` and `SETUP.md` put it on a free Google Cloud machine; `rbn_listen.py` is a one-off tool that counts the feed's rate |
| `simulate_validation.py` | Simulated tests with a known antenna difference, run through the program's own analysis, to check how often the summary is right, wrong and how often the 95% range holds the truth |
| `docs/*.md` | The guides: one for each page of the app, troubleshooting, this developer guide and the "About the method" page. The in-app Help is built from them |
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
