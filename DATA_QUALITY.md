# FitTrack Data Quality Report

# Assignment: Senior QA Engineer (Data Quality), NIBBANA. Database: Postgres, `fittrack`

## What this report covers

The FitTrack database collects data from two systems across 8 gyms in 4 time zones: the CRM (memberships) and the access-control system 
(turnstiles and front-desk tablets). This report lists the data-quality issues found in the delivered data set, the evidence for each, 
and what they do to the management reports built on this data.

## Business rules the data was judged against

1. Membership state comes from `events`, not from the member row: active from `membership_started` / `membership_reactivated` until `membership_cancelled`.
2. A member is active in a month if their latest membership event by month end is a start or reactivation.
3. A visit starts with a `check_in` at a branch and ends with a `check_out` at the same branch.
4. A `friend_visit` happens only together with the member's own visit; monthly allowance by tier: basic 2, standard 3, premium 8.
5. Days and months are calendar days and months in the branch's local time zone.

## Severity scale

Sev-1, blocking: Makes a report wrong in a way a reader cannot see, or breaks a business rule outright. The test suite exits non-zero; reports should not go out until it is fixed or explicitly accepted
Sev-2, major: Skews report numbers or drops real activity. Reports can go out, but only with the caveat stated next to them
Sev-3, minor: Data hygiene problem with no visible report impact today. Worth fixing at the source and worth monitoring, because it can become Sev-2 without anyone noticing

## Findings

### 1. Membership never started for two members

**What it is:** The members table has 1,122 rows, but only 1,120 membership_started events. 
				Members 1031 and 1132 have no membership_started event, even though both rows show status active 
				and both members have check_in, check_out, and friend_visit events in 2024. 
				Because membership state comes from events, these two members are invisible to the reports: 
				they never count as active, and their visits drop out of the visit reports at the join to members.

**Evidence:** 1,122 members vs 1,120 membership_started events. The query below returns members 1031 and 1132.

SELECT m.member_id, m.first_name, m.last_name, m.home_branch_id,
       m.joined_on, m.membership_tier, m.status
FROM members m
WHERE NOT EXISTS (
    SELECT 1
    FROM events s
    WHERE s.member_id = m.member_id
      AND s.event_type = 'membership_started'
)
ORDER BY m.member_id;

member_id | first_name | last_name | home_branch_id | joined_on  | membership_tier | status
-----------+------------+-----------+----------------+------------+-----------------+--------
      1031 | Ella       | Nelson    |              7 | 2021-04-03 | basic           | active
      1132 | Jacob      | Hill      |              4 | 2021-12-09 | premium         | active
(2 rows)

**Severity:**
	Sev-2
**Reports affected:**
	visits_per_branch: their visits are excluded at the join to members 
	Any monthly active-members count built from events would also miss both members entirely
**Likely cause:**
	The CRM membership creation flow. Either it sometimes fails to write the membership_started event, or these two members were created by a manual update that skipped the event. 
	Their home branches differ (7 and 4), so it is not one branch's local problem.
**Comments:**
	The member rows say active since 2021, so the CRM treats them as members while the event stream says their membership never began. 
	Question for the CRM owner: which of the two drives billing? If billing keys off the start event, these members may never have been charged. 
	If it keys off the member row, the event stream is simply incomplete.

### 2. Events reference members missing from the members table

**What it is:** 828 events point to member IDs 990001 and 990002, which do not exist in the members table. 
				The activity is not a one-off: it spans all 8 branches in an almost even pattern (109 at branch 1, 
				108 each at branches 2, 3, 4, 5, 7, 109 at branch 6, 70 at branch 8) and runs from 2024-01-01 to 2024-12-30. 
				The events are only check-ins and check-outs, 414 of each, with no friend visits.

**Evidence:** 

SELECT count(*) FROM events WHERE member_id IN (990001, 990002);
 count
-
   828
(1 row)

SELECT branch_id, count(*) FROM events WHERE member_id IN (990001, 990002) GROUP BY branch_id ORDER BY branch_id;
 
 branch_id | count
-----------+-------
         1 |   109
         2 |   108
         3 |   108
         4 |   108
         5 |   108
         6 |   109
         7 |   108
         8 |    70
(8 rows)

SELECT event_type, count(*)
FROM events
WHERE member_id IN (990001, 990002)
GROUP BY event_type;

 event_type | count
------------+-------
 CHECK_IN   |     1
 check_in   |   413
 check_out  |   414
(3 rows)

**Severity:**
	Sev-3
**Reports affected:**
	None of the delivered reports: visits_per_branch joins to members, so this activity is excluded
	Any count taken from events alone would quietly include 414 fake check-ins
**Likely cause:**	
	Test or probe accounts in the access-control feed that were never cleaned up 
	The even branch spread, the balanced ins and outs, and the absence of friend visits all point that way
**Comments:**
	Question for the access-control owner: can you confirm 990001 and 990002 are internal test IDs, and not real access by unknown cards? 
	If they are test IDs, they should be filtered or removed at ingestion

### 3. Uppercase `CHECK_IN` events at branch 4

**What it is:** 
	The event_type vocabulary is not normalized: alongside 73,913 lowercase check_in events there are 181 CHECK_IN events in uppercase. 
	All 181 come from one device, D04-IN at branch 4 (Riverwalk), in one week, 2024-04-08 to 2024-04-14. 
	These are real visits, each has a later check-out for the same member at the same branch, so any count that matches check_in exactly and case-sensitively silently loses 181 branch 4 visits.

**Evidence:** 
SELECT event_type, count(*)
FROM events
WHERE lower(event_type) = 'check_in'
GROUP BY event_type;

 event_type | count
------------+-------
 check_in   | 73913
 CHECK_IN   |   181
(2 rows)

SELECT branch_id, device_id, min(event_ts) AS first_seen, max(event_ts) AS last_seen, count(*)
FROM events
WHERE event_type = 'CHECK_IN'
GROUP BY branch_id, device_id;

 branch_id | device_id |       first_seen       |       last_seen        | count
-----------+-----------+------------------------+------------------------+-------
         4 | D04-IN    | 2024-04-08 06:08:36-04 | 2024-04-14 22:00:32-04 |   181
(1 row)

SELECT count(*)
FROM events ci
WHERE ci.event_type = 'CHECK_IN'
  AND EXISTS (
      SELECT 1
      FROM events co
      WHERE co.member_id = ci.member_id
        AND co.branch_id = ci.branch_id
        AND lower(co.event_type) = 'check_out'
        AND co.event_ts > ci.event_ts
  );

 count
-------
   181
(1 row)

SELECT count(*)
FROM events ci
WHERE ci.event_type = 'CHECK_IN'
  AND NOT EXISTS (
      SELECT 1
      FROM events co
      WHERE co.member_id = ci.member_id
        AND co.branch_id = ci.branch_id
        AND lower(co.event_type) = 'check_out'
        AND co.event_ts > ci.event_ts
  );
  
count
-------
     0
(1 row)

**Severity:**
	Sev-2

**Reports affected:** 
	visits_per_branch, limited to branch 4. 
	A counter that matches check_in exactly loses 181 of branch 4's roughly 9,300 visits, about 2 percent; 
	the delivered report counts them because matching is case-insensitive

**Likely cause:**
	Device D04-IN at Riverwalk sent an uppercase event type for one week, 2024-04-08 to 2024-04-14, most plausibly a firmware or configuration change on that one device that was rolled back the next week.

### 4. Check-in and check-out totals do not reconcile

**What it is:** 
	A basic reconciliation control: over a full year, check-ins and check-outs should match, since every visit that starts should end. 
	They do not: check-ins outnumber check-outs by 889. This finding is the control total; the causes underneath it are the visits that never closed and the duplicate check-ins (see Findings below)

**Evidence:** 
	 Counted case-insensitively, there are 74,094 check-ins (73,913 check_in plus 181 CHECK_IN) against 73,205 check_out events: a gap of 889. 
	 Counted lowercase-only, the gap looks like 708, which understates it, because the 181 uppercase check-ins did check out and their check-outs are inside the 73,205.

SELECT lower(event_type) AS event_type, count(*)
FROM events
WHERE lower(event_type) IN ('check_in', 'check_out')
GROUP BY lower(event_type);

 event_type | count
------------+-------
 check_in   | 74094
 check_out  | 73205
(2 rows)


**Severity:**
	Sev-3

**Reports affected:**
	visits_per_branch report requires a check-out before counting a visit

**Likely cause:**
	Two components, both proven separately below: some visits genuinely never record a check-out and duplicated check-in rows inflate the check-in side 

### 5. Some check-ins never close cleanly

**What it is:** 
	Some visits start but never properly end. 115 check-ins have no later check-out at all for the same member at the same branch: those visits are lost completely. 
	Under the stricter rule that the member's next event at that branch must be the check-out, 1,424 check-ins (about 2 percent of 74,094) fail. 
	
**Evidence:** 

SELECT count(*)
FROM events ci
WHERE lower(ci.event_type) = 'check_in'
  AND NOT EXISTS (
      SELECT 1 FROM events co
      WHERE co.member_id = ci.member_id
        AND co.branch_id = ci.branch_id
        AND lower(co.event_type) = 'check_out'
        AND co.event_ts > ci.event_ts
  );
  
   count
-------
   115
(1 row)

SELECT count(*)
FROM (
    SELECT lower(event_type) AS event_type,
           lead(lower(event_type)) OVER (
               PARTITION BY member_id, branch_id
               ORDER BY event_ts, event_id
           ) AS next_event_type
    FROM events
    WHERE lower(event_type) IN ('check_in', 'check_out')
) s
WHERE s.event_type = 'check_in'
  AND s.next_event_type IS DISTINCT FROM 'check_out';
  
 count
-------
  1424
(1 row)  

**Severity:**
	Sev-2
**Reports affected:**
	visits_per_branch counts only completed visits
**Likely cause:**
	Members leaving without swiping out, missed exit reads, or check-out events lost before ingestion. 
	Part of the 1,424 overlaps with the next Finding (6): duplicated check-in also makes the genuine check-in look unclosed under next-event logic

### 6. Duplicate check-ins at the same second

**What it is:** 
	Ingestion sometimes writes the same device event more than once. 
	The copies share one source_ref and one event_ts, and differ only in ingested_at. so one physical entry becomes two check-ins

**Evidence:** 
	331 duplicated source_ref groups among check-ins, 662 rows; some source_ref values appear 3 times. 
	Inspected pair: D01-IN:0002169, identical event_ts, two different ingested_at values.

SELECT source_ref, count(*) AS copies,
       min(event_ts) AS event_ts,
       min(ingested_at) AS first_ingested,
       max(ingested_at) AS last_ingested
FROM events
WHERE lower(event_type) = 'check_in'
GROUP BY source_ref
HAVING count(*) > 1
ORDER BY copies DESC, source_ref;

(too many resulting rows to copy)

**Severity:**
	Sev-2
**Reports affected:**
	visits_per_branch would count about 331 phantom extra visits without deduplication
**Likely cause:**
	Duplicate ingestion with nothing stopping it: no unique constraint and no dedup on source_ref, so a retried write lands as a second row

### 7. Visits after membership cancellation

**What it is:** 
	Members kept walking in after their membership was cancelled. 
	A check-in counts here when the member's latest membership event at that moment was membership_cancelled, 
	with no membership_reactivated before the visit. 
	In other words, the CRM said these people were no longer members, and the turnstiles let them in anyway.

**Evidence:** 
	302 check-ins by 30 distinct members happened while the member was in cancelled state

WITH lifecycle AS (
    SELECT member_id, event_ts, lower(event_type) AS event_type
    FROM events
    WHERE lower(event_type) IN
          ('membership_started', 'membership_reactivated', 'membership_cancelled')
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
SELECT count(*) AS visits_while_cancelled,
       count(DISTINCT member_id) AS members
FROM state
WHERE last_event = 'membership_cancelled';

 visits_while_cancelled | members
------------------------+---------
                    302 |      30
(1 row)


**Severity:**
	Sev-1
**Reports affected:**
	visits_per_branch counts these as ordinary visits: roughly 300 of 70,824, about 0.4 percent
	Nothing in the report can tell them apart from legitimate visits.

**Likely cause:**
	Access control does not check membership state at the door, or it checks a stale copy: the cancellation exists in the CRM event stream, but the turnstile let them in anyway.

## Root causes

To be completed after grouping findings that share the same cause.

## Questions for the CRM team

To be completed.

## Questions for the access-control team

To be completed.

## Monitoring from now on

To be completed.



## Data checked: baseline checks run

| Table | Rows | Contents |
| - | - | - |
| `branches` | 8 | one row per gym, with time zone and opening hours |
| `devices` | 24 | entrance, exit and front-desk devices per branch | 
| `members` | 1,122 | member profiles and the CRM's current membership state |
| `events` | 156,040 | everything both systems recorded (membership history from 2021, access events for 2024) |


##  ROW COUNTS
  SELECT count(*) FROM branches;
  SELECT count(*) FROM devices;
  SELECT count(*) FROM members;
  SELECT count(*) FROM events;

##  NULLS
  SELECT count(*) FROM members WHERE email IS NULL;
  SELECT count(*) FROM events WHERE member_id IS NULL;
  SELECT count(*) FROM events WHERE event_ts IS NULL;

##  VALUE DOMAINS
  SELECT distinct event_type FROM events;
  SELECT distinct kind FROM devices;
 
##  UNIQUENESS
  SELECT source_ref, count(*) FROM events GROUP BY source_ref HAVING count(*) > 1;

##  REFERENTIAL INTEGRITY
  SELECT e.event_id, e.member_id, e.event_type, e.event_ts, e.branch_id, e.source_ref
  FROM events e
  LEFT JOIN members m ON m.member_id = e.member_id
  WHERE m.member_id IS NULL
  ORDER BY e.member_id, e.event_ts;

##  RECONCILIATION SUMS
  SELECT  count(*) FROM events WHERE event_type = 'membership_started';
