from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IngestionDocument, IngestionRun, utcnow


def record_ingestion_success(
    db: Session,
    *,
    document_id: str,
    source_url: str,
    document_type: str | None,
    document_number: str | None,
    title: str,
    year: int | None,
    file_hash: str,
    namespace: str,
    chunks_count: int,
    pasal_count: int | None,
    execution_id: str,
    workflow: str = "manual-ingest",
) -> None:
    now = utcnow()
    document = db.get(IngestionDocument, document_id)
    if not document:
        document = IngestionDocument(id=document_id, source_url=source_url)
        db.add(document)
    document.source_url = source_url
    document.document_type = document_type
    document.document_number = document_number
    document.title = title
    document.year = year
    document.file_hash = file_hash
    document.status = "success"
    document.namespace = namespace
    document.last_processed_at = now
    document.chunks_count = chunks_count
    document.pasal_count = pasal_count
    document.pinecone_confirmed = True
    document.updated_at = now
    run = db.scalar(
        select(IngestionRun).where(
            IngestionRun.workflow == workflow,
            IngestionRun.execution_id == execution_id,
        )
    )
    if not run:
        run = IngestionRun(
            workflow=workflow,
            execution_id=execution_id,
            document_id=document_id,
            status="success",
            started_at=now,
            completed_at=now,
            chunks_count=chunks_count,
            pasal_count=pasal_count,
            namespace=namespace,
        )
        db.add(run)
    else:
        run.document_id = document_id
        run.status = "success"
        run.completed_at = now
        run.chunks_count = chunks_count
        run.pasal_count = pasal_count
        run.namespace = namespace
    db.commit()
