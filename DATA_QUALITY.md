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
-++-+++-+
      1031 | Ella       | Nelson    |              7 | 2021-04-03 | basic           | active
      1132 | Jacob      | Hill      |              4 | 2021-12-09 | premium         | active
(2 rows)

**Severity:**
	Sev-2
**Reports affected:**
	active_members_monthly (2 members never counted) 
	visits_per_branch and daily_visits (their visits excluded at the join)
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
-+-
         1 |   109
         2 |   108
         3 |   108
         4 |   108
         5 |   108
         6 |   109
         7 |   108
         8 |    70
(8 rows)

**Severity:**
	Sev-3
**Reports affected:**
	None of the delivered reports: all of them join to members, so this activity is excluded
	Any future count taken from events alone would quietly include 414 fake check-ins
**Likely cause:**	
	Test or probe accounts in the access-control feed that were never cleaned up 
	The even branch spread, the balanced ins and outs, and the absence of friend visits all point that way
**Comments:**
	Question for the access-control owner: can you confirm 990001 and 990002 are internal test IDs, and not real access by unknown cards?

### 3. Uppercase `CHECK_IN` events at branch 4

**What it is:** The events table contains both `check_in` and uppercase `CHECK_IN` event types. The uppercase form appears only at branch 4 and only from device D04-IN, during one week in April 2024.

**Evidence:** 73,913 lowercase `check_in` events vs 181 uppercase `CHECK_IN` events. All 181 uppercase rows are from branch 4, device D04-IN, between 2024-04-08 and 2024-04-14. All 181 later have a check-out for the same member at the same branch under the loose matching check.

**Severity:**

**Reports affected:** Any report filtering only on lowercase `check_in` would miss these 181 branch 4 visits unless it handles the uppercase form.

**Likely cause:**

### 4. Check-in and check-out totals do not reconcile

**What it is:** There are more check-in events than check-out events. This is a reconciliation gap that needs to be explained by the more specific pairing findings below.

**Evidence:** 73,913 lowercase `check_in` events vs 73,205 `check_out` events, a difference of 708 before the 181 uppercase `CHECK_IN` events are considered.

**Severity:**

**Reports affected:**

**Likely cause:**



### 5. Phantom member activity is spread across all branches

**What it is:** The two missing member IDs are not a one-off local problem. Their activity is spread across all 8 branches in an almost even pattern, which makes it look more like test or probe traffic than normal member activity.

**Evidence:** 828 event rows for member_id in (990001, 990002). Branch distribution: 109 at branch 1, 108 at branches 2, 3, 4, 5 and 7, 109 at branch 6, and 70 at branch 8. Both member IDs span the full 2024 access period.

**Severity:**

**Reports affected:**

**Likely cause:** Possible test/probe accounts; needs confirmation from the CRM and access-control owners.

### 6. Some check-ins never close cleanly

**What it is:** Some visits start with a check-in but do not end cleanly with a matching check-out. The size of the problem depends on how strictly visits are paired.

**Evidence:** 115 check-ins have no later check-out at all for the same member at the same branch. Under stricter next-event logic, 1,424 check-ins are not followed by a check-out as the member's next event at that branch.

**Severity:**

**Reports affected:**

**Likely cause:**

### 7. Duplicate check-ins at the same second

**What it is:** The same member sometimes has two check-ins at the same branch in the exact same second. That pattern points to duplicate ingestion rather than two real entries.

**Evidence:** 331 duplicate same-second check-in groups, involving 662 check-in rows. In one inspected pair, the two rows had the same `source_ref` and the same `event_ts`, but different `ingested_at` values.

**Severity:**

**Reports affected:**

**Likely cause:**

### 8. Visits after membership cancellation

**What it is:** Some check-ins happened while the member's membership was cancelled and had not been reactivated before the visit.

**Evidence:** The cancelled-membership visit query returned 30 grouped member rows. The total visit count should be confirmed before this number is finalized.

**Severity:**

**Reports affected:**

**Likely cause:**

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
