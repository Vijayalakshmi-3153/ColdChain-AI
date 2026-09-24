"""add shipment packaging image path and cached CNN result

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shipments", sa.Column("packaging_image_path", sa.String(length=500), nullable=True))
    op.add_column("shipments", sa.Column("packaging_result", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("shipments", "packaging_result")
    op.drop_column("shipments", "packaging_image_path")
