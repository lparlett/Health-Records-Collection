"""Unit tests for frontend.ui_components."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from health_records_collection.frontend import ui_components


class SidebarStub:
    """Provide a stubbed Streamlit sidebar with capturable methods."""

    def __init__(self) -> None:
        self.headers: list[str] = []
        self.multiselect_args: tuple[str, list[str]] | None = None
        self.text_area_args: tuple[str, str] | None = None
        self.multiselect_result: list[str] = []
        self.text_area_result = ""

    def header(self, text: str) -> None:
        self.headers.append(text)

    def multiselect(self, label: str, options: list[str]) -> list[str]:
        self.multiselect_args = (label, options)
        return self.multiselect_result

    def text_area(self, label: str, value: str) -> str:
        self.text_area_args = (label, value)
        return self.text_area_result


class TestUIComponents(unittest.TestCase):
    """Unit tests for the Streamlit UI helper functions."""

    def setUp(self) -> None:
        self.sidebar = SidebarStub()
        self.patcher = patch(
            "health_records_collection.frontend.ui_components.st", autospec=True
        )
        self.mock_streamlit = self.patcher.start()
        self.mock_streamlit.sidebar = self.sidebar

    def tearDown(self) -> None:
        self.patcher.stop()

    def test_sidebar_table_selector(self) -> None:
        """sidebar_table_selector should configure the sidebar and return the result."""
        self.sidebar.multiselect_result = ["condition", "encounter"]

        result = ui_components.sidebar_table_selector(
            ["condition", "encounter", "vital"]
        )

        self.assertEqual(self.sidebar.headers, ["Select Tables"])
        self.assertEqual(
            self.sidebar.multiselect_args,
            ("Tables", ["condition", "encounter", "vital"]),
        )
        self.assertEqual(result, ["condition", "encounter"])

    def test_query_box(self) -> None:
        """query_box should render headers and return text_area value."""
        self.sidebar.text_area_result = "SELECT * FROM condition;"

        result = ui_components.query_box()

        self.assertEqual(self.sidebar.headers, ["Custom Query"])
        self.assertEqual(self.sidebar.text_area_args, ("Enter SQL query", ""))
        self.assertEqual(result, "SELECT * FROM condition;")


if __name__ == "__main__":  # pragma: no cover - direct invocation
    unittest.main()
