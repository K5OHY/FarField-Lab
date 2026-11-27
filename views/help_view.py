"""The Help page: pick a topic. Each topic starts with the page's own short guide, then the guide files in docs/ that belong to it, with the long parts folded closed."""
import re
from pathlib import Path

import streamlit as st

from ui_common import CHOOSER, PAGES, brand_strip, github_url, show_guide

# Each topic: the page guide that opens it (if it has one) and the docs/ files that follow. A docs/ file not listed here goes in the last topic, so
# nothing in docs/ is ever left out of the page (METHODOLOGY.md is the exception: it is long, and the About topic links to it).
TOPICS = {
    "Start here": (None, ["start-here.md"]),
    "My spots": ("spots", ["my-spots.md"]),
    "Compare antennas": ("compare", ["compare-antennas.md"]),
    "Band conditions": ("conditions", ["band-conditions.md"]),
    "Log analysis": ("log", ["log-analysis.md"]),
    "Troubleshooting": (None, ["troubleshooting.md"]),
    "About and methodology": (None, ["about.md", "developer.md"]),
}
LINKED_NOT_SHOWN = {"METHODOLOGY.md"}
SEE_ALSO = {"My spots": ["Troubleshooting"], "Compare antennas": ["Troubleshooting", "About and methodology"],
            "Band conditions": ["Troubleshooting", "About and methodology"], "Log analysis": ["Troubleshooting"],
            "Start here": ["Troubleshooting"]}
BUTTONS = {"Troubleshooting": "Open troubleshooting", "About and methodology": "Methodology and calculations"}
INTRO = ("See where your signal is heard, how strong it is, and how conditions change. Map the [Reverse Beacon Network](https://www.reversebeacon.net/) "
         "stations that spotted your CQ, or the [WSPR](https://wsprnet.org/) stations that heard your beacon. Compare which of two antennas, frequencies or "
         "power levels is getting out better, using real-world signal measurements. And check which bands are open and where you would be heard right now.")
DALE = ("The long-test method (relative gain at each receiver, linear averaging and long alternating blocks) follows the work of "
        "**[Dale, N3HXZ](https://www.n3hxz.net/)**, published on his site. The quick paired test is this app's own.")


def _slug(topic):
    return topic.lower().replace(" ", "-")


def _link(match):
    """One markdown link made to work inside the app. A link to the repository (`../collector/SETUP.md`) or to the methodology goes to GitHub. A link
    to another guide or to another part of the same one would go nowhere from inside a topic, so it becomes plain text: the 'See also' buttons
    carry the real navigation."""
    label, target = match.group(1), match.group(2)
    if target.startswith(("http://", "https://", "mailto:")):
        return match.group(0)
    if target.startswith("../"):
        return f"[{label}]({github_url()}/blob/main/{target[3:]})"
    if target.split("#")[0] in LINKED_NOT_SHOWN:
        return f"[{label}]({github_url()}/blob/main/docs/{target})"
    return label


def _fix(line):
    """A line of a docs/ file made to work in the app (see _link). Pictures are drawn separately and are left alone."""
    return re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]*)\)", _link, line)


def _topic_lines(docs, names):
    """The lines of a topic's files, each without its own '# ' title (the topic's name is the heading already). A file that is not there is skipped
    and reported by the page."""
    lines, missing = [], []
    for name in names:
        try:
            text = (docs / name).read_text(encoding="utf-8")
        except OSError:
            missing.append(name)
            continue
        body = text.splitlines()
        if body and body[0].startswith("# "):
            body = body[1:]
        lines += body
    return lines, missing


def _show(lines, root):
    """Draw lines from the docs/ files: text as markdown, a picture from the app's own folder, and a <details> block as a closed expander. A block
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
        picture = re.match(r"!\[(.*)\]\((?:\.\./)?(images/[^)]+)\)\s*$", line)
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
    st.markdown("**Just looking?** My spots has a **Try an example** button, and Compare antennas "
                "opens with six real tests (listed below).")


def _about():
    """What the project is, who it owes the method to, and where the code and the calculations are written down."""
    st.markdown("#### About FarField Lab")
    st.markdown(INTRO)
    st.markdown(DALE)
    st.markdown(f"[Read the README on GitHub]({github_url()}#readme) · [Technical methodology]({github_url()}/blob/main/docs/METHODOLOGY.md) · "
                f"[Report a problem or suggest something]({github_url()}/issues)")


def help_page():
    """Help: choose a topic."""
    brand_strip()
    st.title("Help")
    docs = Path(__file__).resolve().parent.parent / "docs"
    root = docs.parent
    ss = st.session_state
    if "help_topic" not in ss:                     # a shared link (?topic=troubleshooting) opens that topic
        by_slug = {_slug(t): t for t in TOPICS}
        ss["help_topic"] = by_slug.get(st.query_params.get("topic", ""), "Start here")
    st.caption("Choose a topic to get started or understand your results.")
    topic = st.segmented_control("Topic", list(TOPICS), key="help_topic", label_visibility="collapsed", on_change=_sync) or "Start here"

    guide, names = TOPICS[topic]
    last = topic == list(TOPICS)[-1]
    if last:                                       # a guide added to docs/ later still shows up
        listed = {name for _, ns in TOPICS.values() for name in ns} | LINKED_NOT_SHOWN
        names = names + sorted(p.name for p in docs.glob("*.md") if p.name not in listed)
    lines, missing = _topic_lines(docs, names)
    if missing:
        st.warning(f"Part of this topic isn't here ({', '.join(missing)}). The guides are on [GitHub]({github_url()}/tree/main/docs).")
    if topic == "Start here":
        _start_here()
    if last:
        _about()
    if guide:
        show_guide(guide)
    if guide and sum(1 for l in lines if l.startswith("## ")) == 1:   # the topic's own name is the heading already
        lines = [l for l in lines if not l.startswith("## ")]
    _show(lines, root)
    _see_also(topic)
