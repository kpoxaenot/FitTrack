# FitTrack Data Quality Assignment

Data-quality work on the FitTrack gym database (Postgres): membership and
access-control events for 8 branches.

Findings, evidence, and severity are in [DATA_QUALITY.md](DATA_QUALITY.md).
How AI tools were used is in [AI_USAGE.md](AI_USAGE.md).

## Contents

- `reports/visits_per_branch.sql`: member visits per branch for 2024, one row
  per branch. Standalone query, runs read-only with `psql -f`.
- `tests/run_data_quality.py`: the data-quality test suite.
- `DATA_QUALITY.md`: findings report.

## Run the report

```bash
psql -f reports/visits_per_branch.sql
```

Connection details come from the standard `PGHOST`, `PGPORT`, `PGDATABASE`,
`PGUSER`, `PGPASSWORD` environment variables (or a connection string argument
to psql). The query is a single SELECT and needs no helper objects.

## Run the test suite

Requires Python 3 and the driver once:

```bash
pip install "psycopg[binary]"
```

Then, with the same `PG*` environment variables set:

```bash
python tests/run_data_quality.py
```

The suite prints one line per check with expected vs actual. Exit code is 1
when a baseline or Sev-1 (blocking) check fails, and 0 otherwise; Sev-2 and
Sev-3 failures print as warnings. All checks are read-only and state invariants
(zero violations), not this dataset's counts, so the suite runs against any
database with the same schema.

On the delivered dataset the suite exits 1, with one blocking failure (302
check-ins while membership was cancelled) and seven warnings. Those are the
known issues documented in DATA_QUALITY.md, not suite errors.

## Time spent

About 7 hours over October 8 and 9, 2026:
- environment setup
- data exploration and checks
- the findings report
- the report query
- this suite
