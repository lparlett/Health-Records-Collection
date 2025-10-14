import streamlit as st
import yaml
import logging
from pathlib import Path
from frontend import db_utils, views

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Log to console/streamlit
    ]
)

# Load config
CONFIG_PATH = Path(__file__).parent / "config.yaml"
with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.safe_load(f)


def _divider():
    if hasattr(st, "divider"):
        st.divider()
    else:
        st.markdown("---")


st.set_page_config(page_title=CONFIG["page_title"], layout=CONFIG["layout"])
st.title(CONFIG["page_title"])

conn = db_utils.get_connection()
try:
    show_overview = views.render_patient_encounter_experience(conn)
    if show_overview:
        _divider()
        views.show_tables(conn)
        _divider()
        views.show_query(conn)
finally:
    conn.close()
