# Data migration 2026-05-04 — homelab → Cloud Supabase

Project: `drwgozasaypgphkxyizt` (Frankfurt, eu-central-1).

## Sources

- **Homelab Supabase** (`213.108.170.194:5433` PostgreSQL 15) — xapi-side tables.
- **Homelab `avito-monitor-db-1`** (`docker exec`, PostgreSQL 16) — monitor-side tables.

## Schema applied to Cloud

1. `supabase/migrations/001_init.sql` (with `audit_log` renamed to `audit_log_xapi` to avoid clash with monitor's audit_log)
2. `supabase/migrations/003_tenant_auth.sql`
3. `supabase/migrations/005_avito_notifications.sql`
4. `supabase/migrations/006_avito_device_commands.sql`
5. `supabase/migrations/007_avito_accounts_pool.sql`
6. `supabase/migrations/008_avito_accounts_multidevice.sql`
7. `avito-monitor` Alembic upgrade head (revisions 0001 → 0005_owner_account)
8. Manual `CREATE TABLE avito_api_keys` (xapi calls `sb.table("avito_api_keys")` but the migration files define `api_keys` — likely historical drift; created the AvitoSystem-specific table on top)

Seed migrations (`002_seed.sql`, `004_tenant_auth_seed.sql`) **skipped** — would have created test rows that conflict with live data being migrated.

## Data migrated

xapi-side (from `213.108.170.194:5433`):

| Table | Rows |
|---|---|
| supervisors | 1 |
| toolkits | 1 |
| tenants | 1 |
| avito_accounts | 2 (Main, Clone) |
| avito_sessions | 3 (`is_active=true` only; 66 inactive history rows skipped) |
| avito_api_keys | 1 |

monitor-side (from `avito-monitor-db-1`):

| Table | Rows |
|---|---|
| users | 1 |
| listings | 759 |
| llm_analyses | 872 |
| search_profiles | 7 |
| profile_listings | 517 |
| user_listing_blacklist | 15 |
| profile_market_stats | 7 |

## Tables NOT migrated (rebuild themselves)

- `avito_listings`, `avito_listings_history` — no rows existed on homelab Supabase
- `audit_log` (monitor) — 0 rows
- `audit_log_xapi` (formerly homelab `audit_log`) — 69 rows skipped per plan
- `avito_notifications` (50), `avito_device_commands` (117) — historical, not needed post-cutover
- `notifications` (monitor, 18) — replayed on next polling tick
- `profile_runs` (1074), `activity_log`, `health_checks`, `system_settings` (0) — operational telemetry, regenerated
- `messenger_chats`, `messenger_messages`, `chat_dialog_state`, `price_analyses`, `price_analysis_runs` — not yet populated in production

## Method

```
# xapi (FK order: supervisors → toolkits → tenants → avito_sessions → avito_api_keys)
pg_dump --data-only --no-owner --column-inserts -t public.<X> SOURCE | psql CLOUD

# avito_sessions: only active rows
psql SOURCE -c "\copy (SELECT * FROM avito_sessions WHERE is_active=true) TO STDOUT" \
  | psql CLOUD -c "\copy avito_sessions FROM STDIN"

# monitor (FK order: users → listings → llm_analyses → profile_listings → user_listing_blacklist;
#                   search_profiles, profile_market_stats already loaded earlier)
docker exec avito-monitor-db-1 pg_dump -U avito -d avito_monitor -h localhost \
    --data-only --no-owner -t public.<X> \
  | psql CLOUD
```

`--column-inserts` corrupted on emoji/apostrophe boundaries in `listings.description` (33/759 rows
lost on first pass). Switched to default COPY format which is encoding-robust.

## Source dumps NOT committed

The dumps include JWT tokens (in `avito_sessions.tokens`) and api-key hashes — sensitive,
never committed. `.gitignore` in this dir excludes them.
