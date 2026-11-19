"""Additive admin and ingestion monitoring tables.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa

from alembic import op
from app.db.models import Base

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE SCHEMA IF NOT EXISTS admin")
        op.execute("CREATE SCHEMA IF NOT EXISTS ingestion")
    elif bind.dialect.name == "sqlite":
        databases = list(bind.exec_driver_sql("PRAGMA database_list"))
        attached = {row[1] for row in databases}
        main_path = next((row[2] for row in databases if row[1] == "main"), "")
        if main_path:
            from pathlib import Path

            root = Path(main_path)
            admin_path = str(
                root.with_name(root.stem + ".admin" + root.suffix)
            ).replace("'", "''")
            ingestion_path = str(
                root.with_name(root.stem + ".ingestion" + root.suffix)
            ).replace("'", "''")
        else:
            admin_path = ingestion_path = ":memory:"
        if "admin" not in attached:
            op.execute(f"ATTACH DATABASE '{admin_path}' AS admin")
        if "ingestion" not in attached:
            op.execute(f"ATTACH DATABASE '{ingestion_path}' AS ingestion")

    tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.schema in ("admin", "ingestion")
    ]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)

    inspector = sa.inspect(bind)
    if not inspector.has_table("documents", schema="ingestion"):
        return

    expected_columns = {
        "id": sa.String(128),
        "source_url": sa.Text(),
        "document_type": sa.String(120),
        "document_number": sa.String(120),
        "title": sa.Text(),
        "year": sa.Integer(),
        "file_hash": sa.String(128),
        "status": sa.String(32),
        "namespace": sa.String(255),
        "last_processed_at": sa.DateTime(timezone=True),
        "chunks_count": sa.Integer(),
        "pasal_count": sa.Integer(),
        "pinecone_confirmed": sa.Boolean(),
        "created_at": sa.DateTime(timezone=True),
        "updated_at": sa.DateTime(timezone=True),
    }
    known = {
        column["name"]
        for column in inspector.get_columns("documents", schema="ingestion")
    }
    for name, column_type in expected_columns.items():
        if name not in known:
            op.add_column(
                "documents",
                sa.Column(name, column_type, nullable=True),
                schema="ingestion",
            )

    if "id" not in known:
        if bind.dialect.name == "postgresql":
            op.execute(
                "UPDATE ingestion.documents SET id = md5(random()::text || clock_timestamp()::text) WHERE id IS NULL"
            )
        elif bind.dialect.name == "sqlite":
            op.execute(
                "UPDATE ingestion.documents SET id = lower(hex(randomblob(16))) WHERE id IS NULL"
            )
    if bind.dialect.name == "postgresql":
        op.execute(
            "UPDATE ingestion.documents SET source_url = '' WHERE source_url IS NULL"
        )
        op.execute(
            "UPDATE ingestion.documents SET status = 'pending' WHERE status IS NULL"
        )
        op.execute(
            "UPDATE ingestion.documents SET pinecone_confirmed = false WHERE pinecone_confirmed IS NULL"
        )
        op.execute(
            "UPDATE ingestion.documents SET created_at = now() WHERE created_at IS NULL"
        )
        op.execute(
            "UPDATE ingestion.documents SET updated_at = now() WHERE updated_at IS NULL"
        )
    elif bind.dialect.name == "sqlite":
        op.execute(
            "UPDATE ingestion.documents SET source_url = '' WHERE source_url IS NULL"
        )
        op.execute(
            "UPDATE ingestion.documents SET status = 'pending' WHERE status IS NULL"
        )
        op.execute(
            "UPDATE ingestion.documents SET pinecone_confirmed = 0 WHERE pinecone_confirmed IS NULL"
        )
        op.execute(
            "UPDATE ingestion.documents SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
        )
        op.execute(
            "UPDATE ingestion.documents SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"
        )


def downgrade():
    # Monitoring/auth tables may contain durable operational data; intentionally retain them.
    pass
