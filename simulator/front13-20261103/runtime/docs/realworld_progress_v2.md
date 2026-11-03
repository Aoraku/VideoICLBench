# RealWorld50 v2 private progress scorer

`videoicl_isaaclab.realworld_progress.score_progress(task, variant, observation, *, initial_observation=None, history_valid=True)` implements the 50 task-specific rubric formulas from `VideoICLBench/docs/evaluation/realworld50-score-design-v2.json`.

The returned `task_score_100` is **raw before the native-success gate**. It does not promote native success, change `success`, or average checker conditions. The integration layer must preserve the binary success measure and separately apply validated native success / `min(raw, failure_ceiling_100)` on failure. Exact rational numerators/denominators are included for the raw score and failure cap. `units` records the contributing task milestones and explicit violations. `native_physics_verified=False` states that this pure function does not certify physics.

The argument accepts either a private observation or the native envelope:

```
{
  "schema": "videoicl-native-progress-evidence-v2",
  "task": "E05", "variant": "A", "history_valid": true,
  "observation": {...},
  "object_status": {"cube": {"released": true, "stable": true, "supported": true}},
  "initial": {"observation": {...}, "object_status": {...}}
}
```

A standalone observation uses `progress_physical` for the same per-object map. Envelope task/variant must match the call. A missing field, malformed evidence, invalid history or a zero required-change denominator yields `task_score_100=null`, `progress_available=false`, and `missing_evidence`. Explicitly measured absence (empty membership, false predicate, no target region or no release yet) yields numeric zero or the remaining valid milestones, never fabricated success. Do not pass actor-provided records into this API.

Partial-state fields added alongside the legacy native checker observations:

- E03: `progress_nested_pairs` contains every measured nesting edge; `outer_supported` contains the cups directly supported on the table.
- E07: `nonoverlap_pairs` maps rank pairs such as `1|2` to booleans; `rank_label_map` connects ranks and status IDs.
- E11: `object_cells` maps original IDs to `[row, column]`, even before the grid is filled.
- E18: `drawer_opened_for_access` and `drawer_closed_after_delivery` derive from measured joint/event history.
- E22: `object_sides` preserves each block's car-relative region.
- E29: `pending_strikes` retains begun but unreleased actual impacts; an extra pending strike can invalidate the last full-sequence unit.
- E37: `screw_progress` maps screw roles to witnessed current legal loosening.
- E39: `reference_changed` records an actual reference disturbance.
- E41: `extension_object_ids` preserves distinct actual spare identities; `progress_supported_rows` gives row-local support.
- E43: release and trajectory samples carry the same `release_id`; `launcher_moved` is measured. No release is represented by `release=null, trajectory=[]`.
- E28/E42/E45/E46/E50: `progress_causal[object_id]` has `transport_achieved`, `delivery_chain_valid`, and E45 `poured_exit_valid`. E50 also requires `clip_grip_achieved` and `clip_return_after_delivery`. These fields must come from the per-tick causal adapter, not a best historical trace patched onto an unrelated final pose.

For E07/E09, initialize and lock a settled initial snapshot before model actions. E39 uses frozen original positions/yaws. The initial denominator must be the same for matched real/sim/text runs; it must not be inferred from the terminal state or allowed to change while a run is active.

Tests in `tests/test_realworld_progress.py` use synthetic semantic fixtures. They cover all 150 task variants with full and zero outcomes, missing evidence, invalid histories, dynamic denominators, wrong events, over-counts, causal invalidation and terminal rollback. They are not native positive/negative physics acceptance. No model/API/GPU execution is performed by this test suite.

Initial admission writes per-room pre-seal/post-settle native evidence before raising any room error. Only E07/E09/E39 require settled actors relevant to their dynamic denominator (blocks, pieces, and original reference actors respectively); other tasks preserve actual `stable=False` values in the frozen baseline rather than adding a new global admission condition. Native history/errors and the existing `source_initial_state` guard remain mandatory for every task. The pool permits at most two additional seconds of real pre-agent physics for unsettled denominator actors (configurable 0–10 seconds), with no reset, relocation, or resampling. Actor-level diagnostics and exact extra tick counts are saved privately.
