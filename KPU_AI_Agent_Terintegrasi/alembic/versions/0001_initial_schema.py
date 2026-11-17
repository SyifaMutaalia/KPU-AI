"""Initial anonymous sessions, conversations, chat messages and rate windows.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("anonymous_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("anonymous_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_conversations_session_id", "conversations", ["session_id"])
    op.create_table("messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_conversation_created", "messages", ["conversation_id", "created_at"])
    op.create_table("usage_windows",
        sa.Column("session_id", sa.String(64), sa.ForeignKey("anonymous_sessions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("minute", sa.Integer(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False))


def downgrade():
    op.drop_table("usage_windows")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_session_id", table_name="conversations")
    op.drop_table("conversations")
    op.drop_table("anonymous_sessions")
