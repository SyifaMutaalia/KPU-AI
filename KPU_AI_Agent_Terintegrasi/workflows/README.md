# n8n workflows (sanitized exports)

The repository does not contain the original WF1 ingestion export. Do not replace it with a guessed workflow: it depends on the existing source, review/approval nodes, Pinecone node, and configured index/namespace. The available files are:

- `wf1-success-callback.json`: a subworkflow helper to call after a Pinecone upsert is confirmed.
- `error-handler.json`: WF2 Error Trigger, redacted normalization, idempotent PostgreSQL persistence, and Telegram/email notification nodes.

Both exports are inactive and contain no credentials or provider tokens. Import each JSON file from the n8n editor. Assign credentials after import; placeholder credential IDs/names and recipient fields are not credentials.

## PostgreSQL and notifications

Create a PostgreSQL credential named `KPU Monitoring PostgreSQL` that connects to the FastAPI app database (host `postgres`, port `5432`, database/user/password from private `APP_DB_*` values). Do not use the n8n internal DB (`POSTGRES_DB`) or its superuser credential for application monitoring. Assign the app credential to **Persist Error in PostgreSQL**.

Create a Telegram credential named `KPU Monitoring Telegram` and set a real chat ID on **Notify Telegram**. Create an SMTP credential named `KPU Monitoring SMTP`, and set the verified sender and administrator recipient on **Notify Email**. Configure at least one notifier; disable the other unconfigured node. Notification provider failures do not erase the error log already committed by PostgreSQL.

The Code node stores only workflow/execution identifiers, node, a bounded redacted error message, and a small normalized detail object. It does not serialize full execution input, authorization headers, or secrets. Review your provider's retention and access controls.

## WF1 integration and credential

Create an n8n HTTP Header Auth credential named `KPU Ingestion Callback Header`, header name `X-Ingestion-Key`, and set its value to the same private `INGESTION_CALLBACK_SECRET` configured in the backend. Assign it to **Record ingestion status** in the callback helper.

Call the helper with a JSON object containing:

```json
{
  "workflow": "WF1",
  "execution_id": "n8n execution ID",
  "status": "processing",
  "document_id": "stable document identifier",
  "source_url": "source URL",
  "document_type": "document type",
  "document_number": "document number",
  "title": "document title",
  "year": 2026,
  "file_hash": "SHA-256 of the current file",
  "namespace": "the existing configured Pinecone namespace",
  "chunks_count": 0,
  "pasal_count": null,
  "pinecone_confirmed": false,
  "retry_error_id": null
}
```

Invoke it at start (or set processing through your existing DB node), then only after Pinecone's successful upsert response set `pinecone_confirmed=true`, include the actual counts, and call it again. The helper explicitly returns `processing` when confirmation is false; it never infers success from extraction/embedding. Do not change the current index, namespace, or Pasal chunking. Use the same `document_id`/execution ID for retries of callback delivery.

For a retry started from Admin Monitoring, pass the originating error row's `error_id` as `retry_error_id` and the newly queued n8n execution ID as `execution_id`. This lets the backend mark the original error `retry_succeeded` only after a Pinecone-confirmed success callback. If the retry execution fails and triggers WF2, WF2 marks the original retry `retry_failed` using the execution ID returned by the retry webhook.

## Error trigger assignment and limitations

1. Import and configure `error-handler.json`, save, and activate it.
2. Open **WF1 → Settings → Error Workflow**, select **KPU WF2 - Error Handler**, and save WF1.
3. Keep WF2 unassigned to itself to avoid recursive error handling.
4. Test with a trigger/schedule execution in staging and verify the DB row and at least one notification.

n8n Error Trigger does not fire for a workflow run manually started from the editor. It also may not fire when a node uses `Continue On Fail`, a node error output is connected/handled, or a workflow catches and consumes the error. Route known handled failures explicitly to logging/notification. Do not rely on WF2 for manual executions or failures already swallowed by a node.

## Safe retry configuration

The repository has no WF1 source to infer a restart point or retry semantics. The API therefore requires an operator-configured **dedicated authenticated retry webhook**; it is disabled until `ADMIN_RETRY_WEBHOOK_URL` and `ADMIN_RETRY_WEBHOOK_SECRET` are set privately. Configure the WF1 webhook to validate `X-Admin-Retry-Secret`, persist/check `Idempotency-Key`, execute the approved ingestion path, and return `{"accepted": true, "execution_id": "..."}` only after n8n has queued the execution. Keep upsert IDs deterministic and handle unchanged `file_hash` idempotently. Never expose the webhook publicly without authentication.

The API records `retry_requested` before dispatch. If the HTTP request times out, it leaves the request locked because dispatch may already have occurred. Inspect n8n before operator intervention; the UI's accepted state is not a Pinecone or workflow success confirmation.
