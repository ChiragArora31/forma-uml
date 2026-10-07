# The feedback → ART path

The assignment asks for feedback to reach the ART integration of LangChain. The current integration is [OpenPipe ART's LangGraph adapter](https://art.openpipe.ai/integrations/langgraph-integration/), exposed through `art.langgraph.init_chat_model` and `wrap_rollout`. This implementation uses those actual APIs; it does not invent a feedback endpoint that the library does not provide.

## Immediately after a review

The server writes two records in one transaction:

1. Human feedback tied to an immutable revision, optionally scoped to one diagram.
2. A durable outbox payload containing the prompt, previous design, reviewed design, generated diagrams, provider trace/usage, rating, comment, and revision identities.

The normalized rating is `(rating - 1) / 4`. It is a rating on the historical candidate. It is not applied as a reward to new unseen outputs. A sample review is stored and inspectable, but excluded from RL training.

Prior review comments are also supplied as context to the next live revision. This provides an immediate refinement effect without claiming that the model's weights changed.

## Inspect and export

These commands make no remote model calls:

```bash
uv run python -m app.training inspect
uv run python -m app.training export --output .data/feedback-scenarios.jsonl
# Local demonstration only: include deterministic sample reviews in an inspectable export.
uv run python -m app.training export --include-samples --output .data/sample-reviews.jsonl
```

The export is JSONL and owner-readable only. It is repeatable; `exported` does not remove a scenario from eligibility for later training. Keep exports in ignored `.data/`; they contain user designs and potentially proprietary feedback.

## Train fresh on-policy candidates

Requires an ART/W&B Training account and credentials for the semantic judge. Training performs paid remote inference and a model update; it is deliberately a separate explicit command.

```bash
uv sync --frozen --extra training
# Configure FORMA_API_KEY / FORMA_MODEL in .env for the semantic judge.
# Set WANDB_API_KEY in the shell using your secret manager.
uv run --extra training python -m app.training train \
  --name forma-designer --base-model Qwen/Qwen3-8B --limit 2 --rollouts 4
```

The worker:

1. Selects eligible **live** reviewed scenarios.
2. Registers `art.TrainableModel` with `art.serverless.ServerlessBackend`.
3. Claims outbox rows atomically so another worker cannot submit them concurrently.
4. Runs four candidates per scenario through `wrap_rollout`. Within that context, `init_chat_model` accesses the registered trainable model and captures actual model interactions and log probabilities.
5. Uses the same LangGraph generation/compile/render pipeline as the app.
6. Gives an invalid-schema or invalid-render candidate zero reward. A valid candidate earns `0.25 + 0.75 * semantic_score` from a structured judge evaluating coverage, consistency, provenance, and incorporation of actionable criticism.
7. Requires within-scenario reward variation. A no-op group is left queued rather than falsely marked trained.
8. Submits the groups to `backend.train()` with an explicit learning rate.
9. Persists a checkpoint receipt, then marks the claimed feedback `trained` only after completion.

The receipt includes the backend checkpoint step, artifact name, model identifier and inference endpoint, associated feedback IDs, and metrics. Credentials are excluded. Outputs live under `.data/training-runs/` and are ignored by Git.

A failure before remote submission returns the feedback to `queued`. An interrupted or failed local result after remote submission is `needs_reconciliation`: an operator must inspect the named run in the backend before deciding whether to requeue it. Automatically retrying an uncertain update could train twice.

## Use the trained policy for future iterations

Training is not silently connected to the commercial-model alias. Once a checkpoint has been evaluated, configure `FORMA_BASE_URL` and `FORMA_MODEL` using the receipt's inference endpoint and checkpoint identifier, with its authorized serving credential in `FORMA_API_KEY`. Restart the app. Subsequent live iterations then use that policy through the same OpenAI-compatible LangChain boundary.

This explicit promotion keeps an experimental training job from silently replacing the serving model. Keep a held-out set of briefs and compare correctness, latency, and requirement coverage before promoting.

## What has and has not been verified

The optional pinned ART library is installed during integration verification. Its LangGraph adapter, model and trajectory constructors, and training method contract are checked. Local tests verify exact feedback context, sample exclusion, atomic worker claiming, export retryability, reward context, and reconciliation behavior. The commercial generation path is exercised with a realistic mocked OpenAI transport, including malformed-output repair.

Remote training requires user-provided W&B credentials and compute. No GPU training result, improvement percentage, or completed checkpoint is claimed without a successful remote training receipt. A functioning storage/export path alone is not described as completed RL training.

## Next production steps

Add held-out evaluation and checkpoint promotion gates; persist an explicit training-run ledger and reconciliation command; manage retention/consent for human feedback; use a durable scheduler and worker queue; aggregate several independent reviewers to mitigate subjective or malicious rewards. Those are intentionally outside the local take-home scope.
