"""Assign the Director access role to the two designated employee accounts.

Revision ID: 20260821_0025
Revises: 20260821_0024
"""

from __future__ import annotations

import re
import unicodedata
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260821_0025"
down_revision: Union[str, None] = "20260821_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DIRECTOR_NAMES = frozenset({"ton that trung kien", "to to van"})


def _normalize(value: str | None) -> str:
    plain = unicodedata.normalize("NFKD", value or "")
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", plain.casefold()).strip()


def _linked_director_user_ids(connection) -> list[int]:
    rows = connection.execute(
        sa.text(
            "SELECT e.full_name, e.user_id "
            "FROM employees e "
            "WHERE e.user_id IS NOT NULL"
        )
    ).mappings()
    return [
        int(row["user_id"])
        for row in rows
        if _normalize(row["full_name"]) in DIRECTOR_NAMES
    ]


def upgrade() -> None:
    connection = op.get_bind()
    for user_id in _linked_director_user_ids(connection):
        connection.execute(
            sa.text("UPDATE users SET role = :role WHERE id = :user_id"),
            {"role": "DIRECTOR", "user_id": user_id},
        )


def downgrade() -> None:
    connection = op.get_bind()
    for user_id in _linked_director_user_ids(connection):
        connection.execute(
            sa.text(
                "UPDATE users SET role = :role "
                "WHERE id = :user_id AND role = :director_role"
            ),
            {"role": "USER", "director_role": "DIRECTOR", "user_id": user_id},
        )
