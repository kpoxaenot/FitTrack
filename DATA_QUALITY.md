<# FitTrack Data Quality Report

_Assignment: Senior QA Engineer (Data Quality), NIBBANA. Database: Postgres, `fittrack`._

## What this report covers
The FitTrack database collects data from two systems across 8 gyms in 4 time zones:
the CRM (memberships) and the access-control system (turnstiles and front-desk tablets).
This report lists the data-quality issues found in the delivered data set, the evidence
for each, and what they do to the management reports built on this data.

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


1. 1,122 members vs 1,120 membership_started events:  membership never started for member_ids 1031,1132
2. CHECK_IN event_type exists in the event table and is sometimes used by branch_id 4. as opposed to check_in used normally
3. 73,913 lowercase check_in vs 73,205 check_out events
4. members do not exist in membershit table: member_ids 990001, 990002
5. 828 rows in events where  member_id in (990001, 990002) who do not exist in members table. Almost perfectly even across all branches; test/probe accounts? 
6. 115 have no later check-out at all and 1,424 aren't followed by a check-out as the next event, across all branch_ids
7. 331 same-second check_ins per same members
8. 30 visits by people whose membership was cancelled at the time

## Issue 1: Start of Membership activity lost
#
**What it is:** 
**Evidence:**

