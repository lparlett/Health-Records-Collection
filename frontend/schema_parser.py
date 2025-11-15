"""Schema.sql parsing utilities for extracting table and relationship metadata."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ForeignKey:
    """Foreign key relationship extracted from schema.sql."""

    column: str
    target_table: str
    target_column: str


@dataclass(frozen=True)
class TableDefinition:
    """Table metadata parsed from schema.sql."""

    name: str
    columns: tuple[str, ...]
    foreign_keys: tuple[ForeignKey, ...]


# pylint: disable=too-few-public-methods
class SchemaParser:
    """Parse schema.sql into structured table and relationship metadata."""

    def __init__(self, schema_path: Path) -> None:
        """Initialize parser with path to schema file.

        Args:
            schema_path: Path to schema.sql file.

        Raises:
            FileNotFoundError: If schema file does not exist.
        """
        if not schema_path.exists():
            raise FileNotFoundError(f"schema.sql not found at {schema_path}")
        self.schema_path = schema_path

    @staticmethod
    def _normalize_column_line(raw_line: str) -> str:
        """Return a cleaned column definition for display.

        Args:
            raw_line: Raw column definition from schema.

        Returns:
            Normalized column definition with abbreviations.
        """
        stripped = raw_line.strip().rstrip(",")
        if stripped.upper().startswith("PRIMARY KEY"):
            return stripped
        collapsed = " ".join(stripped.split())
        collapsed = re.sub(r"\bPRIMARY\s+KEY\b", "PK", collapsed, flags=re.IGNORECASE)
        collapsed = re.sub(r"\bAUTOINCREMENT\b", "AUTO", collapsed, flags=re.IGNORECASE)
        collapsed = re.sub(r"\bINTEGER\b", "INT", collapsed, flags=re.IGNORECASE)
        collapsed = re.sub(r"\bNOT\s+NULL\b", "NN", collapsed, flags=re.IGNORECASE)
        collapsed = re.sub(
            r"\bDEFAULT\s+([^\s]+)\b", r"DEF \1", collapsed, flags=re.IGNORECASE
        )
        return collapsed

    @staticmethod
    def _parse_foreign_key(raw_line: str) -> Optional[ForeignKey]:
        """Parse a foreign key constraint line into a ForeignKey object.

        Args:
            raw_line: Raw foreign key constraint line.

        Returns:
            ForeignKey object or None if line is not a valid foreign key.
        """
        stripped = raw_line.strip().rstrip(",")
        upper = stripped.upper()
        if not upper.startswith("FOREIGN KEY"):
            return None
        try:
            before_ref, after_ref = stripped.split("REFERENCES", maxsplit=1)
        except ValueError:
            return None

        column_part_start = before_ref.find("(")
        column_part_end = before_ref.find(")", column_part_start)
        target_part_start = after_ref.find("(")
        target_part_end = after_ref.find(")", target_part_start)

        if (
            column_part_start == -1
            or column_part_end == -1
            or target_part_start == -1
            or target_part_end == -1
        ):
            return None

        column_name = before_ref[column_part_start + 1 : column_part_end].strip()
        target_table = after_ref[:target_part_start].strip().split()[0]
        target_column = after_ref[target_part_start + 1 : target_part_end].strip()

        return ForeignKey(
            column=column_name,
            target_table=target_table,
            target_column=target_column,
        )

    def _parse_table_body(
        self, lines: list[str], start_idx: int
    ) -> tuple[list[str], list[ForeignKey], int]:
        """Parse columns and foreign keys from table definition.

        Args:
            lines: All schema lines.
            start_idx: Index of line after CREATE TABLE statement.

        Returns:
            Tuple of (column_list, foreign_key_list, end_index).
        """
        columns: list[str] = []
        foreign_keys: list[ForeignKey] = []

        for idx in range(start_idx, len(lines)):
            stripped = lines[idx].strip()
            upper = stripped.upper()

            # End of table definition
            if stripped.startswith(")"):
                return columns, foreign_keys, idx

            # Skip empty lines and comments
            if not stripped or upper.startswith("--"):
                continue

            # Skip CONSTRAINT lines (not foreign keys)
            if upper.startswith("CONSTRAINT"):
                continue

            # Parse foreign key
            fk = self._parse_foreign_key(stripped)
            if fk is not None:
                foreign_keys.append(fk)
                continue

            # Add column definition
            if upper.startswith("PRIMARY KEY") or upper.startswith("UNIQUE"):
                columns.append(self._normalize_column_line(stripped))
            else:
                columns.append(self._normalize_column_line(stripped))

        return columns, foreign_keys, len(lines)

    def _parse_create_table_line(self, line: str) -> Optional[str]:
        """Extract table name from CREATE TABLE statement.

        Args:
            line: CREATE TABLE statement line.

        Returns:
            Table name or None if not a valid CREATE TABLE.
        """
        match = re.match(
            r"CREATE TABLE(?: IF NOT EXISTS)?\s+([A-Za-z_][A-Za-z0-9_]*)",
            line,
            flags=re.IGNORECASE,
        )
        return match.group(1) if match else None

    @lru_cache(maxsize=1)
    def parse(self) -> tuple[TableDefinition, ...]:
        """Parse schema.sql into table and foreign key metadata.

        Returns:
            Tuple of TableDefinition objects.

        Raises:
            FileNotFoundError: If schema file not found during read.
        """
        if not self.schema_path.exists():
            raise FileNotFoundError(f"schema.sql not found at {self.schema_path}")

        tables: list[TableDefinition] = []
        lines = self.schema_path.read_text(encoding="utf-8").splitlines()

        idx = 0
        while idx < len(lines):
            line = lines[idx].strip()
            upper = line.upper()

            # Look for CREATE TABLE statement
            if upper.startswith("CREATE TABLE"):
                table_name = self._parse_create_table_line(line)
                if table_name:
                    columns, foreign_keys, end_idx = self._parse_table_body(
                        lines, idx + 1
                    )
                    tables.append(
                        TableDefinition(
                            name=table_name,
                            columns=tuple(columns),
                            foreign_keys=tuple(foreign_keys),
                        )
                    )
                    idx = end_idx + 1
                    continue

            idx += 1

        logger.debug("Parsed %d tables from schema", len(tables))
        return tuple(tables)
