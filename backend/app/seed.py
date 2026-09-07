"""Optional demo corpus, ingested into a demo account.

Not run at startup (every account starts empty). Use it to populate a
throwaway login for screenshots / local play:

    python -m app.seed --user demo --password demopass1
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.core.database import db_session
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.orm import Document, User
from app.services.ingestion import ingest_content

logger = get_logger(__name__)

SEED_DOCUMENTS: list[dict] = [
    {
        "title": "Remote Work & Equipment Policy",
        "category": "policy",
        "source_type": "policy",
        "content": """# Remote Work & Equipment Policy

## Eligibility
All full-time employees who have completed their 90-day onboarding period are
eligible to work remotely up to five days per week. Contractors are eligible for
hybrid arrangements only, with a minimum of two on-site days per week.

## Equipment
The company provides one laptop, one external monitor, a keyboard and a mouse to
every remote employee. Employees may expense up to $500 for a desk and chair in
their first year and up to $200 per year thereafter for peripherals. All hardware
purchases above $500 require manager approval before the expense is submitted.

## Security requirements
Remote employees must use the company VPN when accessing internal systems, enable
full-disk encryption, and keep operating systems patched within 14 days of a
release. Personal devices may access email and calendar only, never source code
or customer data.

## Reimbursement
Home internet is reimbursed at a flat $50 per month. Co-working space membership
is reimbursed up to $300 per month with prior approval from the employee's
manager and the Finance team.

## Exceptions
Exceptions to this policy are approved by the People Operations team and must be
documented in the HR system. Team-wide exceptions require VP approval.
""",
    },
    {
        "title": "Master Services Agreement — Acme Corp",
        "category": "contract",
        "source_type": "contract",
        "content": """# Master Services Agreement — Acme Corp

## 1. Term
This Agreement begins on 1 March 2026 and continues for an initial term of
twenty-four (24) months. It renews automatically for successive twelve (12) month
terms unless either party gives written notice of non-renewal at least sixty (60)
days before the end of the then-current term.

## 2. Fees and payment
Acme Corp will pay a subscription fee of $18,000 per month, invoiced quarterly in
advance. Payment is due net 30 from the invoice date. Late payments accrue
interest at 1.0% per month.

## 3. Service levels
The Provider guarantees 99.9% monthly uptime for the production API. If uptime
falls below 99.9% in a calendar month, Acme Corp is entitled to a service credit
of 10% of that month's fee; below 99.0%, a 25% credit. Service credits are the
sole remedy for availability failures.

## 4. Data protection
The Provider processes Acme Corp data only to deliver the services. Sub-processors
must be disclosed with thirty (30) days notice. All data is deleted or returned
within thirty (30) days of termination.

## 5. Limitation of liability
Except for breaches of confidentiality or data protection obligations, each
party's aggregate liability is capped at the fees paid in the twelve (12) months
preceding the claim.

## 6. Termination for cause
Either party may terminate for a material breach that remains uncured thirty (30)
days after written notice.
""",
    },
    {
        "title": "Retrieval Service — Architecture & Operations",
        "category": "tech-doc",
        "source_type": "tech-doc",
        "content": """# Retrieval Service — Architecture & Operations

## Overview
The retrieval service answers natural-language questions over the enterprise
knowledge base. It combines dense vector search (pgvector, HNSW index) with
sparse keyword search (PostgreSQL full-text) and fuses the results using
Reciprocal Rank Fusion before a reranking pass.

## Components
- **Ingestion worker** — parses documents, splits them into ~320-token chunks
  with sentence overlap, and writes embeddings to the `chunks` table.
- **Retriever** — runs the hybrid query and returns the top candidates.
- **Reranker** — blends vector score, keyword score and term coverage into a
  single calibrated score.
- **Synthesizer** — calls the configured LLM with the numbered passages and a
  strict JSON schema, producing an answer, citations and a confidence value.

## Configuration
`TOP_K_DEFAULT` controls how many passages are sent to the model (default 6).
`RERANK_ENABLED` toggles the reranking pass. `LLM_PROVIDER` selects
`anthropic`, `openai` or `offline`.

## Runbook: high retrieval latency
1. Check the `rag.generate_answer` span in the trace viewer for the slow stage.
2. If `vectorstore.hybrid_search` dominates, confirm the HNSW index exists:
   `\\d+ chunks`. Rebuild with `REINDEX INDEX ix_chunks_embedding_hnsw`.
3. If synthesis dominates, check the LLM provider status page and consider
   lowering `LLM_MAX_TOKENS`.
4. Redis caches answers for 15 minutes; a cold cache after a deploy is expected.

## On-call
The retrieval service is owned by the Knowledge Platform team. Page
`knowledge-platform` for SEV1/SEV2 incidents.
""",
    },
    {
        "title": "Weekly Engineering Sync — 2026-08-18",
        "category": "meeting-notes",
        "source_type": "meeting-notes",
        "content": """# Weekly Engineering Sync — 18 August 2026

Attendees: Priya (Eng Lead), Marcus (Backend), Dana (Frontend), Sam (SRE)

## Decisions
- We will ship hybrid retrieval to production on 25 August behind a feature flag.
- The embedding dimension is fixed at 768 for now; migrating to 1024 is deferred
  to Q4 and requires a full re-index.
- Answer caching TTL is set to 15 minutes. Sam to add a cache-hit-rate dashboard.

## Action items
- Marcus: add the reranker span to OpenTelemetry — due 21 August.
- Dana: build the confidence gauge and citation hover previews — due 22 August.
- Sam: load-test the `/query` endpoint at 50 rps — due 22 August.
- Priya: schedule a follow-up with the Legal team about contract ingestion.

## Risks
- pgvector HNSW build time grows with corpus size; we should monitor ingestion
  latency once we pass 100k chunks.
- The offline synthesis fallback is extractive only; demos without an API key
  will look weaker. Document this clearly in the README.
""",
    },
    {
        "title": "Incident Report — INC-20260812 API Latency Spike",
        "category": "incident",
        "source_type": "incident",
        "content": """# Incident Report — INC-20260812

## Summary
On 12 August 2026 between 14:05 and 14:52 UTC, the production `/query` endpoint
p95 latency rose from 900 ms to 6.3 s. Roughly 8% of requests timed out. Severity
was classified as SEV2.

## Impact
Approximately 1,200 user-facing queries were slow or failed. No data was lost. No
incorrect answers were served.

## Root cause
A deploy shipped a change that disabled the HNSW index hint, causing pgvector to
fall back to an exact nearest-neighbour scan. Under normal load this scan
saturated CPU on the primary database.

## Detection
The SRE on-call was paged by the latency SLO burn-rate alert at 14:11 UTC.

## Resolution
The offending deploy was rolled back at 14:44 UTC. Latency recovered within
eight minutes. The index hint was restored and covered by a regression test.

## Follow-up actions
1. Add a query-plan assertion to CI that fails if `chunks` is scanned
   sequentially. Owner: Sam. Due: 19 August.
2. Add a pre-deploy canary that runs 20 representative queries and checks p95.
   Owner: Marcus. Due: 26 August.
3. Document the rollback procedure in the retrieval runbook. Owner: Priya.

## Lessons learned
Index configuration should be treated as code and verified in CI, not assumed.
""",
    },
    {
        "title": "Information Security Policy — Access Control",
        "category": "security",
        "source_type": "policy",
        "content": """# Information Security Policy — Access Control

## Principle of least privilege
Access to systems and data is granted based on job function and is reviewed
quarterly. Access that has not been used for 90 days is automatically revoked.

## Authentication
All employees must use single sign-on with hardware-backed multi-factor
authentication. Passwords must be at least 14 characters and are never shared.
Service accounts use short-lived tokens issued by the secrets manager.

## Production access
Access to production databases requires a documented business reason, manager
approval, and is time-boxed to a maximum of eight hours. All production sessions
are logged and recorded.

## Customer data
Customer data may only be accessed from managed devices on the corporate network
or VPN. Exporting customer data to a personal device or account is prohibited and
is grounds for termination.

## Incident reporting
Suspected security incidents must be reported to the Security team within one
hour of discovery via the `#security-incidents` channel or the on-call pager.

## Vendor access
Third-party vendors are granted access through a dedicated, monitored account
with an expiry date. Vendor access is reviewed before each contract renewal.
""",
    },
]


def ensure_user(db, username: str, password: str) -> User:
    user = db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    ).scalar_one_or_none()
    if user is None:
        user = User(id=str(uuid.uuid4()), username=username, password_hash=hash_password(password))
        db.add(user)
        db.flush()
    return user


def seed(username: str = "demo", password: str = "demopass1", *, reset: bool = False) -> int:
    with db_session() as db:
        user = ensure_user(db, username, password)
        if reset:
            for doc in db.query(Document).filter(Document.user_id == user.id).all():
                db.delete(doc)
            db.flush()
        ingested = 0
        for spec in SEED_DOCUMENTS:
            _, _, deduped = ingest_content(
                db,
                user_id=user.id,
                title=spec["title"],
                content=spec["content"],
                category=spec["category"],
                source_type=spec["source_type"],
                metadata={"seed": True},
            )
            if not deduped:
                ingested += 1
    logger.info("seed_complete", username=username, documents_ingested=ingested)
    return ingested


if __name__ == "__main__":  # python -m app.seed [--user U --password P] [--reset]
    import argparse

    from app.core.database import init_db

    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="demo")
    parser.add_argument("--password", default="demopass1")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    init_db()
    count = seed(args.user, args.password, reset=args.reset)
    print(f"seeded {count} documents into account '{args.user}' (password: {args.password})")
