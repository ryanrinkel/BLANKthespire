#!/usr/bin/env bash
# Nightly sync of the server data that lives OUTSIDE the database and git — forged art, the live card-feedback
# log, and the captured-gaps log — to a DigitalOcean Space (S3-compatible) with rclone. The Managed MySQL
# database has its own daily backups (verify retention in the DO console); this covers what it doesn't.
#
# One-time setup on the droplet:
#     sudo apt install rclone
#     rclone config   # remote "spaces", type s3, provider DigitalOcean, your Space's endpoint + keys
# Then install btsweb-backup.service + .timer (this directory) and `systemctl enable --now btsweb-backup.timer`.
set -euo pipefail

REPO="${BTSWEB_REPO:-/opt/btsweb}"
REMOTE="${BTSWEB_BACKUP_REMOTE:-spaces:btsweb-backup}"
STAMP="$(date -u +%F)"

echo "== $(date -u +%FT%TZ) backup -> $REMOTE"
# Art: incremental mirror (only new/changed files move; deleted classes' art is pruned on the remote too).
rclone sync "$REPO/web/static/forged" "$REMOTE/forged" --fast-list --quiet
# Append-only logs: keep a dated copy so a corrupted file can't overwrite good history.
for f in card_feedback.jsonl captured_gaps.jsonl; do
  if [[ -f "$REPO/web/$f" ]]; then
    rclone copyto "$REPO/web/$f" "$REMOTE/logs/$STAMP/$f" --quiet
  fi
done
# The per-user recency ledgers the generator keeps (scratch, but they steer future forges).
if [[ -d "$REPO/generation/scratch" ]]; then
  rclone sync "$REPO/generation/scratch" "$REMOTE/scratch" --include "*.jsonl" --quiet
fi
echo "== backup done"
