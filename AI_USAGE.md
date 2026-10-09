# AI Usage

## Tools used

I worked with one AI assistant (Muse, by Meta) in a chat session. It never
connected to my database. Every SQL statement below ran in my own local
PostgreSQL 18 (database `fittrack`) in psql or in the suite, and every number
in DATA_QUALITY.md comes out of my runs.

## What the AI did

- Drafted SQL on request: evidence queries for the findings, the
  `visits_per_branch` report query, and the check queries behind the test
  suite.
- Drafted the test suite script (`tests/run_data_quality.py`) from the list of
  checks we had agreed on.
- Proposed structure and wording for DATA_QUALITY.md (severity scale, finding
  template, root-cause grouping) and the README.

## What was mine

- All counting decisions: case-insensitive `check_in` matching, deduplication
  by `source_ref` and `event_ts`, next-event pairing for completed visits,
  branch-local calendar year, excluding member IDs missing from `members`,
  and shipping only the one required report.
- Every severity call, every likely cause, and the questions for the CRM and
  access-control owners.
- Verifying each result, including re-running the cancelled-membership query
  grouped by visits (302) instead of members (30).

## Where I corrected the AI

- **Duplicate count.** The AI's duplicate check grouped by `source_ref` alone
  and reported 1,779 groups. My own count was 331. The AI's grouping was
  wrong: devices reuse `source_ref` values, so the check had to group by
  `source_ref` and `event_ts` together. Fixed in both the finding and the
  suite; the suite then reproduced 331.
- **Pairing claim.** An early AI-drafted check showed every uppercase
  `CHECK_IN` had *a* later check-out (EXISTS). That does not prove each
  check-in had its own check-out, so the report uses stricter next-event
  pairing instead.
- **Report total.** A draft total of 71,899 for `visits_per_branch` did not
  match my own run (70,824). I kept my number; the difference is the stricter
  pairing rule.
- **Scope.** The AI drafted all three bonus reports. I skipped them: one
  required report done well, inside the stated time, beats three done thin.

## How generated SQL and code were verified

- Every evidence query was run in psql against my local database before its
  count went into DATA_QUALITY.md.
- The suite was run end to end locally. Its output line up with the report
  (302 blocking, warnings 331, 115, 1,424, 2, 181, 828, 889) and it exits 1,
  as designed, on this dataset.
