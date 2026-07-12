#!/usr/bin/env bash
# File: infra/backup.sh
# Purpose: On-box backup of the two stateful stores — Postgres (courts, cases, sessions,
#   transcripts, scorecards, users) via pg_dump, and the MinIO volume (uploaded pleading/rule
#   PDFs) via a tar of the named volume. Keeps the last RETAIN of each; prints what it wrote.
#   Without this, a droplet/volume failure loses every court, case, and session ever created.
# Usage (from the repo root on the droplet):
#   ./infra/backup.sh                 # one manual backup (run one right before the demo)
#   crontab -e  →  0 3 * * * cd /root/lexpar-ai && ./infra/backup.sh >> /root/backups/backup.log 2>&1
# Restore (Postgres):
#   gunzip -c /root/backups/pg-<STAMP>.sql.gz | docker compose --env-file .env.prod \
#     -f infra/docker-compose.prod.yml exec -T postgres psql -U lexpar -d lexpar
# Restore (MinIO volume — with the stack STOPPED):
#   docker run --rm -v lexpar-prod_minio_prod_data:/data -v /root/backups:/backup alpine \
#     sh -c "cd /data && tar xzf /backup/minio-<STAMP>.tar.gz"
# Security notes: dumps contain attorney work product — they stay on-box under /root/backups
#   (root-only). If you later ship them off-box, encrypt first.

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/root/backups}"
RETAIN="${RETAIN:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
COMPOSE=(docker compose --env-file .env.prod -f infra/docker-compose.prod.yml)

mkdir -p "$BACKUP_DIR"

# 1. Postgres logical dump (consistent snapshot; safe while the stack runs).
"${COMPOSE[@]}" exec -T postgres pg_dump -U lexpar -d lexpar \
  | gzip > "$BACKUP_DIR/pg-$STAMP.sql.gz"
echo "wrote $BACKUP_DIR/pg-$STAMP.sql.gz ($(du -h "$BACKUP_DIR/pg-$STAMP.sql.gz" | cut -f1))"

# 2. MinIO volume tar (the uploaded PDFs). Reading while running is fine for these
#    write-once objects; the authoritative metadata is in Postgres anyway.
docker run --rm -v lexpar-prod_minio_prod_data:/data -v "$BACKUP_DIR":/backup alpine \
  sh -c "cd /data && tar czf /backup/minio-$STAMP.tar.gz ."
echo "wrote $BACKUP_DIR/minio-$STAMP.tar.gz ($(du -h "$BACKUP_DIR/minio-$STAMP.tar.gz" | cut -f1))"

# 3. Retention: keep the newest $RETAIN of each series.
for prefix in pg minio; do
  ls -1t "$BACKUP_DIR"/$prefix-*.gz 2>/dev/null | tail -n +$((RETAIN + 1)) | xargs -r rm --
done
echo "retention: kept newest $RETAIN of each series"
