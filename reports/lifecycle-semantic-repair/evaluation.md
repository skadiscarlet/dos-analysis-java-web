# PoC-33 21-Library Demo Evaluation

## Infrastructure

- targets: 21/21 completed
- selected queries: 168
- query diagnostics: 0
- skipped queries: 0

## Known-case oracle

- formal static_vulnerable matches: 0/33 (0.0)
- supported-chain subset: 20/29 (0.689655)
- explicit deferred: 4

## Formal predicted positives

- predicted_positive_families (static_vulnerable, deduplicated): 0
- analysis_unknown_families: 126
- bounded_families: 0
- reviewed TP / FP / unreviewed positives: 0 / 0 / 0
- novel positives outside the oracle records: 0
- confirmed precision TP/(TP+FP): None
- conservative precision lower bound TP/(TP+FP+unreviewed): None
- precision_review_status: not_evaluable_no_positive
- precision threshold: 0.8 (proposed_default)
- FPR: not_measured

## Dynamic case taxonomy

- eligible positives: 6
- hard negatives: 15
- weak negatives: 25
- unscored: 3

## Static gates

- ordinary positive recall subset: 0/6 (0.0)
- hard-negative not-static_vulnerable (legacy, not a bounded proof): 15/15 (1.0)
- hard-negative determined bounded: 0/15 (0.0)
- hard-negative split: determined_bounded=0, analysis_unknown=0, false_positive=0, extraction_failure=0, unmatched_static_evidence=15

## Historical queue score

- raw analyzed rows (not review queue): 126
- historical finding-level TP / FP / blocked: 0 / 0 / 0
- historical precision TP/(TP+FP): None

Unknown families are not review positives. Dynamic evidence is used only for this post-hoc evaluation; it does not rewrite static artifacts.
