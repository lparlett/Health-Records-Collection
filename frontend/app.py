import streamlit as st
import db_utils
import views
import yaml
from pathlib import Path

# Load config
CONFIG_PATH = Path(__file__).parent / "config.yaml"
with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.safe_load(f)

st.set_page_config(page_title=CONFIG["page_title"], layout=CONFIG["layout"])
st.title(CONFIG["page_title"])

# DB connection
conn = db_utils.get_connection()

# Show UI components
views.show_tables(conn)
views.show_query(conn)

# Close DB
conn.close()
