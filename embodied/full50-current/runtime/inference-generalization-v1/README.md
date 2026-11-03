# Inference generalization v1

Opt-in bindings for the user-supplied `INFERENCE_GENERALIZATION_DESIGN.md`. The source document and private catalog preserve all 50 task definitions: 20 G0, 20 G1, 10 G2, each with A/B/C. E06's prompt says small tangerines, matching its object specification rather than the source prompt's egg typo.

G0 task bindings remain byte-value identical to the original JSON. G1 changes objects while preserving robot and camera configuration. G2 changes objects and selects the separate hash-pinned UR5/WSG and table profile. No video is changed. Existing campaign configurations do not select these bindings automatically.

`catalog.private.json` contains answer relations and acceptance boundaries and must never enter the agent context. The compiler emits `public-prompts.json` containing only the 30 changed tasks' shared A/B/C instructions. Unchanged G0 tasks retain their original instructions. Harbor packages must select these public prompts explicitly and refresh their instruction manifest hashes; the native scene loader independently selects the same opt-in instruction.

Compile after both replacement asset patches exist:

```sh
python runtime/scripts/build_inference_generalization.py \
  --g2-profile runtime/configs/inference-generalization-ur5-wsg-v1.json
```

Output `inference-bindings.json` preserves every original `variants` object, including semantic selection, targets, and initial pose overrides. The compiler refuses missing/repeated tasks, G0 edits, renamed object identities, changed rules, absent asset pins, and G1 environment drift. `binding-compilation-checks.json` records all 50 checks. Asset SHA/geometry verification and native physics validation remain separate acceptance steps; successful compilation does not certify physical solvability.

The six-case engineering wave is exactly E01A/E02B/E38C (G1) and E04A/E06B/E49C (G2), seed 4201, simulation demonstrations, one room per pool and at most two pools per GPU. Explicit deployment bindings select physical cards. New controller per-task robot profile pins must agree with the frozen native specs and plan.

## Explicit E24 rule adaptation

The source cup evaluator required both upright cup axes and a final left-to-right color order. The new document replaces cups with yarn balls and specifies the sequence of actual insertions and closing the lid, without an orientation or lateral layout requirement. Only compiled G1 E24 enables `e24-yarn-insertion-v1`; it drops these two cup-specific restrictions. It retains the exact A/B/C first-insertion sequence, all three named objects inside and supported, released/stable state, and lid closure strictly after the last insertion. Progress remains 25 points per correct insertion plus 25 for the final lid condition. Existing E24 bindings and all G0 behavior retain their old checks.

Final CPU verification: 150/150 recipes loaded with file/dependency SHA verification, and 582 contract/progress/native-evidence/panel regression tests passed. See `recipe-file-validation.private.json` for the compiled binding hash and `semantic-compatibility-audit.private.json` for the 30-task review. These checks do not replace live physics acceptance.
