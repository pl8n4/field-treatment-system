import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st

from data_layer.work_orders import init_db
from ui import pages, shell
from ui import state as session

st.set_page_config(
    page_title="AgriFlow AI",
    page_icon=":material/agriculture:",
    layout="wide",
)

init_db()
session.bootstrap()

shell.render_identity()

navigation = st.navigation(
    [
        st.Page(
            pages.review_page,
            title="Treatment review",
            icon=":material/gavel:",
            url_path="review",
            default=True,
        ),
        st.Page(
            pages.queue_page,
            title="Work orders",
            icon=":material/assignment:",
            url_path="work-orders",
        ),
    ]
)

shell.render_session_panel()
navigation.run()
