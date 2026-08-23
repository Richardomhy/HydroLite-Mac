# Water Environment Source Accounting (M9A)

M9A is the first formal water-environment foundation in HydroLite. It inventories evidenced pollution sources and records generated load, treated/removed load, and net-emission load for CODMn, NH3-N, TN, and TP.

> 当前水环境能力仅完成污染源清单和产生/净排放负荷核算，尚未模拟污染物入河输移和河流水质过程。

## Evidence and semantics

- Every quantified record links source, activity, factor, treatment, units, evidence tier, uncertainty, and provenance.
- Missing activity or a missing/unapproved factor remains missing; it is never filled with zero or a generic coefficient.
- Example factors are schemas only and are blocked for real projects by default.
- `generated_load - removed_load = net_emission_load` is the M9A mass-balance gate.
- Net-emission load is not mobilized, delivered, river-input, or section load. No source-apportionment or river-concentration claim is made.

## CLI

Run the real-project workflow once with an explicit read-only source path:

```bash
python -m hydrolite water-environment inventory --source-root <real-project-source>
```

Then inspect the generated M9A outputs:

```bash
python -m hydrolite water-environment status
python -m hydrolite water-environment factors
python -m hydrolite water-environment ledger
python -m hydrolite water-environment validate
python -m hydrolite water-environment report
```

Outputs are written below `output/water_environment/m9a/` and are ignored by Git. Real source files are read in place and are not copied into the repository.
