"""The app: page setup and navigation. Each page lives in views/."""
import streamlit as st

from pathlib import Path

from ui_common import CSS, github_url
from views.compare_page import compare_page
from views.conditions_view import conditions_page
from views.help_view import help_page
from views.spots_view import spots_page


BRAND = Path(__file__).resolve().parent / "images" / "branding"


def main():
    favicon = BRAND / "farfield-favicon.png"
    st.set_page_config(layout="wide", page_title="FarField Lab", page_icon=str(favicon) if favicon.exists() else "\U0001F4E1")
    if (BRAND / "farfield-icon-512.png").exists():
        st.logo(str(BRAND / "farfield-icon-512.png"), size="large")
    st.markdown(CSS, unsafe_allow_html=True)
    pages = [st.Page(spots_page, title="My spots", icon=":material/cell_tower:", url_path="spots", default=True),
             st.Page(compare_page, title="Compare antennas", icon=":material/balance:", url_path="compare"),
             st.Page(conditions_page, title="Band conditions", icon=":material/public:", url_path="conditions"),
             st.Page(help_page, title="Help and README", icon=":material/help:", url_path="help")]
    st.navigation(pages).run()
    st.sidebar.divider()
    st.sidebar.caption(f"Built by Tim, K5OHY \u00b7 [README and code on GitHub]({github_url()}#readme) \u00b7 long-test method by "
                       "[Dale, N3HXZ](https://www.n3hxz.net/)")


if __name__ == "__main__":
    main()
