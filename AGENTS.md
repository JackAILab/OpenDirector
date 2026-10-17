# VisualAgent Rules

- Keep `Task → Agent → Runner → Tool/Model → Observation → Trajectory → Evaluator` boundaries explicit.
- Put provider adapters in `harness/models`; expose bounded agent actions in `harness/tools`.
- Never store API keys, credential values, base URLs, signed temporary URLs, raw provider payloads or personal data in trajectories.
- Paid generation must be explicit, non-overwriting and never silently retried with changed parameters or another model.
- Generated live-commerce plates must be visually rich, layered and commercially legible; clean plate does not mean empty scene.
- Models generate people, products, physical sets, lighting and motion. Code renders all readable UI, comments, counters, prices, buttons, cards and captions.
- Keep `training_eligible=false` until technical QA, independent semantic/visual review and explicit human approval pass.
- Historical files live only on the remote archive branch `archive/pre-agent-system-reset-20260819`; do not copy them back into the active tree.
