#!/usr/bin/env bash
# Phase B soak metrics — bucket distribution, LLM cost, blacklist auto-red rate.
# Usage:  ssh root@81.200.119.132 'bash -s' < ops/v2-soak-metrics.sh
# Or remote one-shot:  ssh homelab "PGPASSWORD='...' psql '...' < ops/v2-soak-metrics.sh"
#
# Reads DB connection from /opt/avito-system/.env on VPS,
# falls back to AVITO_PG_URL env var if running elsewhere.

set -euo pipefail

if [[ -z "${AVITO_PG_URL:-}" ]]; then
  if [[ -r /opt/avito-system/.env ]]; then
    # Strip the SQLAlchemy +asyncpg adapter and the prepared_statement_cache_size knob,
    # neither of which psql understands.
    AVITO_PG_URL=$(grep -E '^DATABASE_URL=' /opt/avito-system/.env \
      | head -1 | cut -d= -f2- \
      | sed 's|postgresql+asyncpg://|postgresql://|' \
      | sed 's|[?&]prepared_statement_cache_size=0||g' \
      | sed 's|[?&]ssl=require|?sslmode=require|g')
  fi
fi
: "${AVITO_PG_URL:?DATABASE_URL not found — set AVITO_PG_URL manually}"

run() { psql "$AVITO_PG_URL" -X -tA -c "$1" ; }

echo "===== Phase B V2 soak metrics @ $(date -u +%FT%TZ) ====="

echo
echo "--- Bucket distribution (last 24h) ---"
psql "$AVITO_PG_URL" -X -c "
  SELECT bucket, count(*) AS lots, count(*) FILTER (WHERE in_alert_zone) AS in_alert
  FROM profile_listing_evaluations e
  JOIN profile_listings pl ON pl.profile_id = e.profile_id AND pl.listing_id = e.listing_id
  WHERE e.evaluated_at > now() - interval '24 hours'
  GROUP BY bucket
  ORDER BY bucket;
"

echo "--- Per-profile bucket split (last 24h) ---"
psql "$AVITO_PG_URL" -X -c "
  SELECT sp.name, e.bucket, count(*) AS lots
  FROM profile_listing_evaluations e
  JOIN search_profiles sp ON sp.id = e.profile_id
  WHERE e.evaluated_at > now() - interval '24 hours'
  GROUP BY sp.name, e.bucket
  ORDER BY sp.name, e.bucket;
"

echo "--- LLM cost (last 24h) ---"
psql "$AVITO_PG_URL" -X -c "
  SELECT type,
         count(*) AS rows,
         round(sum(cost_usd)::numeric, 4) AS total_usd,
         round(avg(cost_usd)::numeric * 1000, 4) AS per_1k_usd,
         round(avg(latency_ms)::numeric, 0) AS avg_latency_ms
  FROM llm_analyses
  WHERE created_at > now() - interval '24 hours'
  GROUP BY type
  ORDER BY type;
"

echo "--- Auto-red blacklist rate (last 24h) ---"
psql "$AVITO_PG_URL" -X -c "
  SELECT
    split_part(reason, ':', 2) AS criterion_key,
    count(*) AS hits
  FROM user_listing_blacklist
  WHERE reason LIKE 'auto_red:%'
    AND created_at > now() - interval '24 hours'
  GROUP BY 1
  ORDER BY hits DESC;
"

echo "--- Polling success rate (last 1h) ---"
psql "$AVITO_PG_URL" -X -c "
  SELECT status, count(*) AS runs,
         round(avg(EXTRACT(EPOCH FROM (finished_at - started_at)))::numeric, 1) AS avg_dur_s
  FROM profile_runs
  WHERE started_at > now() - interval '1 hour'
  GROUP BY status
  ORDER BY status;
"

echo "--- Pool state right now ---"
psql "$AVITO_PG_URL" -X -c "
  SELECT a.nickname, a.android_user_id, a.state,
         s.expires_at,
         (s.expires_at - now()) AS time_left
  FROM avito_accounts a
  LEFT JOIN avito_sessions s ON s.account_id = a.id AND s.is_active
  ORDER BY a.android_user_id;
"

echo "===== End ====="
