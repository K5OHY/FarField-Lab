# About the method

## Deep dive (for the curious)

This is where the working is.

- **[Technical methodology](METHODOLOGY.md).** Every rule and number, how the program was checked (including tests where A and B are the same antenna), and what it does not establish.
- **[How the comparison works](compare-antennas.md#compare-two-antennas) and the math, step by step.** Folded away in the Compare antennas section, under *How does the comparison work, step by step?*
- **[Checked against a published study](#checked-against-a-published-study).** How the results compare with published work.
- **[Dale, N3HXZ](https://www.n3hxz.net/).** The long-test method this app's second mode follows.
- **[Files](developer.md#files) and [Data sources and thanks](developer.md#data-sources-and-thanks).** What each file is for, and where the data comes from.

## Checked against a published study

Dale, N3HXZ, published a long WSPR test of two vertical antennas, "Comparing Performance between an Elevated and a Ground mounted Vertical Antenna" (31 August 2026): a Performer (tuned elevated quarter-wave vertical, two raised radials) against an untuned 17 ft whip on a 5:1 matching unit, ground-mounted with two radials, on 20m at 1 W, switched in 30 minute blocks from 12:00 to 21:30 UTC on 26 August 2026, using the stations with 40 or more spots on each antenna. His table gives each station's relative gain. Loading his transmitter and date, with that schedule, gives the same answers in this program:

- On the 27 stations in the first version of his table, the program's relative gain differs from his by 0.00 dB on average, and by no more than 0.12 dB at any one station.
- The average over 500 to 1,500 miles was 3.87 dB here against 3.86 dB in his table.
- The program also counted four more stations that met the 40-spot rule (ON5KQ, W0AY, WA3TTS and WA7LNW), so the 1,500 to 2,500 mile averages first differed (5.81 dB here against 6.06 dB). His updated paper includes those stations and agrees with this program on which ones qualify.

Open the **Long alternating blocks** example in the app to see it. The example uses 18 blocks (9 hours, to 21:00 UTC) at Dale's request, so its numbers differ a little from his first table, which ran to 21:30. The automated check in `tests/test_dale_study.py` repeats the comparison against the 27 stations of the first version of his table. His article also works out the expected gain by hand from antenna measurements and compares it with the WSPR result, which is worth reading on his site, [n3hxz.net](https://www.n3hxz.net/).
