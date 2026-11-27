# Troubleshooting

## Troubleshooting

| What you see | What to do |
| --- | --- |
| "RBN has no data file for ... yet" | RBN publishes a day's file after the UTC day ends. Pick an earlier date, or paste today's spots. |
| "RBN has no spots of ... for that date" | Check the callsign or try another day. |
| "Couldn't read any spot rows" | Copy the rows straight from the RBN spot table. The message quotes the first line it couldn't read. |
| "Couldn't find a location for ..." | Enter your grid square in the sidebar. |
| "No location for ..." under the stats | Those skimmers are in neither RBN's node list nor HamQTH's copy of it, so they are counted but not drawn. |
| Compare found only one frequency group | Your spots are on one frequency, or your two tests were less than 0.1 kHz apart. Use a different frequency for each antenna. |
| A few WSPR cycles show only one or two receivers while the rest show dozens | Usually a few receivers with a wrong clock reporting your signal in the slot where you skipped a transmission. The app leaves those slots out and lists them above the table. If you really transmitted in one (a weak band can do this), pick it under **Count these slots as transmissions**, or every antenna label after it is one step off. |
| "wspr.live seems to be missing most of the reports for ... of your transmissions" | wspr.live's own data has gaps, seen at the start of every hour in some 2024 dates. Spots from those transmissions are undercounted, which can favour the antenna that was on the air at other times. A recent test is not affected. |
| "Not enough data yet" / too close to call | Run more transmissions per antenna (see above). |
| Downloading is slow | A day of RBN data is a large file. Each day in a range is a separate download. Results are cached for an hour. |
