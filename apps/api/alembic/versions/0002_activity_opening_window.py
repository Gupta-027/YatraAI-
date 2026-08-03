"""Record the opening window each visit was scheduled inside.

The solver already constrained every visit to a real opening interval; it simply
threw the interval away afterwards. Persisting it lets the itinerary show
"10:00-11:30, open 09:00-17:00", which a traveller can sanity-check, instead of a
bare visit time they have to take on trust.

Both columns are nullable, and that is meaningful rather than lazy: meals and rest
breaks have no opening window, and an attraction with no recorded hours must read
as "hours not recorded" rather than silently appearing to be open all day.

Revision ID: b1c7f0a94d22
Revises: ea4563174965
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c7f0a94d22"
down_revision: str | None = "ea4563174965"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("itinerary_activities", sa.Column("opens_min", sa.Integer(), nullable=True))
    op.add_column("itinerary_activities", sa.Column("closes_min", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("itinerary_activities", "closes_min")
    op.drop_column("itinerary_activities", "opens_min")
