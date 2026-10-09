"""FitTrack data-quality suite.

Run:  python tests/run_data_quality.py
Connection comes from the standard Postgres environment variables
(PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD). Read-only queries.
Exit code is 1 when a baseline or Sev-1 check fails, 0 otherwise.
Sev-2 and Sev-3 failures print as warnings.
"""

import sys

import psycopg

# (name, level, sql returning one number, expectation)
# expectation "zero"  -> actual must be 0
# expectation "pos"   -> actual must be above 0
CHECKS = [
    # Baseline: the load itself must be sane on any database with this schema
    ("branches rows present", "BASE",
     "SELECT count(*) FROM branches", "pos"),
    ("devices rows present", "BASE",
     "SELECT count(*) FROM devices", "pos"),
    ("members rows present", "BASE",
     "SELECT count(*) FROM members", "pos"),
    ("events rows present", "BASE",
     "SELECT count(*) FROM events", "pos"),
    ("members with NULL email", "BASE",
     "SELECT count(*) FROM members WHERE email IS NULL", "zero"),
    ("events with NULL member_id", "BASE",
     "SELECT count(*) FROM events WHERE member_id IS NULL", "zero"),
    ("events with NULL event_ts", "BASE",
     "SELECT count(*) FROM events WHERE event_ts IS NULL", "zero"),
    ("unknown event_type values", "BASE",
     """SELECT count(*) FROM events
        WHERE lower(event_type) NOT IN
          ('membership_started', 'membership_reactivated',
           'membership_cancelled', 'tier_changed',
           'check_in', 'check_out', 'friend_visit')""", "zero"),
    ("devices with invalid kind", "BASE",
     """SELECT count(*) FROM devices
        WHERE kind NOT IN ('entrance', 'exit', 'front_desk')""", "zero"),

    # Sev-1: report-blocking
    ("check-ins while membership cancelled", "SEV1",
     """WITH lifecycle AS (
            SELECT member_id, event_ts, lower(event_type) AS event_type
            FROM events
            WHERE lower(event_type) IN
              ('membership_started', 'membership_reactivated',
               'membership_cancelled')
        ),
        state AS (
            SELECT c.member_id, c.event_ts,
                   (SELECT l.event_type FROM lifecycle l
                     WHERE l.member_id = c.member_id
                       AND l.event_ts <= c.event_ts
                     ORDER BY l.event_ts DESC LIMIT 1) AS last_event
            FROM events c
            WHERE lower(c.event_type) = 'check_in'
        )
        SELECT count(*) FROM state
        WHERE last_event = 'membership_cancelled'""", "zero"),

    # Sev-2: warnings
    ("duplicate source_ref groups (check-ins)", "SEV2",
     """SELECT count(*) FROM (
            SELECT source_ref FROM events
            WHERE lower(event_type) = 'check_in'
            GROUP BY source_ref, event_ts HAVING count(*) > 1
        ) d""", "zero"),
    ("check-ins with no later check-out", "SEV2",
     """SELECT count(*) FROM events ci
        WHERE lower(ci.event_type) = 'check_in'
          AND NOT EXISTS (
              SELECT 1 FROM events co
              WHERE co.member_id = ci.member_id
                AND co.branch_id = ci.branch_id
                AND lower(co.event_type) = 'check_out'
                AND co.event_ts > ci.event_ts
          )""", "zero"),
    ("check-ins not closed by next event", "SEV2",
     """SELECT count(*) FROM (
            SELECT lower(event_type) AS event_type,
                   lead(lower(event_type)) OVER (
                       PARTITION BY member_id, branch_id
                       ORDER BY event_ts, event_id
                   ) AS next_event_type
            FROM events
            WHERE lower(event_type) IN ('check_in', 'check_out')
        ) s
        WHERE s.event_type = 'check_in'
          AND s.next_event_type IS DISTINCT FROM 'check_out'""", "zero"),
    ("members with no membership_started event", "SEV2",
     """SELECT count(*) FROM members m
        WHERE NOT EXISTS (
            SELECT 1 FROM events s
            WHERE s.member_id = m.member_id
              AND s.event_type = 'membership_started'
        )""", "zero"),
    ("non-lowercase event_type rows", "SEV2",
     "SELECT count(*) FROM events WHERE event_type <> lower(event_type)",
     "zero"),

    # Sev-3: warnings
    ("events for unknown members", "SEV3",
     """SELECT count(*) FROM events e
        LEFT JOIN members m ON m.member_id = e.member_id
        WHERE m.member_id IS NULL""", "zero"),
    ("check-in/check-out count gap", "SEV3",
     """SELECT abs(
            (SELECT count(*) FROM events
              WHERE lower(event_type) = 'check_in')
            -
            (SELECT count(*) FROM events
              WHERE lower(event_type) = 'check_out')
        )""", "zero"),
]


def main():
    failed_blocking = 0
    warnings = 0
    with psycopg.connect("") as conn:  # "" = take PG* env vars
        with conn.cursor() as cur:
            for name, level, sql, expectation in CHECKS:
                cur.execute(sql)
                actual = cur.fetchone()[0]
                if expectation == "zero":
                    ok = actual == 0
                    expected_text = "0"
                else:
                    ok = actual > 0
                    expected_text = ">0"
                if ok:
                    status = "PASS"
                elif level in ("BASE", "SEV1"):
                    status = "FAIL"
                    failed_blocking += 1
                else:
                    status = "WARN"
                    warnings += 1
                print(f"[{status}] {level:4} {name}: "
                      f"expected {expected_text}, actual {actual}")
    print()
    print(f"Blocking failures: {failed_blocking}, warnings: {warnings}")
    return 1 if failed_blocking else 0


if __name__ == "__main__":
    sys.exit(main())
