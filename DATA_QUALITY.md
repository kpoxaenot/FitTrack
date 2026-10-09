# FitTrack Data Quality Report

# Assignment: Senior QA Engineer (Data Quality), NIBBANA. Database: Postgres, `fittrack`

## What this report covers

The FitTrack database collects data from two systems across 8 gyms in 4 time zones: the CRM (memberships) and the access-control system 
(turnstiles and front-desk tablets). This report lists the data-quality issues found in the delivered data set, the evidence for each, 
and what they do to the management reports built on this data.

## Data checked

| Table | Rows | Contents |
| --- | --- | --- |
| `branches` | 8 | one row per gym, with time zone and opening hours |
| `devices` | 24 | entrance, exit and front-desk devices per branch |
| `members` | 1,122 | member profiles and the CRM's current membership state |
| `events` | 156,040 | everything both systems recorded (membership history from 2021, access events for 2024) |

## Business rules the data was judged against

1. Membership state comes from `events`, not from the member row: active from `membership_started` / `membership_reactivated` until `membership_cancelled`.
2. A member is active in a month if their latest membership event by month end is a start or reactivation.
3. A visit starts with a `check_in` at a branch and ends with a `check_out` at the same branch.
4. A `friend_visit` happens only together with the member's own visit; monthly allowance by tier: basic 2, standard 3, premium 8.
5. Days and months are calendar days and months in the branch's local time zone.

##


## Findings

### 1. Membership never started for two members

**What it is:** The `members` table has 1,122 rows, but there are only 1,120 `membership_started` events. The two-row difference is fully explained by members 1031 and 1132, who have no `membership_started` event.

**Evidence:** 1,122 members vs 1,120 `membership_started` events; missing starts for member_ids 1031 and 1132.
select * from members m where m.member_id in (SELECT DISTINCT e.member_id FROM events e WHERE NOT EXISTS (SELECT 1 FROM events s WHERE s.member_id = e.member_id AND s.event_type = 'membership_started'));
 member_id | first_name | last_name |              email               | date_of_birth | home_branch_id | joined_on  | membership_tier | status
-----------+------------+-----------+----------------------------------+---------------+----------------+------------+-----------------+--------
      1031 | Ella       | Nelson    | ella.nelson1031@example.com      | 1958-02-14    |              7 | 2021-04-03 | basic           | active
      1132 | Jacob      | Hill      | jacob.hill1132@inbox.example.net | 1975-05-20    |              4 | 2021-12-09 | premium         | active
(2 rows)



**Severity: 3 **

**Reports affected:**

**Likely cause:**

### 2. Uppercase `CHECK_IN` events at branch 4

**What it is:** The events table contains both `check_in` and uppercase `CHECK_IN` event types. The uppercase form appears only at branch 4 and only from device D04-IN, during one week in April 2024.

**Evidence:** 73,913 lowercase `check_in` events vs 181 uppercase `CHECK_IN` events. All 181 uppercase rows are from branch 4, device D04-IN, between 2024-04-08 and 2024-04-14. All 181 later have a check-out for the same member at the same branch under the loose matching check.

**Severity:**

**Reports affected:** Any report filtering only on lowercase `check_in` would miss these 181 branch 4 visits unless it handles the uppercase form.

**Likely cause:**

### 3. Check-in and check-out totals do not reconcile

**What it is:** There are more check-in events than check-out events. This is a reconciliation gap that needs to be explained by the more specific pairing findings below.

**Evidence:** 73,913 lowercase `check_in` events vs 73,205 `check_out` events, a difference of 708 before the 181 uppercase `CHECK_IN` events are considered.

**Severity:**

**Reports affected:**

**Likely cause:**

### 4. Events reference members missing from the members table

**What it is:** Some events point to member IDs that do not exist in the `members` table. That breaks the member-to-events relationship because those events cannot be tied back to a member profile.

**Evidence:** Events exist for member_ids 990001 and 990002, but neither ID exists in `members`.

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
