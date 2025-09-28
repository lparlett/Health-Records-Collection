import streamlit as st
import db_utils
import ui_components

def show_tables(conn):
    tables = db_utils.list_tables(conn)
    selected_tables = ui_components.sidebar_table_selector(tables)

    if not selected_tables:
        st.info("👈 Select tables from the sidebar to display")
    else:
        for table in selected_tables:
            st.subheader(f"Table: {table}")
            df = db_utils.get_table_preview(conn, table)
            st.dataframe(df, use_container_width=True)

def show_query(conn):
    sql = ui_components.query_box()
    if sql.strip():
        try:
            df = db_utils.run_query(conn, sql)
            st.subheader("Query Results")
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")
