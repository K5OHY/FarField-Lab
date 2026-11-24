"""The Help page: pick a topic. Each topic starts with the page's own short guide, then the README's detail, with the long parts folded closed."""
import re
from pathlib import Path

import streamlit as st

from ui_common import CHOOSER, PAGES, brand_strip, github_url, show_guide

# Each topic: the page guide that opens it (if it has one) and the README "## " sections that follow. A README section not listed here goes
# in the last topic, so nothing in the README is ever left out of the page.
TOPICS = {
    "Start here": (None, ["Examples", "Sharing a view"]),
    "My spots": ("spots", ["Getting your spots", "The map"]),
    "Compare antennas": ("compare", ["Compare two antennas"]),
    "Band conditions": ("conditions", ["Band conditions now"]),
    "Log analysis": ("log", ["Log analysis"]),
    "Troubleshooting": (None, ["Troubleshooting"]),
    "About and methodology": (None, ["Deep dive (for the curious)", "Checked against a published study", "Run it locally", "Help inside the app",
                                     "Files", "Data sources and thanks", "License"]),
}
NOT_HERE = {"What it looks like", "Quick start"}   # the screenshots are for GitHub; the quick start is drawn by the page itself, with links
SEE_ALSO = {"My spots": ["Troubleshooting"], "Compare antennas": ["Troubleshooting", "About and methodology"],
            "Band conditions": ["Troubleshooting", "About and methodology"], "Log analysis": ["Troubleshooting"],
            "Start here": ["Troubleshooting"]}
BUTTONS = {"Troubleshooting": "Open troubleshooting", "About and methodology": "Methodology and calculations"}
DALE = ("The long-test method (relative gain at each receiver, linear averaging and long alternating blocks) follows the work of "
        "**[Dale, N3HXZ](https://www.n3hxz.net/)**, published on his site. The quick paired test is this app's own.")


def _slug(topic):
    return topic.lower().replace(" ", "-")


def _fix(line):
    """A README line made to work in the app: links to the docs go to the repository, and a link to another part of the README (which
    would go nowhere from inside a topic) becomes plain text. The 'See also' buttons carry the real navigation."""
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
    """Draw README lines: text as markdown, a picture from the app's own folder, and a <details> block as a closed expander. A block
    between <!-- help:skip --> and <!-- /help:skip --> is for GitHub only (this page draws the same thing from the page's own guide)."""
    chunk, skipping, i = [], False, 0

    def flush():
        if chunk:
            st.markdown("\n".join(chunk))
            chunk.clear()

    while i < len(lines):
        line = lines[i]
        i += 1
        if line.strip() == "<!-- help:skip -->":
            skipping = True
            continue
        if line.strip() == "<!-- /help:skip -->":
            skipping = False
            continue
        if skipping:
            continue
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
                _show(inside[1:], root)
            continue
        chunk.append(_fix(line))
    flush()


def _go(topic):
    """A 'See also' button: switch to another topic (and put it in the address, so the link can be shared)."""
    st.session_state["help_topic"] = topic
    st.query_params["topic"] = _slug(topic)


def _sync():
    topic = st.session_state.get("help_topic")
    if topic:
        st.query_params["topic"] = _slug(topic)


def _see_also(topic):
    names = SEE_ALSO.get(topic, [])
    if names:
        st.markdown("**See also**")
        for col, name in zip(st.columns(max(len(names), 3)), names):
            col.button(BUTTONS[name], key=f"see_{_slug(topic)}_{_slug(name)}", on_click=_go, args=(name,), width="stretch")


def _start_here():
    """The quick start: the four things the app does, each a link to its page."""
    st.markdown("#### Quick start")
    st.markdown("Pick what you want to do. The topics above explain each part, with the long explanations folded closed.")
    for row in (CHOOSER[:2], CHOOSER[2:]):
        for col, (key, title, blurb, icon, action) in zip(st.columns(2), row):
            with col, st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(blurb)
                if key in PAGES:
                    st.page_link(PAGES[key], label=action, icon=icon)
    st.markdown("**Just looking?** My spots has a **Try an example** button, Band conditions has **Try an example location**, and Compare antennas "
                "opens with six real tests (listed below).")


def _about(text):
    """What the project is, who it owes the method to, and where the code and the calculations are written down."""
    intro = next((l for l in text.splitlines() if l.startswith("See where your signal is heard")), "")
    st.markdown("#### About FarField Lab")
    if intro:
        st.markdown(_fix(intro))
    st.markdown(DALE)
    st.markdown(f"[Read the README on GitHub]({github_url()}#readme) · [Technical methodology]({github_url()}/blob/main/docs/METHODOLOGY.md) · "
                f"[Report a problem or suggest something]({github_url()}/issues)")


def help_page():
    """Help: choose a topic."""
    brand_strip()
    st.title("Help")
    root = Path(__file__).resolve().parent.parent
    try:
        text = (root / "README.md").read_text(encoding="utf-8")
    except OSError:
        st.warning(f"The README file isn't here. It is on [GitHub]({github_url()}#readme).")
        return
    ss = st.session_state
    if "help_topic" not in ss:                     # a shared link (?topic=troubleshooting) opens that topic
        by_slug = {_slug(t): t for t in TOPICS}
        ss["help_topic"] = by_slug.get(st.query_params.get("topic", ""), "Start here")
    st.caption("Choose a topic to get started or understand your results.")
    topic = st.segmented_control("Topic", list(TOPICS), key="help_topic", label_visibility="collapsed", on_change=_sync) or "Start here"

    guide, titles = TOPICS[topic]
    sections = {title: lines for title, lines in _sections(text).items() if title not in NOT_HERE}
    listed = {title for _, ts in TOPICS.values() for title in ts}
    if topic == list(TOPICS)[-1]:                  # a section added to the README later still shows up
        titles = titles + [title for title in sections if title not in listed]
    if topic == "Start here":
        _start_here()
    if topic == list(TOPICS)[-1]:
        _about(text)
    if guide:
        show_guide(guide)
    for title in titles:
        if title in sections:
            lines = sections[title]
            _show(lines[1:] if len(titles) == 1 and guide else lines, root)   # the topic's own name is the heading already
    _see_also(topic)
