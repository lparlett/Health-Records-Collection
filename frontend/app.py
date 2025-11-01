# Purpose: Launch Streamlit UI with SQLCipher unlock workflow.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: manual (Streamlit runtime)
# AI-assisted: Module updated with AI assistance.
"""Streamlit entry point for the encrypted Health Records dashboard."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Literal, Mapping, cast

import streamlit as st  # type: ignore
import yaml  # type: ignore

from health_records_collection.frontend import db_utils, views
from health_records_collection.security import sqlcipher_support

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

DEFAULT_CONFIG: Final[Mapping[str, str]] = {
    "page_title": "Health Records Dashboard",
    "layout": "wide",
}
SECRET_STATE_KEY: Final[str] = "session_secret"
ERROR_STATE_KEY: Final[str] = "credential_error"

CONFIG_PATH = Path(__file__).parent / "config.yaml"


@lru_cache(maxsize=1)
def _load_config() -> Mapping[str, Any]:
    """Return Streamlit configuration merged with defaults."""
    config: Mapping[str, Any] = DEFAULT_CONFIG
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                loaded = yaml.safe_load(handle)
        except (OSError, yaml.YAMLError) as exc:  # type: ignore[attr-defined]
            logging.warning("Failed to read %s: %s", CONFIG_PATH, exc)
        else:
            if isinstance(loaded, dict):
                config = {**DEFAULT_CONFIG, **loaded}
            else:
                logging.warning("Config at %s is not a mapping; using defaults.", CONFIG_PATH)
    return config


def _divider() -> None:
    """Render a horizontal divider compatible with older Streamlit versions."""
    if hasattr(st, "divider"):
        st.divider()
    else:
        st.markdown("---")


def _initialise_session_state() -> None:
    """Ensure required Streamlit session keys exist."""
    if SECRET_STATE_KEY not in st.session_state:
        st.session_state[SECRET_STATE_KEY] = None
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
            st.session_state[SECRET_STATE_KEY] = passphrase
            st.session_state[ERROR_STATE_KEY] = ""
            st.rerun()


def _offer_lock_button() -> None:
    """Provide a control for clearing the cached passphrase."""
    if st.sidebar.button("Lock database", use_container_width=True):
        st.session_state[SECRET_STATE_KEY] = None
        st.session_state[ERROR_STATE_KEY] = ""
        sqlcipher_support.clear_cached_passphrase()
        st.rerun()


def main() -> None:
    """Entrypoint invoked by Streamlit."""
    config = _load_config()
    page_title = str(config.get("page_title", DEFAULT_CONFIG["page_title"]))
    layout_setting = str(config.get("layout", DEFAULT_CONFIG["layout"])).lower()
    layout: Literal["centered", "wide"] = "wide"
    if layout_setting in {"centered", "wide"}:
        layout = cast(Literal["centered", "wide"], layout_setting)

    st.set_page_config(page_title=page_title, layout=layout)
    _initialise_session_state()

    if st.session_state[SECRET_STATE_KEY] is None:
        st.title(page_title)
        _render_unlock_form()
        if st.session_state[ERROR_STATE_KEY]:
            st.error(st.session_state[ERROR_STATE_KEY])
        st.stop()

    conn: Any | None = None
    try:
        conn = db_utils.get_connection(passphrase=st.session_state[SECRET_STATE_KEY])
    except RuntimeError:
        st.session_state[SECRET_STATE_KEY] = None
        st.session_state[ERROR_STATE_KEY] = (
            "Stored passphrase is no longer valid. Please re-enter it."
        )
        st.rerun()
    else:
        st.title(page_title)
        _offer_lock_button()
        show_overview = views.render_patient_encounter_experience(conn)
        if show_overview:
            _divider()
            views.show_tables(conn)
            _divider()
            views.show_query(conn)
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
