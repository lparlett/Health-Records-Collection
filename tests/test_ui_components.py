"""Unit tests for frontend.ui_components."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from health_records_collection.frontend import ui_components


@pytest.fixture
def sidebar_stub() -> SimpleNamespace:
    """Provide a stubbed Streamlit sidebar with capturable methods."""

    class SidebarStub:
        def __init__(self) -> None:
            self.headers: list[str] = []
            self.multiselect_args: tuple[str, list[str]] | None = None
            self.text_area_args: tuple[str, str] | None = None
            self._multiselect_result: list[str] = []
            self._text_area_result = ""

        def header(self, text: str) -> None:
            self.headers.append(text)

        def multiselect(self, label: str, options: list[str]) -> list[str]:
            self.multiselect_args = (label, options)
            return self._multiselect_result

        def text_area(self, label: str, value: str) -> str:
            self.text_area_args = (label, value)
            return self._text_area_result

    return SidebarStub()


def test_sidebar_table_selector(monkeypatch: pytest.MonkeyPatch, sidebar_stub: SimpleNamespace) -> None:
    """sidebar_table_selector should configure the sidebar and return the widget result."""
    sidebar_stub._multiselect_result = ["condition", "encounter"]
    monkeypatch.setattr(ui_components.st, "sidebar", sidebar_stub)

    result = ui_components.sidebar_table_selector(["condition", "encounter", "vital"])

    assert sidebar_stub.headers == ["Select Tables"]
    assert sidebar_stub.multiselect_args == ("Tables", ["condition", "encounter", "vital"])
    assert result == ["condition", "encounter"]


def test_query_box(monkeypatch: pytest.MonkeyPatch, sidebar_stub: SimpleNamespace) -> None:
    """query_box should render headers and return text_area value."""
    sidebar_stub._text_area_result = "SELECT * FROM condition;"
    monkeypatch.setattr(ui_components.st, "sidebar", sidebar_stub)

    result = ui_components.query_box()

    assert sidebar_stub.headers == ["Custom Query"]
    assert sidebar_stub.text_area_args == ("Enter SQL query", "")
    assert result == "SELECT * FROM condition;"
