"""Checks that drive the real app, page by page, with Streamlit's own test runner. The ones that need the internet (wspr.live,
NOAA) only run when you ask for them:

    python -m unittest discover -s tests -v                      (quick, offline)
    set RBN_TEST_NETWORK=1 && python -m unittest discover -s tests -v    (everything, a few minutes)
"""
import os
import sys
import tempfile
import unittest
from datetime import date

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.chdir(HERE)

from streamlit.testing.v1 import AppTest  # noqa: E402

NETWORK = os.environ.get("RBN_TEST_NETWORK") == "1"
needs_network = unittest.skipUnless(NETWORK, "set RBN_TEST_NETWORK=1 to run the checks that use the internet")


def page(function, **params):
    """A page run on its own, as the menu would, with the web address parameters given."""
    runner = os.path.join(tempfile.gettempdir(), f"rbn_{function}_runner.py")
    with open(runner, "w", encoding="utf-8") as f:
        f.write("import sys\nsys.path.insert(0, r'%s')\nimport web\nweb.%s()\n" % (HERE, function))
    at = AppTest.from_file(runner, default_timeout=600)
    for key, value in params.items():
        at.query_params[key] = value
    return at


def errors(at):
    return [e.value[:200] for e in at.exception]


def click(at, label):
    [b for b in at.sidebar.button if b.label == label][0].click()
    at.run()


def open_example(at, key):
    """Opens an example on the Compare page the way a visitor does: click its card."""
    [b for b in at.main.button if b.key == f"hero_{key}"][0].click()
    at.run()


def page_after_example(function, key, as_own_spots=False):
    """A page opened right after an example's own button was pressed on another page: the example's spots and settings are
    already in the session, the way they are when a visitor moves between pages. With `as_own_spots` the spots are no longer
    marked as an example, as if the visitor had loaded them themself."""
    runner = os.path.join(tempfile.gettempdir(), f"rbn_{function}_after_{key}_runner.py")
    lines = ["import sys", "sys.path.insert(0, r'%s')" % HERE, "import streamlit as st", "import web", "from views import inputs",
             "if 'started' not in st.session_state:", "    st.session_state['started'] = True", "    inputs.start_example(%r)" % key]
    if as_own_spots:
        lines.append("    st.session_state['_example'] = False")
    lines.append("web.%s()" % function)
    with open(runner, "w", encoding="utf-8") as f:
        f.write(chr(10).join(lines) + chr(10))
    return AppTest.from_file(runner, default_timeout=600)

class MySpotsPage(unittest.TestCase):
    def test_opens_with_the_load_and_example_buttons(self):
        at = page("spots_page").run()
        self.assertEqual(errors(at), [])
        self.assertEqual([b.label for b in at.sidebar.button], ["Load spots", "Try an example", "Start over"])

    def test_the_old_compare_checkbox_is_gone(self):
        at = page("spots_page").run()
        self.assertEqual([c.label for c in at.sidebar.checkbox if "Compare" in c.label], [])

    def test_a_link_fills_the_sidebar(self):
        at = page("spots_page", call="k5ohy", src="wspr", date="2026-10-04", band="20m", units="km").run()
        self.assertEqual(errors(at), [])
        self.assertEqual(at.session_state["callsign_in"], "K5OHY")
        self.assertEqual(at.session_state["src_in"], "WSPR")
        self.assertEqual(at.session_state["day_in"], date(2026, 10, 4))
        self.assertEqual(at.session_state["band_choice"], "20m")
        self.assertEqual(at.session_state["units_in"], "km")
        self.assertIsNone(at.session_state["raw"])  # no go=1, so nothing is loaded until you click

    def test_the_source_is_rbn_or_wspr_then_download_or_paste(self):
        at = page("spots_page").run()
        net = [r for r in at.sidebar.radio if r.key == "net_in"][0]
        self.assertEqual(net.options, ["RBN", "WSPR"])
        how = [r for r in at.sidebar.radio if r.key == "how_in"][0]
        how.set_value("Paste spots")
        at.run()
        self.assertEqual(at.session_state["src_in"], "Paste from RBN site")
        [r for r in at.sidebar.radio if r.key == "net_in"][0].set_value("WSPR")
        at.run()
        self.assertEqual(at.session_state["src_in"], "WSPR")
        self.assertEqual([r.key for r in at.sidebar.radio if r.key == "how_in"], [])
        [r for r in at.sidebar.radio if r.key == "net_in"][0].set_value("RBN")
        at.run()
        self.assertEqual(at.session_state["src_in"], "Paste from RBN site")  # it remembers your last RBN choice

    def test_switching_to_wspr_moves_the_date_from_yesterday_to_today(self):
        at = page("spots_page").run()
        yesterday = at.session_state["day_in"]
        [r for r in at.sidebar.radio if r.key == "net_in"][0].set_value("WSPR")
        at.run()
        self.assertEqual(errors(at), [])
        self.assertEqual((at.session_state["day_in"] - yesterday).days, 1)
        [r for r in at.sidebar.radio if r.key == "net_in"][0].set_value("RBN")
        at.run()
        self.assertEqual(at.session_state["day_in"], yesterday)  # RBN has no file for today, so it steps back

    def test_a_day_you_picked_stays_when_you_switch_source(self):
        at = page("spots_page", call="K5OHY", src="rbn", date="2024-03-01").run()
        [r for r in at.sidebar.radio if r.key == "net_in"][0].set_value("WSPR")
        at.run()
        self.assertEqual(at.session_state["day_in"], date(2024, 3, 1))

    def test_a_date_range_is_picked_on_one_calendar(self):
        at = page("spots_page", call="K5OHY", src="rbn", date="2024-03-01..2024-03-03").run()
        self.assertEqual(errors(at), [])
        self.assertEqual(at.session_state["span_in"], "Date range")
        self.assertEqual(tuple(at.session_state["range_in"]), (date(2024, 3, 1), date(2024, 3, 3)))
        self.assertEqual([d.label for d in at.sidebar.date_input], ["Dates (UTC)"])
        self.assertEqual(at.session_state["to_in"], date(2024, 3, 3))

    def test_start_over_clears_everything_and_goes_back_to_the_latest_day(self):
        at = page("spots_page", call="K5OHY", grid="DM81wx", src="wspr", date="2024-03-01").run()
        self.assertEqual(at.session_state["day_in"], date(2024, 3, 1))
        click(at, "Start over")
        self.assertEqual(errors(at), [])
        self.assertGreater(at.session_state["day_in"], date(2025, 1, 1))
        self.assertEqual(at.session_state["callsign_in"], "")
        self.assertEqual(at.session_state["grid_in"], "")
        self.assertEqual(at.session_state["src_in"], "Download by date")
        self.assertIsNone(at.session_state["raw"])

    def test_start_over_on_compare_clears_both_callsigns_and_keeps_wspr(self):
        at = page("compare_page", call="K5OHY", cb="N3HXZ", grid="DM81wx", src="wspr", date="2024-03-01").run()
        self.assertEqual(at.session_state["callsign_b_in"], "N3HXZ")
        click(at, "Start over")
        self.assertEqual(errors(at), [])
        for key in ("callsign_in", "callsign_b_in", "grid_in"):
            self.assertEqual(at.session_state[key], "", key)
        self.assertEqual(at.session_state["src_in"], "WSPR")

    def test_use_my_own_data_clears_an_example(self):
        at = page("spots_page").run()
        click(at, "Try an example")
        self.assertEqual(at.session_state["callsign_in"], "K5OHY")
        [b for b in at.main.button if b.label == "Use my own data instead"][0].click()
        at.run()
        self.assertEqual(errors(at), [])
        self.assertEqual(at.session_state["callsign_in"], "")
        self.assertIsNone(at.session_state["raw"])
        self.assertFalse(at.session_state["_example"] if "_example" in at.session_state else False)

    def test_a_bad_link_is_ignored(self):
        at = page("spots_page", call="K5OHY", src="nonsense", date="not-a-date", band="99m", units="furlongs").run()
        self.assertEqual(errors(at), [])
        self.assertEqual(at.session_state["callsign_in"], "K5OHY")
        self.assertIn(at.session_state["src_in"], ("Download by date", "Paste from RBN site", "WSPR"))

    def test_the_address_follows_the_sidebar(self):
        at = page("spots_page", call="K5OHY", src="wspr", date="2026-10-04").run()
        self.assertEqual(at.query_params["call"], ["K5OHY"])
        self.assertEqual(at.query_params["src"], ["wspr"])

    def test_empty_page_suggests_the_example_and_the_compare_page(self):
        at = page("spots_page").run()
        self.assertTrue(any("Try an example" in i.value for i in at.info))
        self.assertTrue(any("Compare antennas" in m.value for m in at.markdown))

    def test_the_empty_page_has_an_example_button_on_the_main_stage(self):
        at = page("spots_page").run()
        self.assertEqual([b.label for b in at.main.button], ["Try an example"])

    def test_the_example_shows_rbn_spots_on_the_map_and_a_shareable_link(self):
        at = page("spots_page").run()
        click(at, "Try an example")
        self.assertEqual(errors(at), [])
        self.assertTrue(any("Reverse Beacon Network" in i.value for i in at.info))
        self.assertEqual(at.session_state["kind"], "RBN")
        self.assertEqual(at.session_state["day_in"], date(2025, 10, 23))
        self.assertGreater(len(at.session_state["raw"]), 50)
        self.assertEqual(len(at.tabs), 2)  # Map & direction, Session report
        self.assertTrue(any("call=K5OHY" in c.value for c in at.sidebar.code))

    @needs_network
    def test_a_shared_link_loads_the_spots(self):
        at = page("spots_page", call="K5OHY", src="wspr", date="2026-10-04", band="20m", go="1").run()
        self.assertEqual(errors(at), [])
        self.assertGreater(len(at.session_state["raw"]), 100)


class ComparePage(unittest.TestCase):
    def test_opens_with_the_steps_and_just_the_load_and_start_over_buttons(self):
        at = page("compare_page").run()
        self.assertEqual(errors(at), [])
        self.assertEqual([b.label for b in at.sidebar.button], ["Load spots", "Start over"])
        self.assertEqual([s.key for s in at.sidebar.selectbox if s.key == "example_pick"], [])
        text = " ".join(m.value for m in at.markdown)
        self.assertIn("With WSPR, the best way", text)
        self.assertIn("With RBN, for a quick CW check", text)

    def test_the_empty_page_shows_every_example_as_a_labelled_card(self):
        from views import inputs
        at = page("compare_page").run()
        self.assertEqual([b.key for b in at.main.button], [f"hero_{key}" for key, _, _, _ in inputs.COMPARE_EXAMPLES])
        text = " ".join(c.value for c in at.main.caption) + " " + " ".join(m.value for m in at.main.markdown)
        for _, how, title, _ in inputs.COMPARE_EXAMPLES:
            self.assertIn(how, text)
            self.assertIn(title, text)

    def test_every_example_opens_from_its_card(self):
        from views import inputs
        for key, _, _, _ in inputs.COMPARE_EXAMPLES:
            at = page("compare_page").run()
            [b for b in at.main.button if b.key == f"hero_{key}"][0].click()
            at.run()
            self.assertEqual(errors(at), [], key)
            self.assertEqual(at.session_state["_example"], key)
            self.assertTrue(any("This is an example" in i.value for i in at.info), key)

    def test_the_dx_commander_examples_use_two_callsigns_and_the_saved_data(self):
        for key, call, other, band, first in (("dxc20", "M0MCX", "M0XXT", "20m", "Delta loop"),
                                              ("dxc40", "M0XXT", "M0MCX", "40m", "Vertical")):
            at = page("compare_page").run()
            open_example(at, key)
            self.assertEqual(errors(at), [], key)
            ss = at.session_state
            self.assertEqual((ss["callsign_in"], ss["callsign_b_in"], ss["band_choice"], ss["cmp_name_a"]), (call, other, band, first))
            self.assertEqual((ss["tx_call"], ss["tx_call_b"]), (call, other))
            self.assertTrue(any("Delta loop" in m.value or "Vertical" in m.value for m in at.markdown))
            self.assertTrue(any("Opened from a saved copy" in c.value for c in at.main.caption), key)

    def test_closing_an_example_goes_back_to_the_cards_on_wspr_with_no_second_callsign(self):
        at = page("compare_page").run()
        open_example(at, "dxc20")
        self.assertEqual(at.session_state["callsign_b_in"], "M0XXT")
        [b for b in at.main.button if b.label == "Close example and see the others"][0].click()
        at.run()
        self.assertEqual(errors(at), [])
        self.assertEqual(at.session_state["src_in"], "WSPR")
        self.assertEqual(at.session_state["callsign_b_in"], "")
        open_example(at, "quick")
        self.assertEqual(errors(at), [])
        self.assertIsNone(at.session_state["tx_call_b"])

    def test_example_notes_are_short(self):
        from views import inputs
        for key, _, _, _ in inputs.COMPARE_EXAMPLES:
            at = page("compare_page").run()
            open_example(at, key)
            note = [i.value for i in at.info if i.value.startswith("This is an example")][0]
            self.assertLess(len(note), 420, key)

    def test_it_starts_on_wspr(self):
        at = page("compare_page").run()
        self.assertEqual(at.session_state["src_in"], "WSPR")

    def test_there_is_no_time_window_for_wspr(self):
        at = page("compare_page").run()
        self.assertEqual([s.label for s in at.sidebar.slider if s.label == "UTC time window"], [])

    def test_the_quick_example_shows_a_verdict(self):
        at = page("compare_page").run()
        open_example(at, "quick")
        self.assertEqual(errors(at), [])
        text = " ".join(m.value for m in at.markdown) + " " + " ".join(i.value for i in at.info)
        self.assertIn("This is an example", text)
        self.assertIn("better", text)
        self.assertTrue(any("call=K5OHY" in c.value for c in at.sidebar.code))

    @needs_network
    def test_two_callsigns_compare_as_a_and_b_and_travel_in_the_link(self):
        at = page("compare_page", call="M0MCX", cb="M0XXT", src="wspr", date="2026-01-14", band="20m", go="1", n="6",
                  ts="13:38").run()
        self.assertEqual(errors(at), [])
        self.assertEqual(at.session_state["tx_call_b"], "M0XXT")
        text = " ".join(m.value for m in at.markdown)
        self.assertIn("Signal advantage", text)
        link = [c.value for c in at.sidebar.code if "call=M0MCX" in c.value][0]
        self.assertIn("cb=M0XXT", link)

    @needs_network
    def test_hand_corrected_antenna_cells_travel_in_the_link(self):
        at = page("compare_page", call="K5OHY", src="wspr", date="2026-10-04", band="20m", go="1", n="12", ord="abba",
                  ed="3B,5X").run()
        self.assertEqual(errors(at), [])
        link = [c.value for c in at.sidebar.code if "call=K5OHY" in c.value][0]
        self.assertIn("ed=3B%2C5X", link)

    @needs_network
    def test_a_pasted_block_schedule_travels_in_the_link(self):
        schedule = "12:00-12:30 A;12:30-13:00 B;13:00-13:30 A;13:30-14:00 B"
        at = page("compare_page", call="N3HXZ", src="wspr", date="2026-08-26", band="20m", go="1", sw="blocks", bl="30",
                  bp=schedule).run()
        self.assertEqual(errors(at), [])
        link = [c.value for c in at.sidebar.code if "call=N3HXZ" in c.value][0]
        self.assertIn("bp=12%3A00-12%3A30+A%3B12%3A30-13%3A00+B", link)

    @needs_network
    def test_a_short_test_with_very_different_farthest_reach_does_not_say_similar(self):
        """Callum's 20m delta loop against a vertical: 10,582 mi against 3,827 mi, but only 3 pairs, so it is not called."""
        at = page("compare_page", call="M0MCX", cb="M0XXT", grid="IO92di", src="wspr", units="mi", date="2026-01-14",
                  band="20m", go="1", na="Delta loop", nb="Vertical", n="6", ts="13:38", mr="1").run()
        self.assertEqual(errors(at), [])
        text = " ".join(m.value for m in at.markdown)
        self.assertIn("too short to tell", text)
        self.assertNotIn("Similar farthest reach", text)
        self.assertIn("3 receivers beyond 5,000 mi heard Delta loop, 0 heard Vertical", text)

    def test_a_cut_off_listening_list_is_reported_and_not_used(self):
        import example_data
        from unittest import mock
        from views import compare_view
        rows, _ = example_data.listening("20m", "2026-10-04 18:00:00", "2026-10-04 18:30:00")
        cut_off = (rows, True)  # the saved listening list, reported as having hit its row limit
        with mock.patch.object(compare_view, "load_listening", return_value=cut_off):
            at = page("compare_page").run()
            open_example(at, "quick")
        self.assertEqual(errors(at), [])
        self.assertTrue(any("cut off at its row limit" in w.value for w in at.warning))

    @needs_network
    def test_truly_similar_farthest_reach_still_says_similar(self):
        at = page("compare_page", call="M0XXT", cb="M0MCX", grid="IO92di", src="wspr", units="mi", date="2026-01-14",
                  band="40m", go="1", na="Vertical", nb="Delta loop", n="6", ts="21:34", mr="1").run()
        self.assertEqual(errors(at), [])
        text = " ".join(m.value for m in at.markdown)
        self.assertIn("Similar farthest reach", text)

    @needs_network
    def test_your_own_spots_wait_for_you_to_confirm_the_setup(self):
        at = page("compare_page", call="K5OHY", src="wspr", date="2026-10-04", band="20m", go="1").run()
        self.assertEqual(errors(at), [])
        self.assertFalse(at.session_state["setup_ok"])
        text = " ".join(m.value for m in at.markdown)
        self.assertNotIn("Signal advantage", text)  # no result until it is confirmed
        confirm = [b for b in at.main.button if b.label.startswith("This matches what I did")]
        self.assertEqual(len(confirm), 1)
        confirm[0].click()
        at.run()
        self.assertEqual(errors(at), [])
        self.assertTrue(at.session_state["setup_ok"])
        self.assertIn("Signal advantage", " ".join(m.value for m in at.markdown))
        self.assertEqual([b for b in at.main.button if b.label.startswith("This matches what I did")], [])

    @needs_network
    def test_examples_and_shared_tests_need_no_confirming(self):
        at = page("compare_page").run()
        open_example(at, "quick")
        self.assertTrue(at.session_state["setup_ok"])
        shared = page("compare_page", call="K5OHY", src="wspr", date="2026-10-04", band="20m", go="1", n="12", ord="abba").run()
        self.assertTrue(shared.session_state["setup_ok"])

    def test_your_own_spots_from_my_spots_are_not_a_confirmed_test_when_you_open_compare(self):
        at = page_after_example("compare_page", "map", as_own_spots=True).run()
        self.assertEqual(errors(at), [])
        self.assertFalse(at.session_state["setup_ok"])
        self.assertNotIn("Signal advantage", " ".join(m.value for m in at.markdown))  # no winner before you check the setup
        self.assertEqual(len([b for b in at.main.button if b.label.startswith("This matches what I did")]), 1)

    def test_a_result_across_two_bands_is_called_a_band_comparison(self):
        at = page_after_example("compare_page", "map", as_own_spots=True).run()
        [b for b in at.main.button if b.label.startswith("This matches what I did")][0].click()
        at.run()
        self.assertEqual(errors(at), [])
        warnings = " ".join(w.value for w in at.warning)
        self.assertIn("compares two bands, not two antennas", warnings)

    def test_the_compare_examples_still_need_no_confirming(self):
        for key in ("quick", "dxc20"):
            at = page_after_example("compare_page", key).run()
            self.assertEqual(errors(at), [], key)
            self.assertTrue(at.session_state["setup_ok"], key)

    def test_the_count_card_says_which_number_it_is(self):
        at = page("compare_page").run()
        open_example(at, "quick")
        self.assertEqual(errors(at), [])
        text = " ".join(m.value for m in at.markdown)
        self.assertIn("Receivers compared", text)  # 184 were compared, of 189 that heard both
        self.assertIn("of 189 that heard both", text)

    def test_the_gain_tiles_say_how_they_differ_from_the_verdict(self):
        at = page("compare_page").run()
        open_example(at, "quick")
        text = " ".join(c.value for c in at.caption)
        self.assertIn("The verdict's number is the average over every receiver compared, taking each one pair by pair", text)

    def test_the_dashboard_watches_one_direction_and_a_second_on_request(self):
        at = page("compare_page").run()
        open_example(at, "long")
        self.assertEqual(errors(at), [])
        watched = at.session_state["dash_dir_a"]
        self.assertIn(watched, ("N", "NE", "E", "SE", "S", "SW", "W", "NW"))
        self.assertEqual(at.session_state["dash_dir_b"], "Off")
        labels = [m.label for m in at.main.metric]
        self.assertIn(f"{watched} average gain", labels)
        other = "N" if watched != "N" else "S"
        [s for s in at.main.selectbox if s.key == "dash_dir_b"][0].set_value(other)
        at.run()
        self.assertEqual(errors(at), [])
        labels = [m.label for m in at.main.metric]
        self.assertIn(f"{other} average gain", labels)
        self.assertIn(f"{watched} average gain", labels)

    def test_the_dashboard_follows_octants_or_quadrants(self):
        at = page("compare_page").run()
        open_example(at, "long")
        octants = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
        picker = lambda: [s for s in at.main.selectbox if s.key == "dash_dir_a"][0]  # noqa: E731
        self.assertEqual(tuple(picker().options), octants)
        [r for r in at.main.radio if r.key == "gs_groups"][0].set_value("Quadrants (4)")
        at.run()
        self.assertEqual(errors(at), [])
        self.assertEqual(tuple(picker().options), ("N", "E", "S", "W"))
        self.assertIn(at.session_state["dash_dir_a"], ("N", "E", "S", "W"))
        self.assertIn(f"{at.session_state['dash_dir_a']} average gain", [m.label for m in at.main.metric])
        [r for r in at.main.radio if r.key == "gs_groups"][0].set_value("Octants (8)")
        at.run()
        self.assertEqual(errors(at), [])
        self.assertEqual(tuple(picker().options), octants)

    def test_one_receiver_numbers_follow_the_averaging_choice(self):
        at = page("compare_page").run()
        open_example(at, "long")
        method = [r for r in at.main.radio if r.key.startswith("rx_method_")][0]
        method.set_value("SNR (dB)")
        at.run()
        self.assertEqual(errors(at), [])
        text = " ".join(c.value for c in at.caption)
        self.assertIn("Middle of the dB reports, as in the list", text)
        [r for r in at.main.radio if r.key.startswith("rx_method_")][0].set_value("Linear power")
        at.run()
        self.assertEqual(errors(at), [])
        text = " ".join(c.value for c in at.caption)
        self.assertIn("Linear power, as in the list", text)

    def test_the_dashboard_is_shut_by_default_with_its_headline_in_the_title(self):
        at = page("compare_page").run()
        open_example(at, "long")
        box = [e for e in at.main.expander if e.label.startswith("Monitoring dashboard")]
        self.assertEqual(len(box), 1)
        self.assertRegex(box[0].label, r"^Monitoring dashboard: average gain [+-][0-9.]+ dB over [0-9]+ receivers$")
        self.assertFalse(box[0].proto.expanded)

    def test_the_leave_out_box_is_with_the_receiver_results_not_the_setup(self):
        at = page("compare_page").run()
        open_example(at, "long")
        self.assertEqual(errors(at), [])
        box = [e for e in at.main.expander if e.label.startswith("Leave out some reports or receivers")]
        self.assertEqual(len(box), 1)
        self.assertEqual(box[0].label, "Leave out some reports or receivers")  # shut, and nothing is left out yet
        self.assertFalse(box[0].proto.expanded)
        self.assertTrue(any(c.value.startswith("This changes the dashboard") for c in at.main.caption))

    def test_the_leave_out_box_says_when_it_is_in_use(self):
        at = page("compare_page").run()
        open_example(at, "long")
        [n for n in at.main.number_input if n.key == "avg_weak"][0].set_value(25)
        at.run()
        self.assertEqual(errors(at), [])
        self.assertIn("Leave out some reports or receivers (in use)", [e.label for e in at.main.expander])

    def test_the_rbn_example_compares_the_loop_and_the_dipole_by_frequency(self):
        at = page("compare_page").run()
        open_example(at, "rbn")
        self.assertEqual(errors(at), [])
        self.assertEqual(at.session_state["kind"], "RBN")
        self.assertEqual(at.session_state["cmp_name_b"], "20m dipole, 40 ft")
        text = " ".join(m.value for m in at.markdown) + " " + " ".join(i.value for i in at.info)
        self.assertIn("14069.5 kHz", text)
        self.assertIn("20m dipole, 40 ft", text)
        self.assertIn("(A)</span> vs", text)  # the result's title, with A and B coloured
        self.assertIn("on 20 m", text)

    def test_the_long_test_example_uses_dales_schedule_and_40_reports(self):
        at = page("compare_page").run()
        open_example(at, "long")
        self.assertEqual(errors(at), [])
        self.assertEqual(at.session_state["callsign_in"], "N3HXZ")
        self.assertEqual(at.session_state["test_mode"], "In long blocks")
        self.assertEqual(at.session_state["rx_min_reports_blk"], 40)
        self.assertIn("Dale, N3HXZ", " ".join(i.value for i in at.info))
        self.assertTrue(any("with 40 or more reports on each" in c.value for c in at.caption))
        self.assertTrue(any("getting out better" in m.value for m in at.markdown))

    def test_comparison_filters_run(self):
        at = page("compare_page").run()
        open_example(at, "long")
        weak = [n for n in at.number_input if n.key == "avg_weak"]
        self.assertTrue(weak)
        weak[0].set_value(25)
        at.run()
        self.assertEqual(errors(at), [])

    def test_a_test_link_fills_in_the_setup(self):
        at = page("compare_page", call="N3HXZ", src="wspr", date="2026-08-26", band="20m", na="Loop", nb="Dipole", sw="blocks",
                  bl="30", ord="abba", mr="25", fl="1", nr="50", wk="20", units="mi").run()
        self.assertEqual(errors(at), [])
        ss = at.session_state
        self.assertEqual((ss["cmp_name_a"], ss["cmp_name_b"]), ("Loop", "Dipole"))
        self.assertEqual(ss["test_mode"], "In long blocks")
        self.assertEqual(ss["blk_len"], 30)
        self.assertTrue(ss["blk_order"].startswith("A, B, B, A"))
        self.assertEqual(ss["rx_min_reports_blk"], 25)
        self.assertTrue(ss["avg_floor"])
        self.assertEqual((ss["avg_near_mi"], ss["avg_weak"]), (50, 20))

    def test_a_bad_test_link_is_ignored(self):
        at = page("compare_page", sw="sideways", n="999", bl="1", ord="zzz", mr="0", nr="-5", wk="abc", ts="<script>").run()
        self.assertEqual(errors(at), [])
        self.assertNotIn("test_mode", at.session_state)

    @needs_network
    def test_the_link_box_holds_the_whole_test_and_reopens_it(self):
        at = page("compare_page").run()
        open_example(at, "long")
        link = [c.value for c in at.sidebar.code if "call=N3HXZ" in c.value][0]
        for part in ("sw=blocks", "bl=30", "bn=", "bs=12%3A00", "mr=40", "na=17+ft"):
            self.assertIn(part, link)
        from urllib.parse import parse_qs, urlparse
        q = {k: v[0] for k, v in parse_qs(urlparse(link).query).items()}
        again = page("compare_page", **q).run()
        self.assertEqual(errors(again), [])
        self.assertEqual(again.session_state["rx_min_reports_blk"], 40)
        self.assertTrue(any("getting out better" in m.value for m in again.markdown))

    def test_the_receiver_minimum_opens_at_two_and_says_how_many_receivers_that_leaves(self):
        at = page("compare_page").run()
        open_example(at, "quick")
        self.assertEqual(errors(at), [])
        self.assertEqual(at.session_state["rx_min_reports_pair"], 2)
        notes = [c.value for c in at.main.caption if c.value.startswith("Showing ")]
        self.assertEqual(len(notes), 1)
        self.assertIn("with 2 or more reports on each", notes[0])
        slider = [s for s in at.main.slider if s.key == "rx_min_reports_pair"][0]
        slider.set_value(1)
        at.run()
        self.assertEqual(errors(at), [])
        self.assertTrue(any(c.value.startswith("Showing all") for c in at.main.caption))

    def test_a_long_example_says_why_the_minimum_is_where_it_is(self):
        at = page("compare_page").run()
        open_example(at, "long")
        self.assertEqual(errors(at), [])
        notes = [c.value for c in at.main.caption if c.value.startswith("Showing ")]
        self.assertEqual(len(notes), 1)
        self.assertIn("40 or more reports", notes[0])

    def test_the_slider_says_how_to_tell_when_the_result_has_settled(self):
        at = page("compare_page").run()
        open_example(at, "long")
        self.assertEqual(errors(at), [])
        self.assertTrue(any(c.value.startswith("Has it settled?") and "5 to 10 receivers" in c.value for c in at.main.caption))

    def test_the_receiver_tab_shows_the_gain_numbers_beside_the_slider(self):
        at = page("compare_page").run()
        open_example(at, "long")
        self.assertEqual(errors(at), [])
        shown = {m.label: m.value for m in at.main.metric}
        for label in ("Typical gain", "Average gain", "Biggest gain", "Smallest gain"):
            self.assertIn(label, shown)
        self.assertEqual(len([s for s in at.main.selectbox if s.key == "dash_dir_a"]), 1)
        self.assertEqual(shown["Receivers"], "31")
        slider = [s for s in at.main.slider if s.key == "rx_min_reports_blk"][0]
        slider.set_value(20)
        at.run()
        self.assertEqual(errors(at), [])
        self.assertGreater(int({m.label: m.value for m in at.main.metric}["Receivers"]), 31)

    def test_the_setup_line_says_which_blocks_the_results_use(self):
        at = page("compare_page").run()
        open_example(at, "long")
        self.assertEqual(errors(at), [])
        line = [c.value for c in at.main.caption if c.value.startswith("Assumed setup")]
        self.assertEqual(len(line), 1)
        self.assertIn("these results use 20 blocks of about 30 minutes, 10 on A and 10 on B, from 12:00 to 22:00 UTC", line[0])

    def test_spots_you_loaded_yourself_carry_over_to_my_spots(self):
        """What you load on one page is there on the other, so you do not have to enter it twice."""
        at = page_after_example("spots_page", "quick", as_own_spots=True).run()
        self.assertEqual(errors(at), [])
        self.assertIsNotNone(at.session_state["raw"])
        self.assertEqual(at.session_state["callsign"], "K5OHY")

    def test_the_my_spots_example_does_not_follow_you_to_compare(self):
        """An example belongs to the page that opened it: Compare shows its own examples, not the map's spots."""
        at = page_after_example("compare_page", "map").run()
        self.assertEqual(errors(at), [])
        self.assertIsNone(at.session_state["raw"])
        self.assertEqual(at.session_state["callsign_in"], "")
        self.assertEqual(at.session_state["src_in"], "WSPR")
        self.assertEqual(len([b for b in at.main.button if b.key.startswith("hero_")]), 5)

    def test_a_compare_example_does_not_follow_you_to_my_spots(self):
        at = page_after_example("spots_page", "quick").run()
        self.assertEqual(errors(at), [])
        self.assertIsNone(at.session_state["raw"])
        self.assertEqual(at.session_state["callsign_in"], "")
        self.assertEqual([b.label for b in at.main.button], ["Try an example"])

    def test_choosing_another_source_closes_an_open_example(self):
        for function, key, to_wspr in (("compare_page", "rbn", True), ("compare_page", "quick", False), ("spots_page", "map", True)):
            at = page_after_example(function, key).run()
            self.assertEqual(at.session_state["_example"], key)
            [r for r in at.sidebar.radio if r.key == "net_in"][0].set_value("WSPR" if to_wspr else "RBN")
            at.run()
            self.assertEqual(errors(at), [], key)
            self.assertIsNone(at.session_state["raw"], key)
            self.assertEqual(at.session_state["callsign_in"], "", key)
            self.assertEqual(at.session_state["src_in"], "WSPR" if to_wspr else "Download by date", key)

    def test_choosing_another_source_keeps_spots_you_loaded_yourself(self):
        at = page_after_example("compare_page", "quick", as_own_spots=True).run()
        [r for r in at.sidebar.radio if r.key == "net_in"][0].set_value("RBN")
        at.run()
        self.assertIsNotNone(at.session_state["raw"])


class SkippedTransmissions(unittest.TestCase):
    """A transmission you skipped can still show up as a slot a few receivers with wrong clocks reported."""

    @staticmethod
    def spots(counts):
        import pandas as pd
        rows = [(pd.Timestamp("2026-10-29 18:00") + pd.Timedelta(minutes=2 * slot), f"RX{i}")
                for slot, n in enumerate(counts) for i in range(n)]
        return pd.DataFrame(rows, columns=["time", "spotter"])

    def test_a_skipped_slot_heard_by_a_few_receivers_is_not_a_transmission(self):
        from views.compare_view import _without_ghost_cycles
        # 18:16 was skipped (3 receivers logged it anyway) and 18:26 is an echo of the last one (4)
        kept = _without_ghost_cycles(self.spots([131, 108, 83, 93, 95, 129, 133, 115, 3, 121, 121, 109, 125, 4]))
        self.assertEqual(sorted(kept["time"].unique()).__len__(), 12)
        self.assertEqual(sorted(kept["time"].dt.strftime("%H:%M").unique())[8], "18:18")

    def test_a_weak_slot_that_is_still_a_real_share_of_the_usual_is_kept(self):
        from views.compare_view import _without_ghost_cycles
        kept = _without_ghost_cycles(self.spots([120, 110, 40, 115, 118, 112]))
        self.assertEqual(kept["time"].nunique(), 6)

    def test_a_quiet_band_throws_nothing_out(self):
        from views.compare_view import _without_ghost_cycles
        kept = _without_ghost_cycles(self.spots([6, 5, 3, 7, 6, 4]))
        self.assertEqual(kept["time"].nunique(), 6)


class SavedExamplesMatchTheLiveData(unittest.TestCase):
    @needs_network
    def test_the_saved_rbn_example_still_matches_the_download(self):
        """The saved copy is a snapshot; this notices if RBN's file for that day ever changes."""
        import example_data
        from data_sources import download_rbn_day
        _, saved = example_data.load("rbn")
        live = download_rbn_day("20260927", "K5OHY")
        self.assertEqual(len(live), len(saved))
        self.assertAlmostEqual(float(live["snr"].sum()), float(saved["snr"].sum()), places=3)


class BandConditionsPage(unittest.TestCase):
    @needs_network
    def test_the_dashboard_opens(self):
        at = page("conditions_page", call="K5OHY").run()
        self.assertEqual(errors(at), [])
        self.assertEqual([x.label for x in at.selectbox if x.label == "Mode"], ["Mode"])

    @needs_network
    def test_an_examples_callsign_does_not_become_yours(self):
        at = page_after_example("conditions_page", "dxc20").run()
        self.assertEqual(at.session_state["cond_call"], "")

    @needs_network
    def test_every_mode_works(self):
        at = page("conditions_page", call="K5OHY").run()
        mode = [x for x in at.selectbox if x.label == "Mode"][0]
        self.assertEqual(mode.options, ["CW", "SSB", "FT8", "WSPR"])
        for name in mode.options:
            [x for x in at.selectbox if x.label == "Mode"][0].set_value(name)
            at.run()
            self.assertEqual(errors(at), [], name)

    @needs_network
    def test_a_link_sets_power_mode_and_look_back(self):
        at = page("conditions_page", call="K5OHY", power="5", mode="SSB", window="60", units="km").run()
        self.assertEqual(errors(at), [])
        self.assertEqual(at.session_state["cond_power"], 5.0)
        self.assertEqual(at.session_state["cond_mode"], "SSB")
        self.assertEqual(at.session_state["cond_window"], 60)
        self.assertEqual(at.session_state["cond_units"], "km")

    def test_the_empty_page_offers_a_use_my_location_button(self):
        at = page("conditions_page").run()
        self.assertEqual(errors(at), [])
        self.assertEqual([b.label for b in at.main.button], ["Use my location"])

    def test_the_use_my_location_button_switches_to_your_location(self):
        at = page("conditions_page").run()
        at.main.button[0].click()
        at.run()
        # the test runner cannot load the page's own location component; that is the only thing allowed to fail here
        self.assertEqual([e for e in errors(at) if "not registered" not in e], [])
        self.assertEqual(at.session_state["cond_where"], "My location")
        self.assertEqual(at.session_state["_locate_ticket"], 1)

    def test_bad_link_values_are_ignored(self):
        at = page("conditions_page", call="K5OHY", power="99999", mode="bogus", window="7").run()
        self.assertEqual(at.session_state["cond_power"], 100.0)
        self.assertEqual(at.session_state["cond_mode"], "CW")
        self.assertEqual(at.session_state["cond_window"], 30)


class HelpPage(unittest.TestCase):
    def test_the_readme_shows_without_error(self):
        at = page("help_page").run()
        self.assertEqual(errors(at), [])
        text = "\n".join(m.value for m in at.markdown)
        self.assertIn("Quick start", text)
        self.assertIn("Open an example", text)
        self.assertIn("DX Commander", text)
        self.assertIn("/blob/main/docs/METHODOLOGY.md", text)  # the README's relative link, pointed at the repository
        self.assertNotIn("](docs/METHODOLOGY.md)", text)
        self.assertNotIn("farfield-banner", text)  # the banner is for GitHub, not the Help page


class WholeApp(unittest.TestCase):
    def test_the_menu_has_the_four_pages(self):
        at = AppTest.from_file(os.path.join(HERE, "web.py"), default_timeout=600).run()
        self.assertEqual(errors(at), [])


if __name__ == "__main__":
    unittest.main()
