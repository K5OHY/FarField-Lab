# My spots

<!-- help:replaces-page-guide -->

## What this page answers

**Where was my signal decoded, and at what SNR?**

It maps the Reverse Beacon Network (RBN) skimmers and WSPR receivers that decoded your signal, and shows the SNR (signal-to-noise ratio, in dB) each one reported.

## Before you begin

- **Your callsign**, the one you sent with. For WSPR, use the callsign your WSPR transmitter sends.
- **A day with reports.** For RBN, you need to have been on CW, because a skimmer only reports signals it decodes. For WSPR, you need a WSPR transmitter of your own.
- **Optional: a grid square**, if you were portable or operating away from home.

Or skip all of this and click **Try an example**: it loads real RBN spots, so you can see a result first.

## Get your first result

1. Open **My spots**. To look first, click **Try an example**.
2. In the sidebar, under **Your signal**, type your **Callsign**.
3. Under **Spots from**, choose **RBN** (CW) or **WSPR** (a WSPR transmitter).
4. Pick the day. Dates are UTC. RBN publishes a day's file after the day ends; today works too, from a live feed, and the page says if part of the day is missing.
5. Click **Load spots**.
6. Look at the map, then use the **Band** buttons above it to look at one band.
7. **Click a station's dot.** A popup shows how far away it is and, for each band it decoded you on, a chart of your **SNR over time** with the number of spots, the median SNR and the range. If it decoded you on more than one band, pick the band with the tabs at the top of the popup.

If you were portable, type the place you operated from in **Grid square (optional)** before you load. Otherwise the pin goes where your callsign or your WSPR spots say your station is.

## Read the result

- **The map.** A line from you to every station that decoded you, coloured by band. Each station is a dot, coloured and sized by SNR. The farthest one is circled. Click a dot to see its SNR over time, band by band.
- **The two tabs.** **Map & direction** has the map, a compass chart of which directions you were decoded in, a world view from your station and a sortable spot table. **Session report** covers the whole day across every band: when you were decoded on each band, a band-by-hour grid, a scorecard, and how many stations decoded you in each region.
- **What to look for.** The farthest station and its band, which bands were decoded at all, and in the Session report, when each band opened and closed.

The Session report counts the time you were *decoded*, not the time you were on the air, because a spot only exists when a receiver decoded you.

## Look deeper

- **Filters in the sidebar:** **UTC time window**, **Minimum SNR (dB)** (RBN only) and **Band**. The map updates as you move them.
- **CW speed (RBN):** a **Typical speed** tile, the speed in each skimmer's popup, and a **Heard by speed** table in the Session report. It is the speed the skimmers measured for your sending, not what you set.
- **More settings:** **Map style** (light, dark, satellite, street), **Show all skimmers** (RBN only) and **Distance units** (miles or kilometres).
- **Spots to paste:** for spots from the last few minutes, and for quick tests, choose **Paste spots** under **How to get them** and paste the rows from reversebeacon.net.
- **A range of days:** choose **Date range** under **Period** (up to 7 days). The popup then has a tab for each day.
- **Take it away:** **Download map** (a standalone web page) and **Download report (PDF)**.
- **Share it:** once spots are loaded, the sidebar shows a link to exactly this view.

## What it cannot tell you

It shows where your signal was decoded, not everywhere it could be heard. Only stations running a skimmer or a WSPR receiver can decode you, so a quiet part of the map can mean nobody was listening there, not that the path was closed.

## Your data

The app asks RBN and WSPR sources for spots of your callsign, and looks up where stations are (from their grid squares, skimmer lists and public callsign lookups). Public lookup results may be cached.

## Common questions

- **"RBN has no spots of … for that date."** Check the callsign, try another day (dates are UTC), or, for today, choose **Paste spots** and copy your spots from reversebeacon.net.
- **"There are no WSPR spots from … in that time range."** Check that the callsign is exactly what your WSPR software sends, wait a few minutes if you have only just transmitted, or try a wider range of dates.
- **A WSPR day is marked "may be incomplete".** Reports take about 5 minutes to arrive in full. Click **Load spots** again to refresh.
- **The pin is in the wrong place.** Type the grid square where you operate in **Grid square (optional)**.
- **WSPR signal strengths look negative.** They are: WSPR SNR is mostly between about -30 and +5 dB, and its stations are called receivers.

## Reference: what every part of the page shows

<details>
<summary><b>What does every part of the My spots page show?</b></summary>

### Getting your spots

In the sidebar, under **Your signal**, type your **Callsign**, then choose **Spots from: RBN or WSPR**. For RBN, choose **How to get them: Download a day** or **Paste spots**.

**RBN, Download a day.** Under **Period**, choose **Single day** or **Date range**, and pick the date or dates (UTC). A range can be up to 7 days, and each day is a separate download. RBN publishes a day's file after that day ends, so any finished day works. Today works too when a live collector is running: on your own computer the app collects while it is open (so it only has the spots since it started), and the website uses a collector that runs all day (see [collector/SETUP.md](../collector/SETUP.md)). The page says if the collector began part way through the day or lost its connection, so you know what may be missing. Only spots of your callsign are kept.

**RBN, Paste spots.** For spots from the last few minutes or hours, and for quick tests. Look up your callsign on [reversebeacon.net](https://www.reversebeacon.net/), copy the spot rows, paste them into **Paste spot rows here**, and click **Load spots**. The app reads each field by what it looks like, so odd spacing is fine. If some of the rows are for your callsign it keeps just those; if none are, it uses every row you pasted. Pasted spots can't be put in a share link.

**WSPR.** Pick a date or a range (today works) and click **Load spots**. The app looks up the WSPR spots sent by the callsign you entered, so use the callsign your WSPR transmitter sends. Reports take about 5 minutes to arrive in full, so the page tells you when it loaded and the time of the newest transmission in it; click **Load spots** again to refresh. If a range holds more spots than the page can fetch, it says so and the oldest are missing: pick fewer days.

WSPR differs from RBN in a few ways: SNR is mostly negative (about -30 to +5 dB), the stations are called receivers, there is no **Minimum SNR** filter, **Show all skimmers** is off because there is no list of every WSPR receiver, and the **UTC time window** covers just the span of the spots you loaded.

**Try an example** loads K5OHY's real RBN spots from 23 October 2025. A banner on an example offers **Use my own data instead**, and **Start over** clears everything: the callsign, grid, date and loaded spots.

### The map

- **The numbers above the map:** **Spots**, **Skimmers** (or **Receivers**), **Farthest**, **Best SNR**, **Average SNR** and, for RBN CW, **Typical speed** (the speed the skimmers measured for your sending, with the range most spots fall in). Under them a line says where you are and how that was found, and warns about any station with no known location (it is not on the map) or one shown at its base callsign's place.
- **Band buttons** above the map: **All** and one for each band that has spots, each with its spot count. They appear when more than one band is loaded. The map, the numbers and the charts under it follow the band you pick; the Session report always shows every band.
- **The map.** Paths from you to every station that decoded you, drawn as great circles and coloured by band. Dots are coloured and sized by SNR, and the farthest station is circled. **Click a station's dot** for a popup with its distance and, for each band it decoded you on, a chart of your SNR over time with the number of spots, the median SNR and the range. A station that decoded you on more than one band has a tab for each band, and a range of days has a tab for each day. For RBN the popup also shows the CW speed. Click the map before you use the mouse wheel to zoom.
- **Under the map:** **Download map** (a standalone HTML file), **Spots (CSV)** (the spots on the map, with the band, time and SNR filters applied, for a spreadsheet) and **Download report (PDF)**: the key numbers, the session report, the direction chart, the world view and the stations that decoded you, farthest first (up to 60).
- **Direction of your spots:** a compass chart of the directions you were decoded in, with a sentence that sums it up.
- **World view from your station:** an azimuthal map with you at the centre. With one band, **Colour the map by** average signal strength or by how many stations decoded you in each direction and distance cell; with several bands the dots are coloured by band. **Show the receivers** draws the dots, and **How much of the world** sets the view (it opens on **Fit to the data**).
- **Spot table:** every spot in the view, sortable, folded under the charts.
- **Filters in the sidebar:** **UTC time window** (one-minute steps) and, for RBN, **Minimum SNR (dB)**. They update the map and the Session report. Under **More settings**: **Map style** (light, dark, satellite, street), **Show all skimmers** (RBN only: a small grey dot for every skimmer, including ones that didn't decode you) and **Distance units** (miles or kilometres).
- **The Session report tab** covers every band you loaded, over the time window and SNR you set. It has a short summary, then: **When you were heard, band by band** (a bar for each stretch of time you were decoded, with a **Day** choice when you loaded several), **When each band worked** (a grid of band by hour that you can show as spots, farthest reach or median SNR), a **Band scorecard**, and **Where each band reached** (how many different skimmers or receivers decoded you on each band, by region: US East, Central and West, Canada, Europe, Asia and so on, with one station that runs several receivers counted once). **Countries heard** is folded under it. It counts the time you were *decoded*, not the time you were on the air, because a spot only exists when a receiver decoded you.
- **CW speed.** For RBN spots, a **Heard by speed** table in the Session report groups your spots by speed (under 20, 20 to 24, 25 to 29, 30 or more wpm) with the spots, skimmers, bands and median signal of each. It is the skimmers' measurement, not what you set, and only CW spots have one (an RTTY spot's speed is in baud, and WSPR has none). A speed group used on only one band or at one time of day can't be compared fairly with another.
- **Log analysis** is its own page in the menu: upload a contact log from your logging program and see it beside your RBN spots and the WSPR stations around you. It can open this page with the day and time window of an activation already set. See the Log analysis topic.

**Your pin is found from the first of these that works:**

1. The grid square you typed.
2. For WSPR, the grid in your own spots.
3. For a US callsign, the FCC ([callook.info](https://callook.info)), then [HamDB](https://hamdb.org).
4. [HamQTH](https://www.hamqth.com)'s callbook, for any callsign: its grid square, or else its call area (the page says that one is approximate).
5. The centre of your callsign's country, as a last resort. The page warns you, because that can be hundreds of km off.

Stations are placed from the RBN skimmer list (HamQTH's copy fills any gaps) and, for WSPR, from the grid in each receiver's own spots.

### Sharing a view

**Share what you are looking at.** Once spots are loaded, the sidebar shows a **Link to this view**, and your browser's address bar holds the same link. Send it to someone and they land on the same callsign, date and band, with the spots already loaded. A narrowed time window goes in the link too. The same link also brings your sidebar choices back if you refresh the page or your computer sleeps. Spots you pasted can't be put in a link. On the Compare page the link also carries the whole test: the antenna names, how you switched, the start and order, a pasted block schedule, any antenna cells you corrected by hand, and the averaging choices, so the person you send it to sees the same summary.

Free hosting can fall asleep: click the button to wake it. A local copy also remembers your settings in `settings.json`.

</details>
