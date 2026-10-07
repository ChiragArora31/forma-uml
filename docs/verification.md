# Verification record

Verified locally on **7 October 2026**, using macOS/Brave for UI tests and a Linux Docker container for packaging. These results distinguish executable local checks from external services requiring credentials.

| Check | Result |
| --- | --- |
| Backend suite (`pytest -q`) | **108 passed** |
| Actual PlantUML engine | All **14 diagram types**, each across **3 revisions**; 42 successful source/render cases |
| Schema and safety validation | Unknown references, duplicate IDs, invalid timelines, source injection, active SVG content, invalid syntax, and missing renderer covered |
| HTTP/session/storage boundaries | Fresh requests, immutable updates, stale-write protection, retry IDs, foreign-session denial, feedback linkage, and ZIP content covered |
| Live LangChain path | Real SDK with mocked HTTP transport: structured generation, prior-design/feedback context, malformed-output repair, sanitized provider failure |
| ART integration | Actual installed ART LangGraph wrapper captures a LangChain completion and log probabilities from a fixture transport; model/trajectory/backend API contract verified |
| Training data path | Context-preserving export, sample exclusion, retryable delivery, atomic worker claim, and unknown-outcome reconciliation covered |
| PostgreSQL | 37 API, admission, and workspace boundary tests against a disposable local PostgreSQL database; hosted Neon persistence smoke passed across app instances |
| Generation admission | Shared owner/global leases, exact-request release, and stale lease expiry covered |
| Frontend | TypeScript check, production build, Prettier check: passed |
| Browser | **7 production-server journeys passed**: full review flow, mobile/error handling, locally bundled API docs under the content security policy |
| Accessibility | Zero axe violations in the scanned welcome, generated workspace, and review dialog views |
| Vercel hosting | Public production health and real rendering verified; all 7 browser journeys also passed on Vercel with Neon persistence |
| Container | Image builds with locked dependencies, checksum-verified PlantUML, non-root execution, and local host binding; generation/export smoke test passed |
| Dependency check | npm audit reported zero vulnerabilities at verification time |
| Original workspace | Existing `agent-orchestrator` checkout left unchanged |

## Browser journey details

The complete browser test requests all fourteen views and checks that every image loads. It then exercises both prescribed sample revisions, inspects changes and assumptions, saves a review, previews valid edited source, rejects invalid syntax and an include directive, downloads a ZIP, reloads the design, revisits an older revision, and enters/exits the expanded canvas. It checks for unhandled browser errors.

The mobile test checks a 390-pixel layout for horizontal overflow, keyboard dismissal of guidance, an honest unsupported-sample error, and preservation of the user's draft after failure. A third test verifies self-hosted interactive API documentation works under the app's production CSP.

Automated accessibility results apply to the specific scanned views; they are not a claim of exhaustive accessibility certification.

## Measured sample-render latency

The original local cold/warm benchmark, before the bundled case-study preload, recorded all fourteen curated SEBI views:

| Run | Design | Rendering | Cache hits |
| --- | --- | --- | --- |
| Cold | 1 ms | 5,971 ms | 0 / 14 |
| Warm | 7 ms | 5 ms | 14 / 14 |

Reproduce with `uv run python -m scripts.benchmark` after setup. These are deterministic-fixture observations, **not live model latency**, service-level commitments, or a statistical benchmark. The warm run measures exact-source reuse. The Docker two-view smoke run recorded 1.9 seconds total; hardware, process startup, diagram complexity, and load affect these numbers.

## External verification limits

**Real Gemini generation was executed** on a dedicated Free-tier project with billing disabled. Generated SEBI and generic document-processing architectures passed strict validation and all fourteen actual PlantUML projections. A hosted arbitrary document-processing brief produced 14 verified views in 32.8 seconds (7.9 s design, 24.9 s render), and its live refinement produced four verified views in 22.5 seconds. Both completed on their first model attempt. The real refinement trace contains the previous architecture and saved review. Public exports, PostgreSQL history/reviews, queued ART payloads, and foreign-session denial were checked across the staged and promoted app. The assignment SEBI brief was then verified on the public app in live mode: 14 views in 34.8 s, durable-queue refinement in 15.2 s, and officer-approval refinement in 12.3 s; all three immutable revisions reloaded successfully. These observations do not guarantee architectural correctness or unlimited provider availability.

**No GPU training was executed:** a W&B Training credential/account was not supplied. The ART adapter and durable feedback path are tested; no trained checkpoint or measured model improvement is claimed. The explicit training command requires the configured backend and judge credentials. Promotion of a resulting checkpoint is a separate documented step.

The default no-key sample deliberately remains labelled as curated data. It cannot substitute for evaluating arbitrary real prompts against a configured provider.

## Expanded control checks

The browser suite also covers workspace renaming, archive/undo/restore, saved drafts after reload, mobile history and new-design access, live/case-study selection, starter briefs, recommended/all-view selection, cancellation, canvas keyboard movement and zoom, clipboard copy, exact edited SVG and PNG contents, blank-source validation, source reset, Markdown review briefs, and controlled export failures. The source-export test verifies the PNG file signature and that the SVG contains the edited label. Added dialogs receive axe scans.

Ordinary automated tests use fixture transports rather than live inference. Real provider checks are explicit manual deployment verification, with no paid credits or training purchases. Rendering checks are run without competing Java-heavy jobs to avoid artificial CPU contention.


## Reviewer workflow and output refinement

The simplified entry screen, visible Send action with validation guidance, collapsed generation options, and single UML view selector passed all seven production-server browser journeys. Backend checks passed **108 tests** and the disposable PostgreSQL boundary suite passed **37 tests**. The GitHub verification workflow passed for runtime commit `529e17e`.

Real Gemini 3.5 Flash Lite generation with medium reasoning and bounded requirement review was exercised on payments orchestration, document processing, clinic scheduling, and tenant-scoped retrieval. Payments and clinic designs passed the automatic review on their first candidate. Document and retrieval designs exercised reviewed correction; the final reviews reported no missing requirements, critical contradictions, or structural issues. These are model review observations rather than a benchmark or proof of correctness. The document design rendered all 14 actual projections; clinic and retrieval rendered sequence, activity, and lifecycle views. An approval refinement preserved every original document requirement verbatim and rendered those three views.

The staged hosted SEBI brief produced all **14 verified UML views in 30.3 seconds**, including 9.8 seconds for architecture generation and requirement review. Deployment checks also cover refinement, saved feedback, portable exports, and readability of designs from the previous release. Public aliases were pinned to the previous verified deployment throughout staging. Google billing remains disabled; no GPU training or paid provider purchases were performed.


After promotion, both existing public aliases served the same tested build. All **seven public browser journeys passed** on the simplified interface, including the complete 14-view flow, both sample refinements, review persistence, source preview/error paths, downloads, reload, mobile controls, and API documentation. The hosted live SEBI refinement retained the original requirements, produced four verified views in **16.2 seconds**, and its saved history and automatic review remained readable after promotion. Existing live designs from the previous deployment also reloaded successfully.
