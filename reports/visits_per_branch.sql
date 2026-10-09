-- Report name: Visits Per Branch
-- Member visits per branch for calendar year 2024, branch local time
-- A visit starts with check_in and ends with check_out at the same branch
-- Operating hours (05:00-23:00) are not encoded in the query 
-- The report covers all of calendar 2024 in branch local time, for readability
--
-- Counting decisions:
--   event_type matched case-insensitively, so the 181 'CHECK_IN' rows count  **
--   Rows sharing the same source_ref counted once  **
--   Events for member_ids missing from the members table are excluded  **
--   A check_in counts only when the member's next event at that branch is a check_out **
--   A check_out with no following check_in 
--
--   ** See Data Quality Report 

WITH deduped AS (
    SELECT e.event_id, e.member_id, e.branch_id, e.event_ts,
           lower(e.event_type) AS event_type,
           row_number() OVER (PARTITION BY e.source_ref
                              ORDER BY e.event_id) AS rn
    FROM events e
    JOIN members m ON m.member_id = e.member_id
    WHERE lower(e.event_type) IN ('check_in', 'check_out')
),
sequenced AS (
    SELECT d.*,
           lead(d.event_type) OVER (
               PARTITION BY d.member_id, d.branch_id
               ORDER BY d.event_ts, d.event_id
           ) AS next_event_type
    FROM deduped d
    WHERE d.rn = 1
)
SELECT b.branch_id,
       b.name AS branch_name,
       count(s.event_id) AS member_visits
FROM branches b
LEFT JOIN sequenced s
       ON s.branch_id = b.branch_id
      AND s.event_type = 'check_in'
      AND s.next_event_type = 'check_out'
      AND s.event_ts >= (TIMESTAMP '2024-01-01 00:00' AT TIME ZONE b.timezone)
      AND s.event_ts <  (TIMESTAMP '2025-01-01 00:00' AT TIME ZONE b.timezone)
GROUP BY b.branch_id, b.name
ORDER BY b.branch_id;
