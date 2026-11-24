# Technical methodology

This is the detailed companion to the [README](../README.md). The README explains how to use the program. This page says exactly what is calculated, which numbers decide a summary, how the program was checked, and what it does not establish. Everything here describes the code as it is, so a result can be reproduced and challenged.

**In one sentence:** the program compares two antennas by asking the *same receivers* about both, which cancels each receiver's own noise and path, and then it is careful about how sure it can be.

## 1. What data goes in

| Source | What is used |
| --- | --- |
| WSPR (wspr.live) | Each report: time, receiver, receiver position, SNR, transmit power (dBm), frequency. A receiver that decodes the same transmission twice is counted once, at its strongest decode. |
| Reverse Beacon Network | The day's public history file, filtered to your callsign. Skimmer positions come from a skimmer list. A skimmer at the same site with a "-1", "-2" suffix is a separate skimmer. |
| Pasted rows | Spots copied from reversebeacon.net, read the same way. |

- All times are UTC. A day that has ended is remembered on disk so it is fetched once (wspr.live allows 20 requests a minute for the whole site). Anything from the last hour is always fetched fresh.
- Spots less than about 5 minutes old are flagged as possibly incomplete, because wspr.live fills a time slot in over several minutes.
- A receiver's position comes from the spot itself (WSPR) or the skimmer list (RBN). A receiver with no position still counts for reach but cannot be placed on a map or in a direction.

**On the band.** Many WSPR receivers hop between bands, and are on a given band only in some time slots. If A's transmissions land in a receiver's on-band slots and B's do not, that receiver "only hears A" because of its schedule, not the antenna. So for a time-based WSPR test the program asks wspr.live which receivers decoded *anything* on that band in each slot, and keeps only receivers that were active in at least two of A's slots and at least two of B's. Two limits: decoding another station is evidence a receiver was on the band, but not decoding anything is not proof it was not, and if wspr.live's list is cut off at its row limit the program says so and does not use it to drop anyone. The program also warns when a slot has far fewer active receivers than usual (below a quarter of the median, on a band with a median of at least 100), which is a known gap in some old wspr.live data.

**Left out of the comparison**
- A transmission heard by 2 or fewer receivers, or by 10% or fewer of the usual number, when ordinary ones are heard by 16 or more is treated as a skipped cycle (usually a few receivers with a wrong clock, reporting your signal in the slot after). It is listed above the test's table with its receiver count, and you can count it as a real transmission, which gives it a row and an antenna. That matters on a weak band, where a real transmission can be heard by only two receivers.
- With **After every transmission**, an A or B transmission with no partner on the other antenna is left out of the comparison, though it still shows on the maps. (In long blocks nothing is paired.)

**Optional filters** (reports at or below -27 dB, which is WSPR's decoding edge; receivers closer than a distance you choose; receivers where more than a chosen share of reports sit at the floor; the page hints at the 20% setting when 3 or more receivers have averages 20 dB or more apart, either way) change the detailed averages on the Receiver by receiver and Linear average views. They change the main summary only while the switch *Use these settings for the summary and the other tabs too* is on, which it is by default for WSPR tests (the minimum-reports slider then decides which receivers the summary counts). With it off, the summary counts every receiver that heard both, so a result can be reproduced from the summary rules alone. The summary always states the other number as well.

## 2. How A and B are told apart and paired

- **By frequency (RBN):** spots are grouped by nearby frequencies, and you say which group was A and which was B.
- **After every transmission (WSPR):** transmissions are labelled A, B, A, B or A, B, B, A. A **round** is an A transmission and the B one next to it. Neighbouring transmissions share nearly the same propagation, so drift mostly cancels.
- **In long blocks (WSPR):** one antenna for a set time, then the other. Nothing is paired; each receiver's reports on A and on B are compared as a whole.
- **Equal time on the air:** if one side was on the air more than 15% longer, the longer side is thinned at random (with a fixed seed, so the answer is repeatable) to match.
- **Sequential tests:** when A and B ran one after the other (separate frequencies or time windows more than 10 minutes apart, mostly unpaired transmissions, or fewer than 4 blocks), the summary says changing conditions could explain a difference.

## 3. What is being estimated

For every receiver that heard both antennas, the program works out that receiver's **relative gain**, B minus A in dB. Three kinds of number come out:

1. **Strength.** At each receiver, the typical difference between the antennas. In the paired method that is the median of the A-minus-B differences over rounds. In the long-block method each antenna's reports are turned into power, averaged, and turned back:

   `G = 10 log10( mean(10^(B/10)) / mean(10^(A/10)) )`

   The headline strength number is the mean of these receiver values, each receiver counting once. The summary uses the paired method for a test that alternates transmissions and the long-block method (average power) for a test run in blocks, so for a long test the summary and the Receiver by receiver average gain are worked out the same way.
2. **Reach.** How many receivers heard each side, and how many heard only one.
3. **Direction and distance.** Receivers are grouped into eight 45-degree sectors and distance bands, and the average relative gain is worked out in each.

The two strength methods do not always use the same observations. The paired method uses receivers that decoded both antennas in a matched pair. The linear-power method can use every decoded transmission, including ones with no partner. When the two disagree, part of the reason can be the different set of observations and not only the different arithmetic.

**Every receiver callsign counts on its own, including several at one site.** That matches how the published method counts stations, but it has a consequence: a site with five receivers gets five votes, and receivers at one site share the same path and noise, so they are not fully independent. Where several receivers share a site, the stated range can be narrower than the real uncertainty. A "one vote per site" sensitivity check is on the list of future work.

## 4. How the uncertainty is worked out

| Quantity | Method |
| --- | --- |
| Strength range, paired tests | 95% bootstrap range of the receiver average (4,000 resamples of the receivers), then widened for fading at the transmitting end (below) |
| Strength range, unpaired tests, fewer than 40 receivers | Student's t interval, because a bootstrap on a few receivers comes out too narrow |
| Per-receiver gain with at least 3 reports on each antenna | Welch's unequal-variance interval on the two means |
| A direction or distance band | 99% bootstrap range (about 14 bands are checked at once), counted only with at least 4 receivers and a difference of more than 2 dB |

**Fading at the transmitting end.** Fading moves every receiver at once, so counting receivers as independent flags differences that are only fading. For paired tests, the range is widened: with 4 or more rounds, by the measured round-to-round spread of the averages, and with fewer rounds by 0.85 dB per pair (the spread of identical-antenna pairs measured on real WSPR data, 0.84 dB over 43 pairs). The final range is the wider of the receiver-based range and this one. That is a practical correction, not a full hierarchical resampling of receivers and rounds, and the program does not claim it is one.

## 5. How a summary is decided

**Strength** (with `N` receivers that heard both, `lo` and `hi` the range, `mean` the average):
- Fewer than 5 receivers: not enough to judge.
- Range excludes zero and the average is 1 dB or more: that side is stronger.
- Range excludes zero but the average is under 1 dB, or the whole range sits inside plus or minus 1 dB: "no meaningful difference". When the range excludes zero, the page names a small lead and says it is too little to matter.
- Otherwise: inconclusive, with the range written out in plain words ("anywhere from A ahead by x dB to B ahead by y dB").

The 1 dB line is a practical convention chosen for this program, not a statistical property of antennas. A lead under 1 dB can matter to a contest operator and not to a portable one. And a range that extends past 1 dB does not prove the antennas are equal, which is why the wording describes the lead and not equivalence.

**Reach**
- Unpaired: an exact sign test on receivers that heard only A against only B, needing at least 4 one-sided receivers.
- Paired: an exact sign (McNemar) test over rounds where one side was heard by more receivers, needing at least 6 such rounds. A paired test judges reach by round, because counting receivers as independent would turn fading into a false winner.
- When the split favours one side but does not reach the significance level, the page may say reach "leans" that way. That is when a split at least that lopsided would happen by chance no more than about 40% of the time if the two reached equally. It is descriptive, not a probability that that antenna truly reaches more.

**Farthest receiver.** A side is called farther only when its farthest receiver is at least 25% and 1,000 km farther and, for a paired test, there are at least 6 paired rounds. That is a rule of thumb, not a significance test. A single far receiver can be luck, so a short test with very different distances says it is too short to tell. Beside it the page shows a plain count of receivers beyond 5,000 miles for each side.

## 6. How it was checked, and what that does not show

**Against Dale's study (N3HXZ, long blocks).** With his transmitter, date and schedule, the program's relative gain matches his table on the 27 stations of the first version of his table: 0.00 dB difference on average and 0.12 dB at most at any station. The 500 to 1,500 mile average was 3.87 dB against 3.86 dB. The program also counted four more stations that met his 40-spot rule, and his updated paper includes them. This shows the linear-power calculation is implemented correctly. It does **not** show that the confidence ranges are right, that the short paired method works, or that a real antenna difference is recovered under changing conditions. The automated check is `tests/test_dale_study.py` (it needs the internet, so it only runs when `RBN_TEST_NETWORK=1` is set).

**Same antenna as A and B ("null" tests).** Two checks, both on real WSPR data where the true difference is zero.

*A day of WW0WWV on 20m*, cut into 47 overlapping one-hour windows (roughly 25 independent cases), with the same transmitter treated as A and as B each time. How often the program named a winner:

| Test shape | False winner |
| --- | --- |
| 2 blocks of 30 min | 5 of 45 (11%) |
| 4 blocks of 15 min | 2 of 47 (4%) |
| 6 blocks of 10 min | 2 of 46 (4%) |
| 12 blocks of 5 min | 2 of 47 (4%) |
| 30 transmissions, A, B, A, B | 2 of 47 (4%) |
| 30 transmissions, A, B, B, A | 0 of 47 |

At a nominal 5% level, a well-calibrated test should wrongly reject "the antennas are equal" in about 5% of independent trials, and the program's extra rule (a lead must be 1 dB or more) can push its false-winner rate lower still. So these counts are a preliminary check, not a measurement of how often the 95% range holds the truth, and the overlapping windows are not independent trials. With that said, most shapes are near the expected rate, two blocks is the weak spot, and A, B, B, A did best. Typical gaps between identical antennas were 0.2 to 0.7 dB, but some windows showed 2 to 5 dB when the band was moving.

*Dale's single-antenna run (N3HXZ, 40m, 25 October 2026, 30 two-minute transmissions).* Both A, B, A, B and A, B, B, A gave "too close to call", with the average gap about 0.6 dB (range -0.1 to +1.3 dB), and the receiver-by-receiver averages stayed within about 1 dB as the minimum reports rose. A 6-block test of 10 minutes gave a false "B stronger by 2.4 dB" on the same data, because the band changed between blocks and every receiver moved together.

What these suggest: the paired method gives fewer false winners than a test with only a few long blocks. They do not show that the intervals are calibrated, and the simulation below shows they sometimes are not. What they do not show: one station, one band and one day each, with overlapping windows, so they are a good indication, not a calibration. A proper coverage study would repeat this over many days, bands and stations.

**Simulated tests with a known difference.** `simulate_validation.py` makes up antenna tests in which B is truly 0, 1, 3 or 6 dB stronger than A, runs them through the program's own analysis, and counts the summaries. The made-up tests have 80 receivers, fading shared by every receiver in each transmission (0.6 dB), noise on every report (3 dB), a steady band drift (2 dB an hour), receivers that listen only 85% of the time, and reports below -28 dB lost. 300 tests per row:

| True gain of B | Transmissions | Says B stronger | Says A stronger (wrong way) | 95% range holds the truth |
| --- | --- | --- | --- | --- |
| 0 dB | 6 | 6% | 5 to 8% | 84 to 87% |
| 0 dB | 12 | 0 to 2% | 0 to 1% | 92 to 95% |
| 0 dB | 30 | 0% | 0% | 86 to 88% |
| 1 dB | 6 to 30 | 35 to 46% | 0% | 86 to 95% |
| 3 dB | 6 to 30 | 100% | 0% | 85 to 94% |
| 6 dB | 6 to 30 | 100% | 0% | 81 to 93% |

Each range covers A, B, A, B and A, B, B, A. What it shows: with identical antennas there are almost no false winners from 12 transmissions up (0 to 3%), but with only 6 transmissions about 11 to 14% of tests name a winner; real differences of 3 dB or 6 dB were found every time and never called the wrong way; a real 1 dB difference is found about 40% of the time, because of the 1 dB rule; and the 95% range holds the truth about 81 to 95% of the time, usually around 90%, so it is a little narrow. What it does not show: the results depend on the noise and drift this makes up, so it tests the program's logic and not real HF propagation, and it does not cover receivers sharing a site.

**Why the range runs a little narrow.** The table above has the 95% range holding the truth 81 to 95% of the time, usually about 90%. To see why, `python simulate_validation.py 250 ablation` starts from complete data and adds one problem at a time (a true gain of 3 dB, 250 tests per cell):

| | 12 tx A,B,A,B | 12 tx A,B,B,A | 30 tx A,B,A,B | 30 tx A,B,B,A |
| --- | --- | --- | --- | --- |
| Complete data (nothing missing, no drift) | 93% | 91% | 92% | 91% |
| + reports below -28 dB lost | 93% | 95% | 87% | 86% |
| + receivers listen 85% of slots | 93% | 95% | 88% | 91% |
| + steady band drift (2 dB an hour) | 94% | 93% | 89% | 93% |
| + no shared fading | 92% | 96% | 95% | 94% |
| Everything on (the main table) | 94% | 94% | 82% | 91% |

With 250 tests a cell, a figure is uncertain by about 2 points either way. Two things stand out. Even with complete data the range holds the truth about 91 to 93% of the time, not 95%, so the interval itself is slightly narrow. And losing the weak reports costs the longer tests about 5 points: a receiver that can only just decode the weaker antenna is kept only when that antenna's reports happen to be strong enough, which shrinks the measured gap, so the range is centred a little short of the truth. That second effect is a selection effect (the comparison is among receivers that decoded both), not an error in the arithmetic. It is a reason to treat the range as slightly optimistic.

The "chance this lead is real" figures in the summary text (for example "a lead this big would still show up about 30% of the time if they were equal") are approximate. They come from the width of the final range, as if it were a t interval, so they are as rough as the range itself.

**Band conditions against RBN.** See the README section "Band conditions now". In short, predicted signal margins were compared with what skimmers actually reported for four stations' activations, and the typical error was about 7 dB (6 dB within 1,000 miles, 9 dB at 1,000 to 2,000 miles, no DX paths in the sample).

## 7. The band conditions model

For each WSPR report near you, the program restates the SNR for your power and mode:

`estimated SNR = reported SNR + 10 log10( your power / the reporting station's power ) + your antenna adjustment`

and works out the **margin** over the mode's threshold (2,500 Hz reference bandwidth): CW -5 dB, SSB +8 dB, FT8 -21 dB, WSPR -28 dB.

- **The percentage** is `Φ(margin / 8 dB)`, where Φ is the standard normal curve and 8 dB is the spread of prediction errors. The 8 dB is a rounded engineering figure, informed by the RBN comparison above (7.4 dB overall), not a fitted statistic. A margin of zero is a coin flip and +8 dB is about 84%.
- **It is not the chance of an RBN spot.** Skimmers report less often than this estimate suggests, which the README quantifies. Treat the percentages as "decodable under the model".
- **Regional percentages** are averages over the receivers actually seen in each band and region. They describe those receivers, not every receiver in the region.
- **"Power needed"** uses the 75th-percentile margin among a region's receivers, so it describes the power to reach a fairly favourable receiver, not a typical one.
- **Cells with fewer than 3 receivers** show only a count, because the receivers that reported anything are the lucky exceptions and a figure from one or two would look far too easy.
- **Band tiles:** "Open" needs at least 3 receivers rated good, and "Marginal" at least 2 rated good or marginal, counting only receivers beyond a minimum distance for that band (below). If receivers rate good or marginal but all of them are closer, the tile says "Local only", and otherwise "Quiet". The tile also shows how far away its best receiver was. These words describe the evidence in the WSPR sample, not an absolute state of the ionosphere.
- **Minimum distance for a band to count as open** (rules of thumb, not measurements). A receiver nearby on the upper bands usually hears you by ground wave or local scatter, not the ionosphere, so it says nothing about the band being open: 160m to 40m none (local use by steep skywave is real), 30m 100 miles, 20m 250 miles, 17m and 15m 400 miles, 12m, 10m and 6m 500 miles.
- **Space weather and MUF.** The sun readings come from NOAA and are described as tendencies, not forecasts for a band. The MUF comes from ionosonde data (GIRO, republished by KC2G) and is an estimate from the nearest working sounders, not a measurement along your path.

### The log analysis

The Log analysis page sets a contact log (ADIF) beside RBN spots and the band conditions model. Its rate counts only the gaps between contacts of 30 minutes or less, so an overnight break is not read as slow operating. For each stretch on a band (a pause of 30 minutes starts a new one) it builds the WSPR picture from the hour before the middle of the stretch, as the Band conditions page does at your power, and uses the CW contacts only. The strength figure matches each WSPR receiver that is also a skimmer that spotted you, takes the median skimmer report minus the receiver's figure restated to your power, and subtracts a typical offset of 10 dB (an ordinary 100 W station read about +10 dB on RBN against the page's figure in two checks of known-power stations, a vertical at 100 W and the NCDXF beacons). It is shown with 3 or more matches and striped below 8. The page no longer sets the Band conditions page's percentage against the share of skimmers that spotted you: that gap mixed three things (WSPR receivers, skimmers on the band and who was tuned to you) and said little about any of them. The openings grid below replaces it. This is a hint, not a calibration: the offset comes from few checks, skimmers and WSPR receivers differ, and one afternoon is a small sample.

The band conditions picture on the same page uses only WSPR. The log is cut into stretches of activity at pauses of 4 hours or more, and each stretch into half hours. For each half hour and band it runs the conditions model on the hour of WSPR spots up to the end of that half hour, from the transmitters within the chosen radius (300, 400 or 500 km, 500 by default) of the place in the log, at the power entered and in the mode most contacts were made in (CW, SSB or FT8, CW if it is something else). The page has two views of the same evidence. The default, *band by band*, draws a card for each band you worked (highest first) on a UTC time axis, with a lane for each distant continent and a bar for each time bin in which receivers there decoded WSPR transmitters near you (or, in the estimate view, looked strong enough). A bar is solid for two or more receiving stations and pale for one: a count of stations is evidence quality, not signal strength, and the page never calls a single station a weak signal. A bin with too little WSPR (see the rules above) gets no bar and a mark of its own. Your contacts are ticks, and a dot where the contact is with a distant continent; logged activity on a band is shaded from its first to its last contact, split at pauses of more than 15 minutes, and is described as logged activity because a log holds contacts and nothing about the time between them. A ring marks a skimmer in the continent that spotted you, drawn only where RBN applies. Each card carries one finding built from counts, in cautious words, checked against the same list of unsupported phrases. The *grid* view, described next, is the earlier view of the same evidence for one destination.

The grid view is read for one destination, a compass sector or a continent, at or beyond a minimum distance (3,000 miles by default; 1,000 km or any distance can be chosen), and has two views. *What WSPR showed* counts, for each band and time bin, the different receivers in the destination that decoded those transmitters, and assumes nothing about the station. *Estimate for my station* counts those that come out as good (the restated signal at least 3 dB above what the mode needs), so its wording is an estimate throughout (looked strong enough, never would hear); a striped box has receivers there that decoded WSPR but none good, a dashed box has too little WSPR behind it to say (see the rules above), and a blank box has no reports from there. Each box is also one of five statements, from three facts that are never combined into a score: whether WSPR showed a path to the destination, whether you were active on the band in that box (any contact on it), and whether you logged a contact with the destination. A path and a contact with it; a path and activity but no contact with it; a path and no contact on the band; a contact but no path in the WSPR; no path and no contact. Where WSPR has too little behind it the box makes no statement about a path, and says so. RBN is a fourth, separate fact. It is counted only for CW and RTTY (FT8 is on PSK Reporter, which the page does not use) and only for a box in which you were calling CQ: known from your own spots' kind in that box (CQ or CQ DX), or because the log is a POTA or SOTA activation, which is run by calling. Where it does not apply the box says RBN is not applicable or unknown, and where the spots could not be read, unavailable. A ring means a skimmer in the destination spotted you; its absence says little, because RBN has far fewer skimmers than WSPR has receivers. The summary lines under the grid are built from the counts of these statements alone, in cautious words (you were active, WSPR showed a path), and are checked against a list of phrases that would claim more than the data shows (a missed chance, a failed attempt, a score, when anyone was listening); a test enforces it. The page has no utilisation score and infers neither listening time nor attempts. A contact counts toward a direction when its own grid square is in the log or when its state lies wholly in one sector as seen from the place (the state's bounding box, to about half a degree, must fall in one sector); a contact placed only at the centre of a country, or in a state that spreads over several sectors, is between directions and counts only in the continent view. Choosing a box on the page shows its evidence: the window bounds, the coverage, the transmitters with their distances, the receivers in the destination with the times they decoded, your RBN spots from skimmers in the destination, and your contacts in the box. The bands looked at are the ones in the log plus 160m to 6m, and a band that was not worked is shown after the worked ones when WSPR has any receiver on it. A US callsign this far away is counted as a US station overseas, not as a US region. A diamond marks a box in which you were active on the band, a star a contact with the destination, and a ring a skimmer in the destination that spotted you (a skimmer's place comes from the skimmer list; one it does not know is not counted). The lines under the picture state those counts band by band; they give no advice, because a log cannot say why a band was chosen. The count is of receivers, so a few steady paths do not look like many reports, but a band with few WSPR transmitters near the place has thin evidence, and bands cannot be fairly ranked by their counts, because they differ in how many receivers they have. A line above the picture counts what it rests on: the WSPR reports, the transmitters near the place, the receivers that decoded them and the farthest one. The space-weather strip uses Kp and solar flux from GFZ Potsdam's archive and NOAA's list of X-ray events (kept for about a month); the lines say the highest Kp that touched the session (below 3 is quiet, 5 or more a storm), the daily solar flux on the days of the session, and the strongest flare between the first and last contact, and never claim an effect on a particular path. The who-hears-whom table takes the S digit of the report both ways (one S-unit counted as 6 dB), needs 10 contacts per band and leaves a band unread when 90% of its reports are S9 both ways. The what-you-worked tiles and table count from the log alone. An entity is the DXCC number the log gives (else the country the log names, else the one the callsign belongs to in cty.dat, the country list the page already has); the continent is the log's, else the country's. A US state is counted only when the contact is with the United States, Alaska or Hawaii and its STATE is one of the 50, and a Canadian province only when the contact is with Canada, so a foreign station's own region code (Brazil's PA, for example) is not a state. Zones are the log's CQZ and ITUZ and are left out when it has none. Band-countries count each entity once per band. The totals (340 entities, 50 states, 13 provinces and territories, 40 CQ zones, 6 continents) are the sizes of the lists, and nothing here says an entity is confirmed. The headline over the park card takes the log's best day (the highest rank by QSOs, the latest when tied) and says whether it is the most of any listed activation, among the top few percent, or your biggest there, with the standing among the park's activators; a day POTA does not list yet is ranked by the log's own count and says so. The share picture and text use only the log's numbers and that headline. A summit is read the same way from SOTA's public record of the summit and its list of activations (callsign, UTC date and QSOs; SOTA lists no modes, so only the total QSOs are ranked, and a day not listed under the callsign is ranked by the log's own count and says so). A reference is read as the program's own format, a letter O typed for a zero in a summit number is read as a zero, and the contacts' SOTA_REF values count the summit-to-summit contacts and the different summits. A station whose grid square is in the log is placed at the centre of its 4 character square from that, with no lookup. The park card reads POTA's public record of the park and its activation list (one entry per callsign and UTC day, with the total, CW, phone and data QSOs the activator uploaded). Each UTC day of the log is matched to the entry under the same callsign (a /P or /M suffix is ignored) and ranked against the other entries, the most QSOs first; a tie shares a rank. A day with no entry is ranked by the log's own counts and says so. The standing among the park's activators adds up what is listed under the same callsign (QSOs, activations, CW QSOs) and ranks it against every other callsign; only listed days count. The park's totals (contacts, and how many activations reached the 10 QSOs POTA needs) come from POTA's statistics for the park. The counts are what activators uploaded, so they can differ from the log (POTA removes duplicates) and from the programs' own records. The earlier picture, the share of the receivers heard that come out as good (a box with fewer than 20 receivers is too thin to say), is kept under "Another view: the percent of stations that could have heard you"; its lines only compare a band with itself: a stretch is steady when a band stays within 10 points of itself, and rising or falling when its first two boxes and last two differ by 15 points or more.

*The rules every part of the page shares* (`log_foundations.py`):

- **Time bins.** Contacts, RBN spots and WSPR are sorted into the same clock-aligned bins, 30 minutes by default (15 is supported). A bin holds its start and everything up to, but not including, its end. A box is judged on the hour of WSPR up to the end of its bin, so with 30-minute bins each box shares 30 of its 60 minutes with the box before (45 with 15-minute bins); the exact window and the shared minutes are stated for every box, so the same reports are not mistaken for independent evidence.
- **Nearby.** A WSPR transmitter is near when it is within the chosen radius (300, 400 or 500 km) of the place. The transmitters' positions are the grid squares in their own spots.
- **Regions.** Eight 45 degree compass sectors seen from the place (North is 337.5 degrees up to, not including, 22.5), or the continent. A contact is placed by its own grid square from the log (the 6 character grid when it has 6), read for each contact, so a station that moved is placed where it was each time. Failing that it is placed at the centre of its state (North America) and then of its country by its callsign; those are flagged approximate and are left out of the sector counts, because a centre can be hundreds of km from the station and could put the contact in the wrong sector. The continent comes from the log's CONT field, else from the callsign, and counts for every contact.
- **SNR bandwidth.** WSPR reports its SNR in 2,500 Hz, and the Band conditions page states its mode thresholds in 2,500 Hz. RBN's operator describes a spot's SNR as signal against noise scaled to 500 Hz (N4ZR, 2014), which is about 7 dB higher than the same signal against 2,500 Hz. That is kept as an assumption, because it depends on each skimmer's software, antenna and noise and no spot says which. The conversion is available but is not applied to the existing strength comparison: the typical offset of 10 dB found from two known-power stations already contains this difference, and applying both would count it twice. The comparison will separate the two.
- **Coverage.** For each box and band: the reports, the different transmitters, the different receivers, and the different receiving sites (positions to about 1 km) in its window. A box with fewer than 3 transmitters or 20 receivers is *sparse*, and says nothing.
- **What a box can be.** In this order: *not applicable* (RBN carries CW and RTTY only, and only speaks for a session in which you were calling CQ), *unavailable* (the data could not be fetched), *no reports*, *insufficient coverage*, *below threshold* (enough stations reported but none looked strong enough), otherwise *evidence*. An empty box is never drawn as if it were one of the others.

The contacts can also be placed on the map. As soon as a log is loaded the stations of every band are looked up in the background, busiest band first, and an answer is remembered (exact answers on disk, misses and guesses in memory for an hour), so a band's map is usually ready when it is picked. Each call is looked up at the FCC and HamDB (the same lookup the app uses for your own callsign), an exact answer is shown at the centre of its 4 character grid square so that another person's address is never drawn, and a call the lookups could only place at the centre of its country is placed at the centre of the state in the log instead. A contact is shown where its station is registered, which is not always where it operated. The report columns use the S digit of an RST report (579 gives 7), ignore digital dB reports, and are shown as an average only; they are not compared with skimmer SNR, because reports are subjective and often sent out of habit.

## 8. Known limitations

- Receivers at one site count separately and can make the stated range too narrow.
- The intervals have been checked against same-antenna data and against simulated tests, not calibrated over many independent real experiments.
- Tests with very few blocks (especially 2) are the weakest, because the band can change between turns.
- WSPR only reports what a receiver decoded, so a weaker antenna is decoded less often and a decoded-only comparison can look slightly better than the antenna is.
- Whether a receiver was on the band is inferred from it decoding other stations.
- The 1 dB threshold, the 25% and 1,000 km farthest-reach rule, and the 8 dB band-conditions spread are conventions, chosen and explained, not measured constants.

## 9. The numbers in one place

| Setting | Value |
| --- | --- |
| Significance level for "a real difference" | 0.05 |
| Practically equal | within plus or minus 1 dB |
| Minimum receivers that heard both, to judge strength | 5 |
| Bootstrap resamples (main range) | 4,000 |
| Direction or distance band: minimum receivers, minimum difference, range level | 4, 2 dB, 99% |
| Pair-to-pair fading spread used for few rounds | 0.85 dB |
| Decisive rounds needed to call reach (paired) | 6 |
| One-sided receivers needed to call reach (unpaired) | 4 |
| Reach described as "leaning" | a split that lopsided would happen by chance no more than about 40% of the time if the two reached equally |
| Farthest-reach call | at least 25% and 1,000 km farther |
| "Far" receiver count | beyond 5,000 miles |
| Equal-time tolerance | 15% |
| Weak-report floor (optional filter) | -27 dB |
| Band conditions prediction spread | 8 dB |
| Region needs this many receivers for a percentage | 3 |
| Minimum distance for a receiver to count toward Open or Marginal | none on 160m to 40m; 100 mi on 30m; 250 mi on 20m; 400 mi on 17m and 15m; 500 mi on 12m, 10m and 6m |

Questions and corrections are welcome. This page and the code in `compare_stats.py` and `conditions.py` should always agree, and if they do not, the code is the truth and the page is a bug.
