"""add chat table

Revision ID: 13d0a53f1b6e
Revises: 39fe85b66b2d
Create Date: 2026-11-08 02:48:17.385764

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "13d0a53f1b6e"
down_revision: Union[str, Sequence[str], None] = "39fe85b66b2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chats",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "guest_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["tests.users.id"],
            name="fk_chats_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["guest_id"],
            ["tests.guests.id"],
            name="fk_chats_guest",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "(user_id IS NOT NULL AND guest_id IS NULL) OR "
            "(user_id IS NULL AND guest_id IS NOT NULL)",
            name="chat_has_one_owner",
        ),
        schema="tests",
    )

    # Пока nullable, чтобы не сломать /generate.
    op.add_column(
        "users_requests",
        sa.Column(
            "chat_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        schema="tests",
    )

    op.create_foreign_key(
        "fk_users_requests_chat",
        "users_requests",
        "chats",
        ["chat_id"],
        ["id"],
        source_schema="tests",
        referent_schema="tests",
        ondelete="CASCADE",
    )

    # Перенос существующих генераций.
    conn = op.get_bind()

    requests = (
        conn.execute(
            sa.text("""
            SELECT id, user_id, guest_id, created_at
            FROM tests.users_requests
            ORDER BY id
        """)
        )
        .mappings()
        .all()
    )

    for request in requests:
        chat_id = conn.execute(
            sa.text("""
                INSERT INTO tests.chats (
                    user_id,
                    guest_id,
                    created_at,
                    updated_at
                )
                VALUES (
                    :user_id,
                    :guest_id,
                    :created_at,
                    :created_at
                )
                RETURNING id
            """),
            {
                "user_id": request["user_id"],
                "guest_id": request["guest_id"],
                "created_at": request["created_at"],
            },
        ).scalar_one()

        conn.execute(
            sa.text("""
                UPDATE tests.users_requests
                SET chat_id = :chat_id
                WHERE id = :request_id
            """),
            {
                "chat_id": chat_id,
                "request_id": request["id"],
            },
        )

    # Индексы для sidebar.
    op.create_index(
        "ix_chats_user_updated",
        "chats",
        ["user_id", sa.text("updated_at DESC")],
        schema="tests",
    )

    op.create_index(
        "ix_chats_guest_updated",
        "chats",
        ["guest_id", sa.text("updated_at DESC")],
        schema="tests",
    )

    # История генераций конкретного чата.
    op.create_index(
        "ix_users_requests_chat_history",
        "users_requests",
        ["chat_id", "created_at", "id"],
        schema="tests",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_users_requests_chat_history",
        table_name="users_requests",
        schema="tests",
    )

    op.drop_constraint(
        "fk_users_requests_chat",
        "users_requests",
        type_="foreignkey",
        schema="tests",
    )

    op.drop_column(
        "users_requests",
        "chat_id",
        schema="tests",
    )

    op.drop_index(
        "ix_chats_guest_updated",
        table_name="chats",
        schema="tests",
    )

    op.drop_index(
        "ix_chats_user_updated",
        table_name="chats",
        schema="tests",
    )

    op.drop_table("chats", schema="tests")
