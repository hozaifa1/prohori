# COOL benchmark results

Start with `20261025T002750Z/REPORT.md` (verified facts, invariance ladder, speed, cost, crash and workaround, what would make COOL pay, threats to validity).
Protocol and reproduction commands: `research/COOL_NOTES.md`.  `ledger.tsv` lists every EC2 instance launched for this study (2.198 instance-hours, about $0.37).

Layout of a run folder: `<instance type>/<build>/<build>.bench.json` (raw timings, sweeps, microbench, per-function profile), `<build>.inv.json.gz` (every result leaf as float64 hex), `<build>.build_info.txt`,
`evidence/` (COOL verification, cmake commands), `extras/` (cProfile, variants, crash matrix), `analysis/` (pairwise comparisons), `bug_connectedcomponents/` (draft bug report and repro), `pareto.png`, `cost_table.csv`.
