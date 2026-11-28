![FarField Lab](images/branding/farfield-banner.png)

# FarField Lab

**Explore propagation. Compare antennas.**

FarField Lab helps you explore how your station gets out. Map the receivers that reported you, compare two antenna setups, check recent propagation near your location, or explore an operating session from your log, such as a POTA or SOTA activation.

It uses reception reports from the [Reverse Beacon Network](https://www.reversebeacon.net/) (RBN) and [WSPR](https://wsprnet.org/), alongside your uploaded log when you provide one.

**[Open FarField Lab](https://farfieldlab.streamlit.app/)**. Nothing to install. (It was called RBN Signal Mapper before; the old addresses still work.)

| | |
|---|---|
| **[My spots](https://farfieldlab.streamlit.app/spots)**<br>[![My spots](images/ui/thumb_spots.jpg)](https://farfieldlab.streamlit.app/spots) | **[Compare antennas](https://farfieldlab.streamlit.app/compare)**<br>[![Compare antennas](images/ui/thumb_compare.jpg)](https://farfieldlab.streamlit.app/compare) |
| **[Band conditions](https://farfieldlab.streamlit.app/conditions)**<br>[![Band conditions](images/ui/thumb_conditions.jpg)](https://farfieldlab.streamlit.app/conditions) | **[Log analysis](https://farfieldlab.streamlit.app/log)**<br>[![Log analysis](images/ui/thumb_log.jpg)](https://farfieldlab.streamlit.app/log) |

## New here? Start with an example

You can explore these without uploading a file or owning any equipment.

- **[My spots](https://farfieldlab.streamlit.app/spots):** open it and click **Try an example** to explore a real reception map.
- **[Compare antennas](https://farfieldlab.streamlit.app/compare):** open it and choose one of the real antenna tests.
- **[Band conditions](https://farfieldlab.streamlit.app/conditions):** there is nothing to load. Enter your callsign or the grid square you are operating from, and see which bands look open near you right now.
- **[Log analysis](https://farfieldlab.streamlit.app/log):** open it and choose an example log, such as a POTA or SOTA activation. In *My biggest at Bush House*, find the station that worked all five bands, then explore where RBN reported the activation.

## Or use your own data

| Your goal | Open | What you need | Start by looking at |
|---|---|---|---|
| See where your signal was decoded | **[My spots](https://farfieldlab.streamlit.app/spots)** ([guide](docs/my-spots.md)) | Your callsign and a day with RBN or WSPR reports | The map, then the band buttons above it |
| Compare two antennas, frequencies or power levels | **[Compare antennas](https://farfieldlab.streamlit.app/compare)** ([guide](docs/compare-antennas.md)) | Reports from a test where you switched between them, and how you switched | The coloured *Summary* card |
| See which bands look open near you now | **[Band conditions](https://farfieldlab.streamlit.app/conditions)** ([guide](docs/band-conditions.md)) | A callsign or grid square, your power and your mode | The band tiles |
| Make sense of an operating session, such as a POTA or SOTA activation | **[Log analysis](https://farfieldlab.streamlit.app/log)** ([guide](docs/log-analysis.md)) | An ADIF file (.adi or .adif) exported from your logging program, and the power you used | The row of findings under the numbers |

**Comparing antennas?** Check which antenna is A and which is B, and how you switched, before you read the result.

**Do I need a WSPR transmitter?** Not for **Band conditions** or **Log analysis**: they use transmissions from other WSPR stations near your operating location. **My spots** and **Compare antennas** need your own signal to have been reported, either on RBN or from a WSPR transmitter of your own.

## Understand the data sources

| Source | What it tells you | Used by |
|---|---|---|
| **Your log** | Who you worked, on which band, and when. | Log analysis |
| **RBN reports of you** | Which automated receivers (skimmers) decoded your CW signal. | My spots, Compare antennas (a quick CW check), Log analysis (your CW contacts) |
| **WSPR reports of your own transmitter** | Which WSPR receivers decoded your WSPR transmissions, and how strongly. | My spots, Compare antennas (the recommended test) |
| **Nearby WSPR** | Which paths were reported from near your location, by other people's transmissions. It describes the path, not you. | Band conditions, Log analysis |

A logged contact confirms communication between those two stations at that time. An RBN or WSPR report of you confirms that a particular receiver decoded your signal. Nearby WSPR adds evidence from other transmitters around your location. Missing reports can reflect gaps in monitoring coverage, so a band with no reports is not necessarily a closed band.

## Help and more detail

- **Help** is in the app's menu, and every page has a *What this page does and how to use it* box.
- **Something looks wrong?** [Troubleshooting](docs/troubleshooting.md)
- **How it is calculated,** including the check against a published study: [Methodology](docs/METHODOLOGY.md)
- **Install it, update your copy, add the optional keys or run a collector:** [Run it yourself](docs/run-it-yourself.md)
- **What each file is for, and where the data comes from:** [Developer guide](docs/developer.md)

## Your data

Your uploaded log is processed for your session and is not saved as a log file by FarField Lab. The app queries external services to retrieve reception reports and to locate stations, using your callsign and, where needed, the callsigns from your contacts. Public lookup results may be cached.

## Credits

The long-test method behind the Compare page follows the work of **Dale, N3HXZ** ([n3hxz.net](https://www.n3hxz.net/)). The full list of data sources and thanks is in the [Developer guide](docs/developer.md#data-sources-and-thanks). MIT License. Made by K5OHY.
