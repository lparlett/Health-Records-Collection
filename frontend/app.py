# Purpose: Launch Streamlit UI with SQLCipher unlock workflow.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: manual (Streamlit runtime)
# AI-assisted: Module updated with AI assistance.
"""Streamlit entry point for the encrypted Health Records dashboard."""

from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st
import yaml

from frontend import db_utils, views
from security import sqlcipher_support

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

PASS_STATE_KEY = "db_passphrase"
ERROR_STATE_KEY = "db_passphrase_error"

# Load config
CONFIG_PATH = Path(__file__).parent / "config.yaml"
with open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
    CONFIG = yaml.safe_load(config_file)


def _divider() -> None:
    """Render a horizontal divider compatible with older Streamlit versions."""
    if hasattr(st, "divider"):
        st.divider()
    else:
        st.markdown("---")


def _initialise_session_state() -> None:
    """Ensure required Streamlit session keys exist."""
    if PASS_STATE_KEY not in st.session_state:
        st.session_state[PASS_STATE_KEY] = None
    if ERROR_STATE_KEY not in st.session_state:
        st.session_state[ERROR_STATE_KEY] = ""


def _render_unlock_form() -> None:
    """Prompt the user for the SQLCipher passphrase inside Streamlit."""
    st.info("Enter the SQLCipher passphrase to unlock the local database.")
    with st.form("unlock_database", clear_on_submit=False):
        passphrase = st.text_input(
            "Database passphrase",
            type="password",
            help="Required to establish or decrypt the encrypted SQLite database",
        )
        submitted = st.form_submit_button("Unlock")
    if submitted:
        if not passphrase or not passphrase.strip():
            st.session_state[ERROR_STATE_KEY] = "Passphrase cannot be empty."
            return
        try:
            conn = db_utils.get_connection(passphrase=passphrase)
        except RuntimeError:
            st.session_state[ERROR_STATE_KEY] = (
                "Invalid passphrase supplied. Please try again."
            )
        else:
            conn.close()
            st.session_state[PASS_STATE_KEY] = passphrase
            st.session_state[ERROR_STATE_KEY] = ""
            st.rerun()


def _offer_lock_button() -> None:
    """Provide a control for clearing the cached passphrase."""
    if st.sidebar.button("Lock database", use_container_width=True):
        st.session_state[PASS_STATE_KEY] = None
        st.session_state[ERROR_STATE_KEY] = ""
        sqlcipher_support.clear_cached_passphrase()
        st.rerun()


def main() -> None:
    """Entrypoint invoked by Streamlit."""
    st.set_page_config(
        page_title=CONFIG["page_title"], layout=CONFIG["layout"]
    )
    _initialise_session_state()

    if st.session_state[PASS_STATE_KEY] is None:
        st.title(CONFIG["page_title"])
        _render_unlock_form()
        if st.session_state[ERROR_STATE_KEY]:
            st.error(st.session_state[ERROR_STATE_KEY])
        st.stop()

    try:
        conn = db_utils.get_connection(
            passphrase=st.session_state[PASS_STATE_KEY]
        )
    except RuntimeError:
        st.session_state[PASS_STATE_KEY] = None
        st.session_state[ERROR_STATE_KEY] = (
            "Stored passphrase is no longer valid. Please re-enter it."
        )
        st.rerun()
        st.stop()

    try:
        st.title(CONFIG["page_title"])
        _offer_lock_button()
        show_overview = views.render_patient_encounter_experience(conn)
        if show_overview:
            _divider()
            views.show_tables(conn)
            _divider()
            views.show_query(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
