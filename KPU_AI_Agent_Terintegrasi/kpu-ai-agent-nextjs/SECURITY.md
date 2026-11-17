# Security baseline — KPU AI Agent frontend

This is a starter, not a security-certified production system. A frontend cannot be made secret by disabling F12; assume all browser-delivered JavaScript and all browser requests are inspectable.

## Must complete before public deployment
- Implement authentication and authorization on the server for every protected endpoint; never trust client-side route guards.
- Use server-managed sessions in `HttpOnly; Secure; SameSite=Lax/Strict` cookies; rotate session IDs; expire sessions; add CSRF/origin protection to state-changing routes.
- Store passwords using Argon2id (or a vetted password-hashing service); use email verification, reset tokens that are random, short-lived, single-use, and stored hashed; rate-limit login/register/reset.
- Enforce per-user authorization for every conversation/document operation; use parameterized queries and tenant/user scoping in PostgreSQL.
- Keep `FASTAPI_BASE_URL`, model-provider API keys, database URLs, Pinecone keys, signing keys, and admin credentials server-only. Never use `NEXT_PUBLIC_` for secrets. Never commit `.env`.
- Do not expose stack traces, prompts, internal URLs, provider errors, secrets, or sensitive records in API responses. Redact secrets and personal data from logs.
- Apply CSP, HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, a restrictive `Permissions-Policy`, frame protection, and secure cookie settings at app/hosting level. Test CSP against required scripts.
- Apply per-user/IP rate limits, request size limits, schema validation, timeouts, concurrency limits, and abuse monitoring to all API routes.
- Treat retrieved documents and user prompts as untrusted input. Defend against prompt injection; keep tool allowlists and validate every tool argument server-side. Retrieval is not authorization.
- Validate uploads by extension, MIME and magic bytes; cap size; scan for malware; store outside executable web roots; process in an isolated worker.
- Protect n8n with private access, strong auth, least privilege, secret store, audit logs, and no public unauthenticated webhooks. Restrict scheduler tools to administrators.
- Add automated dependency scanning, SAST, DAST, secret scanning, backups, restore tests, incident response, and independent penetration testing.
- For voice: request microphone permission explicitly; disclose audio processing/storage; do not persist raw audio by default.

## Current limitations
- `/api/chat` is a proxy skeleton and does not implement user authentication, persistent history, RAG, LangChain, or tool authorization.
- Register/login/reset pages and database schema are not yet implemented. UI routes are placeholders to build next.
- Voice, document upload, library indexing, and scheduled tasks require secure backend integrations.
- Do not describe this code as “without vulnerabilities”; security requires implementation, configuration, testing, and ongoing maintenance.
