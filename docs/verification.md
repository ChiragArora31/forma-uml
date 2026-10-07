# Verification record

Verified locally on **7 October 2026**, using macOS/Brave for UI tests and a Linux Docker container for packaging. These results distinguish executable local checks from external services requiring credentials.

| Check | Result |
| --- | --- |
| Backend suite (`pytest -q`) | **72 passed** |
| Actual PlantUML engine | All **14 diagram types**, each across **3 revisions**; 42 successful source/render cases |
| Schema and safety validation | Unknown references, duplicate IDs, invalid timelines, source injection, active SVG content, invalid syntax, and missing renderer covered |
| HTTP/session/storage boundaries | Fresh requests, immutable updates, stale-write protection, retry IDs, foreign-session denial, feedback linkage, and ZIP content covered |
| Live LangChain path | Real SDK with mocked HTTP transport: structured generation, prior-design/feedback context, malformed-output repair, sanitized provider failure |
| ART integration | Actual installed ART LangGraph wrapper captures a LangChain completion and log probabilities from a fixture transport; model/trajectory/backend API contract verified |
| Training data path | Context-preserving export, sample exclusion, retryable delivery, atomic worker claim, and unknown-outcome reconciliation covered |
| Frontend | TypeScript check, production build, Prettier check: passed |
| Browser | **3 production-server journeys passed**: full review flow, mobile/error handling, locally bundled API docs under the content security policy |
| Accessibility | Zero axe violations in the scanned welcome, generated workspace, and review dialog views |
| Container | Image builds with locked dependencies, checksum-verified PlantUML, non-root execution, and local host binding; generation/export smoke test passed |
| Dependency check | npm audit reported zero vulnerabilities at verification time |
| Original workspace | Existing `agent-orchestrator` checkout left unchanged |

## Browser journey details

The complete browser test requests all fourteen views and checks that every image loads. It then exercises both prescribed sample revisions, inspects changes and assumptions, saves a review, previews valid edited source, rejects invalid syntax and an include directive, downloads a ZIP, reloads the design, revisits an older revision, and enters/exits the expanded canvas. It checks for unhandled browser errors.

The mobile test checks a 390-pixel layout for horizontal overflow, keyboard dismissal of guidance, an honest unsupported-sample error, and preservation of the user's draft after failure. A third test verifies self-hosted interactive API documentation works under the app's production CSP.

Automated accessibility results apply to the specific scanned views; they are not a claim of exhaustive accessibility certification.

## Measured sample-render latency

A fresh pipeline rendering all fourteen curated SEBI views on this machine recorded:

| Run | Design | Rendering | Cache hits |
| --- | --- | --- | --- |
| Cold | 1 ms | 5,971 ms | 0 / 14 |
| Warm | 7 ms | 5 ms | 14 / 14 |

Reproduce with `uv run python -m scripts.benchmark` after setup. These are deterministic-fixture observations, **not live model latency**, service-level commitments, or a statistical benchmark. The warm run measures exact-source reuse. The Docker two-view smoke run recorded 1.9 seconds total; hardware, process startup, diagram complexity, and load affect these numbers.

## External verification limits

**No remote model generation was executed:** a provider credential was not supplied. The live path is implemented and integration-tested with realistic mocked provider responses, but real provider access, model output quality, latency, and billing are unverified.

**No GPU training was executed:** a W&B Training credential/account was not supplied. The ART adapter and durable feedback path are tested; no trained checkpoint or measured model improvement is claimed. The explicit training command requires the configured backend and judge credentials. Promotion of a resulting checkpoint is a separate documented step.

The default no-key sample deliberately remains labelled as curated data. It cannot substitute for evaluating arbitrary real prompts against a configured provider.
