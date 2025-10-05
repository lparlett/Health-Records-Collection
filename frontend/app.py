import streamlit as st
import db_utils
import views
import yaml
from pathlib import Path

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

# DB connection
conn = db_utils.get_connection()

# Encounter overview first
views.show_encounters(conn)
_divider()

# Show UI components
views.show_tables(conn)
_divider()
views.show_query(conn)

# Close DB
conn.close()
