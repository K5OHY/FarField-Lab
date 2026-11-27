"""A power that changes during a log: 75 W on a beam, then 5 W on a doublet. As a number it is the first power; the calculations ask for the power at a moment."""
import pickle
import re
import unittest

import log_check_html as lh
import log_foundations as lf


def plan():
    return lf.PowerPlan([("2025-10-23 17:00", 5), ("2025-10-23 00:00", 75)])           # given out of order on purpose


class ThePlan(unittest.TestCase):
    def test_it_is_the_first_power_as_a_number_and_changes_at_its_steps(self):
        p = plan()
        self.assertEqual(float(p), 75.0)
        self.assertEqual((p.at("2025-10-23 16:59:59"), p.at("2025-10-23 17:00"), p.at("2025-10-24 03:00")), (75.0, 5.0, 5.0))
        self.assertEqual(p.at("2025-10-22 12:00"), 75.0)                               # before the first step: the first power

    def test_the_helpers_treat_a_plain_power_and_a_plan_alike(self):
        self.assertEqual(lf.power_at(100, "2025-10-23 12:00"), 100.0)
        self.assertEqual(lf.power_at(plan(), "2025-10-23 18:00"), 5.0)
        self.assertEqual((lf.power_text(100), lf.power_text(7.5)), ("100 W", "7.5 W"))
        self.assertEqual(lf.power_text(plan()), "75 W until 17:00 UTC, then 5 W")
        self.assertEqual(lf.power_text(plan(), "2025-10-23 18:00"), "5 W")

    def test_it_reads_in_words_wherever_the_page_writes_the_power(self):
        self.assertEqual(f"estimate for {plan():g} W in CW", "estimate for 75 W until 17:00 UTC, then 5 W in CW")
        self.assertEqual(f"{100.0:g} W", "100 W")                                      # a plain power is untouched
        two_days = lf.PowerPlan([("2025-10-23 00:00", 75), ("2025-10-24 08:00", 10)])
        self.assertEqual(two_days.words(), "75 W until 24 Oct 08:00 UTC, then 10 W")   # a change on another day names it
        self.assertAlmostEqual(f"{plan():.1f}" == "75.0", True)                        # other formats are the number

    def test_two_plans_are_told_apart_in_a_cache_key_and_a_plan_is_not_a_plain_power(self):
        from views.log_view import _power_key
        self.assertNotEqual(_power_key(plan()), _power_key(75.0))
        self.assertEqual(_power_key(plan()), _power_key(plan()))
        self.assertNotEqual(_power_key(plan()), _power_key(lf.PowerPlan([("2025-10-23 00:00", 75), ("2025-10-23 16:00", 5)])))

    def test_it_survives_being_copied_and_stored(self):
        import copy
        for other in (pickle.loads(pickle.dumps(plan())), copy.deepcopy(plan())):
            self.assertEqual(other.steps, plan().steps)
            self.assertEqual(float(other), 75.0)

    def test_a_plan_with_no_step_or_a_power_of_zero_is_refused(self):
        with self.assertRaises(ValueError):
            lf.PowerPlan([])
        with self.assertRaises(ValueError):
            lf.PowerPlan([("2025-10-23 00:00", 0)])

    def test_the_worked_example_uses_the_power_of_its_own_band(self):
        example = {"band": "20m", "rx": "K1RA", "obs": 20.0, "est": 8.0, "diff": 12.0, "after": 2.0, "power_w": 5.0}
        text = " ".join(re.sub(r"<[^>]+>", " ", lh.signal_math_html(plan(), "CW", 10.0, example, {"CW": -23})).split())
        self.assertIn("The WSPR estimate for 5 W at that receiver", text)
        self.assertIn("This log changed power (75 W until 17:00 UTC, then 5 W)", text)
        self.assertNotIn("You entered", text)
        plain = " ".join(re.sub(r"<[^>]+>", " ", lh.signal_math_html(75.0, "CW", 10.0, None, {"CW": -23})).split())
        self.assertIn("You entered 75 W", plain)

    def test_a_box_names_its_own_power_in_its_tooltip_text(self):
        self.assertEqual(lh._power_at_text(plan(), "2025-10-23 14:00"), "75 W")
        self.assertEqual(lh._power_at_text(plan(), "2025-10-23 19:00"), "5 W")
        self.assertEqual(lh._power_at_text(100.0, "2025-10-23 19:00"), "100 W")


if __name__ == "__main__":
    unittest.main()
