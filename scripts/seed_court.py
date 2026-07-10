"""
File: scripts/seed_court.py
Purpose: Seed the Court record and ingest OPERATOR-SUPPLIED official rule documents (§13).
    Reads PDFs from seed_data/court_rules/ (gitignored — the operator places real, officially
    sourced documents there; nothing ships in the repo) and runs the real ingestion pipeline
    (extract → chunk → embed → persist). FAILS LOUDLY when the folder is missing or empty —
    it NEVER falls back to generated or synthesized rule text, by design (§13 hard constraint).
Depends on: backend app (SessionLocal, models, court services); a reachable database
    (alembic upgrade head applied) and FIREWORKS_API_KEY for embeddings.
Related: backend/app/services/court_knowledge_service.py, docs/ARCHITECTURE.md §13
Security notes: Promoting a user to admin (--promote-admin) is an explicit operator action —
    this script never makes anyone admin implicitly.

Usage:
    python scripts/seed_court.py [--name "<court name>"] [--jurisdiction "<description>"]
                                 [--rules-dir seed_data/court_rules]
                                 [--promote-admin someone@example.com]

Optional per-file provenance: put a manifest.json in the rules dir mapping filename →
    {"title": ..., "source_citation": ..., "source_reference": ...}. Files without an entry are
    ingested with the filename as title and no citation metadata (a warning is printed —
    provenance matters for the citation-grounding audit trail, Phase 5).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

# Operator-supplied defaults matching the actual filed petition's own caption and jurisdictional
# language (provided by the operator 2026-07-10 — named instruments only, no rule text). Override
# --name/--jurisdiction if your case papers designate the forum differently.
DEFAULT_COURT_NAME = "Regional Trial Court — Special Commercial Court, Taguig City"
DEFAULT_JURISDICTION = (
    "National Capital Judicial Region; designated Special Commercial Court; jurisdiction over "
    "intra-corporate controversies under Section 73 of RA 11232 in relation to A.M. No. "
    "01-2-04-SC"
)

MISSING_RULES_MESSAGE = """
ERROR: no rule documents found to ingest.

Place the official rule documents (text-based PDFs) in:  {rules_dir}

What belongs there: the procedural instruments governing your forum, obtained from OFFICIAL
government sources (e.g. the Supreme Court E-Library / official gazette / the court's own
published issuances). Download the official PDFs and copy them into that folder, optionally
with a manifest.json recording each file's formal citation and source URL.

Do NOT use AI-generated text, unofficial summaries, or retyped excerpts — this pipeline
ingests verbatim official documents only, and the citation-grounding audit trail (§13)
depends on that provenance.
""".strip()


def _load_manifest(rules_dir: Path) -> dict:
    manifest_path = rules_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — bad manifest should stop the operator, loudly
        sys.exit(f"ERROR: could not parse {manifest_path}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default=DEFAULT_COURT_NAME)
    parser.add_argument("--jurisdiction", default=DEFAULT_JURISDICTION)
    parser.add_argument("--rules-dir", default=str(REPO_ROOT / "seed_data" / "court_rules"))
    parser.add_argument(
        "--promote-admin",
        metavar="EMAIL",
        default=None,
        help="Explicitly promote this existing user to the admin role (operator action).",
    )
    args = parser.parse_args()

    rules_dir = Path(args.rules_dir)
    pdfs = sorted(rules_dir.glob("*.pdf")) if rules_dir.is_dir() else []
    if not pdfs:
        sys.exit(MISSING_RULES_MESSAGE.format(rules_dir=rules_dir))

    # Imports deferred until after the fail-fast check so `--help` etc. need no backend deps.
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.court import Court
    from app.models.user import User
    from app.services import court_knowledge_service, storage_service

    manifest = _load_manifest(rules_dir)
    db = SessionLocal()
    try:
        if args.promote_admin:
            user = db.scalar(select(User).where(User.email == args.promote_admin.lower()))
            if user is None:
                sys.exit(f"ERROR: no user with email {args.promote_admin!r} to promote.")
            user.role = "admin"
            db.commit()
            print(f"Promoted {user.email} to admin.")

        # Idempotent: reuse the court if a previous seed created it.
        court = db.scalar(select(Court).where(Court.name == args.name))
        if court is None:
            court = Court(name=args.name, jurisdiction_description=args.jurisdiction)
            db.add(court)
            db.commit()
            db.refresh(court)
            print(f"Created court: {court.name} ({court.id})")
        else:
            print(f"Court already exists: {court.name} ({court.id})")

        for pdf in pdfs:
            meta = manifest.get(pdf.name, {})
            if not meta:
                print(f"WARNING: {pdf.name} has no manifest.json entry — ingesting without "
                      "citation/source provenance (add one for the §13 audit trail).")
            data = pdf.read_bytes()

            # Durable copy in object storage when reachable; otherwise record the operator's
            # local path so ingestion still proceeds (the chunks are what retrieval uses).
            key = f"courts/{court.id}/{pdf.name}"
            try:
                storage_service.put_object(key, data, content_type="application/pdf")
            except Exception:  # noqa: BLE001
                print(f"WARNING: object storage unreachable — recording local path for {pdf.name}")
                key = str(pdf)

            document = court_knowledge_service.create_rule_document_row(
                db,
                court.id,
                title=meta.get("title", pdf.stem),
                storage_path=key,
                source_citation=meta.get("source_citation"),
                source_reference=meta.get("source_reference"),
            )
            print(f"Ingesting {pdf.name} …")
            court_knowledge_service.ingest_rule_document(db, document, data)
            db.refresh(document)
            if document.ingestion_status == "ready":
                print(f"  ready: {document.chunk_count} chunks")
            else:
                print(f"  FAILED: {document.error}")

        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
