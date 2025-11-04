import streamlit as st


def sidebar_table_selector(tables: list[str]) -> list[str]:
    st.sidebar.header("Select Tables")
    return st.sidebar.multiselect("Tables", tables)


def query_box() -> str:
    st.sidebar.header("Custom Query")
    return st.sidebar.text_area("Enter SQL query", "")
