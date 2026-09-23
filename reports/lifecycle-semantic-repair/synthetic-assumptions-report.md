# Static resource-exhaustion analysis report

This report contains static findings only. It does not provide dynamic confirmation or establish a runtime outcome.

## Summary

- P0 families: 0
- P1 families: 0
- P2 families: 1
- Inventory families: 0
- Static vulnerable families: 0
- Bounded under modeled assumptions families: 1
- Static unknown families: 0

## Finding families

| Priority | Family ID | Verdict | Amplification | Reachability | Bound status | Missing evidence / reasons |
|---|---|---|---|---|---|---|
| `P2` | `family:b2ee7e79f6b87c07ec8946ee` | `bounded_under_modeled_assumptions` | `unknown` | `unknown` | `absent` | `A1_SINGLE_OPERATION_NOT_AMPLIFYING`, `A2_BOUNDED_ACCEPTED_TASK_POPULATION`, `BOUND_ABSENT`, `GUARD_ABSENT`, `RELEASE_ABSENT`, `VERDICT_ASSERTIONS_REFUTED` |

## Exact finding audit

| Finding ID | Verdict | Certificate ID | Entry ID | Growth ID |
|---|---|---|---|---|
| `finding:59d303ddd056ce28837c843f` | `bounded_under_modeled_assumptions` | `certificate:11657b82079d4d69592fc07c` | `entry:c777ad1755537647d9afe0ea` | `growth:ba7237d2b8982754e42e4ba7` |

## Coverage and limitations

Coverage is reported from the modeled static-analysis framework set.
- No framework coverage records were supplied.
Limitations: none recorded beyond static-only analysis and modeled assumptions.

## Modeled assumptions in lifecycle certificates

### certificate:11657b82079d4d69592fc07c
- MODELED_DEFAULT_CONFIGURATION
- STATIC_EVIDENCE_COVERAGE_COMPLETE
- a counts reserved or running tasks in the modeled executor
- arbitrary_finite_repetitions_of_external_accept
- derived invariants: 0 <= q <= K, 0 <= a <= W, q + a <= K + W
- each external acceptance denotes a fresh task population member
- proof is inductive for arbitrary finite repetitions, not one unrolling
- q counts accepted tasks in the modeled executor queue
- task phase changes do not create a second population member
