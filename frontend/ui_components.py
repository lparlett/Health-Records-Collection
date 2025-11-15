# Purpose: Streamlit UI components.
# Author: Codex + Lauren
# Date: 2025-11-14
# Tests: test_ui_components.py
# AI-assisted: This module was created with AI assistance.
"""UI components for the health records collection Streamlit app."""

import streamlit as st

def sidebar_table_selector(tables: list[str]) -> list[str]:
    """Render a sidebar multiselect for choosing database tables."""
    st.sidebar.header("Select Tables")
    return st.sidebar.multiselect("Tables", tables)


def query_box() -> str:
    """Render a sidebar text area for entering a custom SQL query."""
    st.sidebar.header("Custom Query")
    return st.sidebar.text_area("Enter SQL query", "")
