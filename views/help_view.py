"""The Help and README page: a short start, then one tab for each part of the README, with the long explanations folded closed."""
import re
from pathlib import Path

import streamlit as st

from ui_common import CHOOSER, PAGES, brand_strip, github_url

# The README is split at its "## " headings. Each tab shows some of those sections. A section not listed here goes in the last tab, so
# nothing in the README is ever left out of the page.
TABS = [("Start here", ["Examples", "Sharing a view"]),
        ("My spots", ["Getting your spots", "The map"]),
        ("Compare antennas", ["Compare two antennas"]),
        ("Band conditions", ["Band conditions now"]),
        ("Log analysis", ["Log analysis"]),
        ("Troubleshooting", ["Troubleshooting"]),
        ("Deep dive and code", ["Deep dive (for the curious)", "Checked against a published study", "Run it locally", "Help inside the app",
                                "Files", "Data sources and thanks", "License"])]
NOT_HERE = {"What it looks like", "Quick start"}   # the screenshots are for GitHub; the quick start is drawn by the page itself, with links


def _fix(line):
    """A README line made to work in the app: links to the docs go to the repository, and a link to another part of the README (which
    would go nowhere from inside a tab) becomes plain text, since each part has its own tab."""
    line = line.replace("](docs/", f"]({github_url()}/blob/main/docs/")
    return re.sub(r"\[([^\]]+)\]\(#[^)]*\)", r"\1", line)


def _sections(text):
    """The README's level-2 sections as {title: [lines, heading first]}. Anything before the first one (the banner, the intro) is left out."""
    sections, current = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = sections.setdefault(line[3:].strip(), [])
        if current is not None:
            current.append(line)
    return sections


def _show(lines, root):
    """Draw README lines: text as markdown, a picture from the app's own folder, and a <details> block as a closed expander."""
    chunk = []

    def flush():
        if chunk:
            st.markdown("\n".join(chunk))
            chunk.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        picture = re.match(r"!\[(.*)\]\((images/[^)]+)\)\s*$", line)
        if picture:
            flush()
            st.image(str(root / picture.group(2)), caption=picture.group(1))
            continue
        if line.strip() == "<details>":  # a folded section: the first line inside is its <summary>
            end = next((k for k in range(i, len(lines)) if lines[k].strip() == "</details>"), len(lines))
            inside = lines[i:end]
            i = end + 1
            flush()
            title = re.sub(r"<[^>]+>", "", inside[0]).strip() if inside else "More"
            with st.expander(title):
                st.markdown("\n".join(_fix(l) for l in inside[1:]))
            continue
        chunk.append(_fix(line))
    flush()


def _start_here():
    """The quick start: the four things the app does, each a link to its page."""
    st.markdown("#### Quick start")
    st.markdown("Pick what you want to do. Each part has its own tab above, with the long explanations folded closed.")
    for row in (CHOOSER[:2], CHOOSER[2:]):
        for col, (key, title, blurb, icon) in zip(st.columns(2), row):
            with col, st.container(border=True):
                if key in PAGES:
                    st.page_link(PAGES[key], label=title, icon=icon)
                else:
                    st.markdown(f"**{title}**")
                st.caption(blurb)
    st.markdown("**Just looking?** My spots has a **Try an example** button, Band conditions has **Try an example location**, and Compare antennas opens with six "
                "real tests (listed below). **Stuck?** See the Troubleshooting tab. **Want the working?** See the Deep dive and code tab.")


def help_page():
    """The README, shown in the app, with the links to the code and to Dale's site."""
    brand_strip()
    st.title("Help and README")
    st.markdown(f"This is the project's README, the same one that is on [GitHub]({github_url()}#readme), where the code lives "
                "and where you can report a problem or suggest something. The long-test method (relative gain at each "
                "receiver, linear averaging and long alternating blocks) follows the work of "
                "[Dale, N3HXZ](https://www.n3hxz.net/), published on his site. The quick paired test is this app's own.")
    root = Path(__file__).resolve().parent.parent
    try:
        text = (root / "README.md").read_text(encoding="utf-8")
    except OSError:
        st.warning(f"The README file isn't here. It is on [GitHub]({github_url()}#readme).")
        return
    sections = {title: lines for title, lines in _sections(text).items() if title not in NOT_HERE}
    listed = {title for _, titles in TABS for title in titles}
    extra = [title for title in sections if title not in listed]          # a section added to the README later still shows up
    tabs = st.tabs([name for name, _ in TABS])
    for n, (tab, (name, titles)) in enumerate(zip(tabs, TABS)):
        with tab:
            if n == 0:
                _start_here()
            for title in titles + (extra if n == len(TABS) - 1 else []):
                if title in sections:
                    _show(sections[title], root)
