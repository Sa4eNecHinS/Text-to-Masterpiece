"""limit prompt length

Revision ID: fbc2910f5ec1
Revises: 8eb105468065
Create Date: 2026-11-06 17:12:06.582802

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fbc2910f5ec1"
down_revision: Union[str, Sequence[str], None] = "8eb105468065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_users_requests_prompt_length",
        "users_requests",
        "char_length(prompt) <= 2000",
        schema="tests",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_users_requests_prompt_length",
        "users_requests",
        type_="check",
        schema="tests",
    )
