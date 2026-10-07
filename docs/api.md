# API reference

Interactive documentation is at **`/docs`** when the API runs. Most routes require the anonymous session cookie issued by `GET /api/session`. Mutations also require `X-Forma-Request: 1`. A session cookie is a bearer capability for that browser workspace; do not share it.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/session` | Create/reuse session; return mode, catalog, sample brief and updates |
| GET | `/api/health` | Readiness of database schema, Java/Graphviz, and renderer jar |
| GET | `/api/conversations` | List this session's active designs; `?archived=true` lists archives |
| GET | `/api/conversations/{id}` | Complete versioned conversation |
| PATCH | `/api/conversations/{id}` | Rename or reversibly archive a session-owned design |
| GET | `/api/allowance` | Remaining free live-generation attempts |
| GET | `/api/revisions/{id}/report` | Standalone Markdown design-review brief |
| POST | `/api/generate` | Generate and commit a complete revision; SSE result |
| POST | `/api/render` | Validate edited source and return a local SVG preview |
| POST | `/api/feedback` | Save feedback and training outbox atomically |
| GET | `/api/revisions/{id}/feedback` | Reviews and training status for this session's revision |
| GET | `/api/revisions/{id}/export` | ZIP of sources, SVGs, model, metadata, design-review brief, and review snapshot |

## Minimum generation request

```bash
curl -c /tmp/forma-session http://127.0.0.1:8018/api/session
curl -N -b /tmp/forma-session \
  -H 'Content-Type: application/json' -H 'X-Forma-Request: 1' \
  -d '{"prompt":"A software design brief of at least 10 characters", "diagram_types":["sequential","component"]}' \
  http://127.0.0.1:8018/api/generate
```

Use live mode for this arbitrary example. Sample mode accepts the SEBI brief returned by `/api/session`.

Optional `mode` is `live` or `sample`; omission uses the server default. On a live server, `sample` explicitly selects the curated SEBI fixture without a model call. Curated refinements cannot be applied to an existing live design.

Optional `request_id` is a UUID; the server supplies one if omitted. The UI always supplies one so a repeated action can return the original result without duplicating it. A reused ID with different request contents fails with 409. Diagram aliases: `sequential` → `sequence`, `state` → `state_machine`, and `usecase` → `use_case`; duplicate normalized types are removed.

Canonical values: `sequence`, `component`, `class`, `object`, `composite_structure`, `deployment`, `package`, `profile`, `use_case`, `activity`, `state_machine`, `communication`, `interaction_overview`, and `timing`.

## Update an existing conversation

```json
{
  "prompt": "Decouple circular ingestion from analysis using a durable queue, with retries and a dead-letter queue.",
  "diagram_types": ["sequence", "component", "activity", "state_machine"],
  "conversation_id": "<UUID from the first result>",
  "base_revision": 1,
  "request_id": "<fresh UUID for this action>"
}
```

Updates take the latest complete architecture and previous reviews as context. The base revision must equal the current latest revision. Changing selected views accompanies a design request; it does not silently reinterpret old revisions.

## Stream contract

The response is `text/event-stream` with JSON `data` payloads:

```text
event: phase
data: {"phase":"design","message":"Building a shared system model"}

event: phase
data: {"phase":"render","message":"Compiling and verifying UML syntax"}

event: complete
data: {"id":"…","conversation_id":"…","number":1,"architecture":{…},"diagrams":[…],"timings":{…}}
```

An `event: heartbeat` is sent during longer work to keep the connection alive.

Boundary errors before streaming use normal HTTP codes. A runtime failure after response headers have been sent uses `event: error` with `message` and `request_id`; the client must inspect events rather than interpret HTTP 200 as success. A completion means all requested views were validated and the revision transaction committed. A disconnect can occur after commit; retry the exact same request ID or reopen the conversation.

## Feedback

```json
{
  "revision_id": "<saved revision UUID>",
  "rating": 4,
  "comment": "The boundaries are clear. Require officer sign-off before publishing.",
  "diagram_type": "component",
  "request_id": "<UUID>"
}
```

`rating` is an integer from 1 to 5. `diagram_type` is optional: omit it for the full design. A selected diagram must exist in the reviewed revision. Feedback is distinct from an update request and does not create a diagram revision. A repeat with the same ID is idempotent.

The returned `training_status` initially reads `queued`. The feedback is durable; this value does not mean the model has been trained.

## Source preview

```json
{ "source": "@startuml\nAlice -> Bob: A message\n@enduml" }
```

Successful previews return `{ "svg": "…", "validated": true, "cache_hit": false }`. Validation/unsafe source errors return HTTP 422. Includes, macros, URLs in diagram links, and active embeds are disabled. This route does not modify a saved revision.

## Workspace management

`PATCH /api/conversations/{id}` accepts `{ "title": "My design" }` or `{ "archived": true }`; restore with `{ "archived": false }`. The session owner and mutation header are enforced. A workspace rename persists across generation without rewriting a blueprint’s original title. Archiving retains all revisions and feedback; restore before adding a revision.

Live attempts reserve a shared daily allowance before model work. Completed idempotent replays and sample requests do not reserve another attempt. Failures retain the draft but conservatively consume the reserved attempt. Read `/api/allowance` before offering new live work.
