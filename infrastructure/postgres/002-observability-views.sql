-- Production observability — cheap, queryable signals.
--
-- Runs as a scheduled job (e.g. k8s cron / systemd timer) rather than a
-- trigger: every mutation already happens through the app, so a daily dump
-- is enough for drift/abuse review.

DROP VIEW IF EXISTS guard_telemetry;
DROP VIEW IF EXISTS org_usage;

-- Per-org activity (read-model freshness + billing sanity).
CREATE VIEW org_usage AS
SELECT
    org_id,
    count(*)                                    AS voucher_count,
    count(*) FILTER (WHERE is_cancelled)        AS cancelled_count,
    sum(amount_paise) FILTER (WHERE NOT is_cancelled) AS net_paise,
    max(vdate)                                  AS last_voucher_date
FROM vouchers
GROUP BY org_id;

-- Cross-tenant queries should be IMPOSSIBLE under RLS; this query returns a
-- row per org and is the health probe proving it works.
COMMENT ON VIEW org_usage IS
  'SELECT * FROM org_usage — one row per org, only your org under RLS.';