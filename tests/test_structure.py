"""The app is split into modules; these checks make sure they all load, in any order, without importing each other in a circle,
and that the entry point stays small."""
import importlib
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = ["ui_common", "data_sources", "maps", "charts", "pdfs", "views.compare_view", "views.spots_view",
           "views.conditions_view", "views.help_view", "web"]


def docs_files():
    """Every guide in docs/, as 'docs/name.md'."""
    return [f"docs/{name}" for name in sorted(os.listdir(os.path.join(HERE, "docs"))) if name.endswith(".md")]


def slug(heading):
    """The anchor GitHub makes from a heading."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


class Structure(unittest.TestCase):
    def test_every_module_loads_on_its_own(self):
        """Each one is imported in a fresh Python, so a circular import cannot hide behind what another import loaded first."""
        for name in MODULES:
            result = subprocess.run([sys.executable, "-c", f"import {name}"], cwd=HERE, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{name} failed to import:\n{result.stderr[-600:]}")

    def test_web_still_offers_the_pages(self):
        sys.path.insert(0, HERE)
        web = importlib.import_module("web")
        for page in ("spots_page", "conditions_page", "help_page", "main"):
            self.assertTrue(callable(getattr(web, page)), page)

    def test_the_name_and_the_branding_files_are_there(self):
        import ui_common
        self.assertEqual(ui_common.GITHUB_URL, "https://github.com/K5OHY/FarField-Lab")
        for name in ("farfield-icon-512.png", "farfield-favicon.png", "farfield-logo-dark.png", "farfield-logo-light.png", "farfield-sidebar-logo.png", "farfield-strip.png",
                     "farfield-banner.png"):
            self.assertTrue(os.path.exists(os.path.join(HERE, "images", "branding", name)), name)
        self.assertTrue(os.path.exists(os.path.join(HERE, "LICENSE")))
        with open(os.path.join(HERE, "README.md"), encoding="utf-8") as f:
            self.assertIn("# FarField Lab", f.read())

    def test_the_log_page_is_called_log_analysis_everywhere_a_visitor_reads_it(self):
        """The page was first called Log check; the name a visitor sees is Log analysis, and the address /log stays so shared links keep working."""
        for name in ("web.py", "README.md", "share_card.py", *docs_files()):
            with open(os.path.join(HERE, *name.split("/")), encoding="utf-8") as f:
                text = f.read()
            self.assertNotIn("Log check", text, name)
            self.assertNotIn("LOG CHECK", text, name)
        with open(os.path.join(HERE, "web.py"), encoding="utf-8") as f:
            web = f.read()
        self.assertIn('title="Log analysis"', web)
        self.assertIn('url_path="log"', web)

    def test_receivers_are_described_as_on_the_band_not_listening(self):
        """One word for the idea, everywhere a visitor reads it: a receiver that decoded something in your slots was 'on the band'."""
        for name in ("views/compare_view.py", "README.md", *docs_files()):
            with open(os.path.join(HERE, *name.split("/")), encoding="utf-8") as f:
                text = f.read()
            for phrase in ("were listening", "not listening", "Listening during", "listening during", "Who was listening"):
                self.assertNotIn(phrase, text, f"{name} still says {phrase!r}")

    def test_every_link_and_picture_in_the_readme_and_the_guides_points_at_something(self):
        """A moved guide changes what its relative links are relative to. Every file, picture and heading a link names has to be there."""
        for name in ("README.md", *docs_files()):
            path = os.path.join(HERE, *name.split("/"))
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for target in re.findall(r"\]\(([^)\s]+)\)", text):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                where, _, anchor = target.partition("#")
                other = os.path.normpath(os.path.join(os.path.dirname(path), where)) if where else path
                self.assertTrue(os.path.exists(other), f"{name}: {target} points at nothing")
                if anchor and other.endswith(".md"):
                    with open(other, encoding="utf-8") as g:
                        slugs = {slug(h) for h in re.findall(r"^#{1,6} (.+)$", g.read(), re.M)}
                    self.assertIn(anchor, slugs, f"{name}: {target} names a heading that is not there")

    def test_the_entry_point_stays_small(self):
        with open(os.path.join(HERE, "web.py"), encoding="utf-8") as f:
            self.assertLess(len(f.read().splitlines()), 60)


if __name__ == "__main__":
    unittest.main()
