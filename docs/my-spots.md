# My spots

## Getting your spots

In the sidebar, choose **Spots from: RBN or WSPR**. For RBN, choose **Download a day** or **Paste spots**.

**RBN, Download a day.** Pick a day or a range (up to 7 days). Works for anything up to yesterday (UTC), because RBN publishes a day's file after that day ends. Only spots of your callsign are kept. On your own computer today works too, because the app collects it while it is open, and where a live collector has been set up (see [collector/SETUP.md](../collector/SETUP.md)) it works on the website: its spots come from RBN's live feed, and the page says if the collector began part way through the day or lost its connection, so you know what may be missing.

**RBN, Paste spots.** For spots from the last few minutes or hours, and for quick tests. Look up your callsign on [reversebeacon.net](https://www.reversebeacon.net/), copy the spot rows, paste them into the box, and click Load spots. The app reads each field by what it looks like, so odd spacing is fine.

**WSPR.** Pick a date (today works) and click Load spots. The app looks up WSPR spots sent by the callsign you entered, so use the callsign your WSPR transmitter sends. Reports take about 5 minutes to arrive in full; a newer cycle is still used and marked *may be incomplete*. Click Load spots again to refresh.

WSPR differs from RBN in a few ways: SNR is mostly negative (about -30 to +5 dB), the stations are called receivers, and *Show all skimmers* is off because there is no list of every WSPR receiver.

## The map

- Paths from you to every station that heard you, drawn as great circles and coloured by band.
- Dots sized and coloured by SNR. Click one for every spot from that station. The farthest station is circled.
- Band buttons above the map: **All** (every spot of the day) and one for each band that has spots, so a single click shows just that band. The sidebar filters are the **UTC time window** (one-minute steps) and **Minimum SNR** (RBN). They update the map instantly.
- A **Session report** tab for the whole day, across every band you loaded: when you were heard on each band, a band-by-hour grid (spots, farthest reach or median signal), a band scorecard, and how many stations heard you on each band by region (US East/Central/West, Canada, Europe, Asia and so on). It counts time you were *heard*, not time on the air, because a spot only exists when someone heard you.
- A **World view from your station** below the map: the same azimuthal map, coloured by average SNR or by how many stations heard you in each direction and distance cell.
- Stats above the map, a compass chart of your spots by direction below it, and a sortable spot table.
- **CW speed.** For RBN spots, a **Typical speed** tile (the speed the skimmers measured for your sending, with the range most spots fall in), the speed in each skimmer's popup, and a **Heard by speed** table in the Session report that groups your spots by speed (under 20, 20 to 24, 25 to 29, 30 or more wpm) with the spots, skimmers, bands and median signal of each. It is the skimmers' measurement, not what you set, and only CW spots have one (an RTTY spot's speed is in baud, and WSPR has none). A speed group used on only one band or at one time of day can't be compared fairly with another.
- Map style (light, dark, satellite, street), miles or kilometres, and **Download map** (a standalone HTML file).
- **Download report (PDF)** next to it: key numbers, the session report, direction chart and the stations that heard you.
- A **Log analysis** page in the menu: upload a contact log from your logging program and see it beside your RBN spots and the WSPR stations around you. See below.

Your location comes from the grid you typed, else (for WSPR) the grid square your own spots report, else the RBN skimmer list, else the FCC ([callook.info](https://callook.info)), else [HamDB](https://hamdb.org), else the centre of your country (the app warns you, because a country's centre can be hundreds of km from you). A WSPR station is always placed by the grid in its spots, 6 characters when there is one, so a station outside the US lands where it really is. Enter the grid square where you operate to place the pin somewhere else.
