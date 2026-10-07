# Vercel deployment

Forma runs as a single container-image Vercel Function. `Dockerfile.vercel` builds the React assets and installs the locked Python dependencies, a Java runtime, Graphviz, and the checksum-verified MIT PlantUML jar. It runs as a non-root user and listens on `$PORT` (80 by default). Source and diagrams stay inside the application's renderer.

Containers are stateless. Hosted records belong in PostgreSQL, not the container filesystem. The `/tmp/forma` directory is ephemeral; no session, revision, or feedback persistence depends on it when `DATABASE_URL` is configured.

## Provision and migrate

1. Link the repository to your Vercel project with the Container framework and Fluid Compute enabled.
2. Attach a Neon database on its **Free** plan. Use the pooled `DATABASE_URL` for application requests and `DATABASE_URL_UNPOOLED` for migrations.
3. Pull development configuration into an ignored `.env.local`, then run:

```bash
uv run python -m app.migrate
```

The migration command applies numbered SQL files once, under an advisory transaction lock. It uses the direct connection where available. Runtime startup never attempts a schema migration. Keep existing migration files immutable; add the next numbered file when changing the hosted schema.

4. Configure Production variables:

```dotenv
FORMA_MODE=sample
FORMA_COOKIE_SECURE=true
PORT=80
```

For verified live generation, additionally set `FORMA_MODE=live`, `FORMA_API_KEY`, `FORMA_MODEL`, and the provider's OpenAI-compatible `FORMA_BASE_URL`. The endpoint must support function calling. Use Vercel **Secret** variables for API keys, never browser variables. Vercel Gateway can use OIDC where its token is available to the runtime; container startup must not assume that a development OIDC token is present in production. Do not copy an expiring development token into production secrets.

5. Build a staged production deployment, inspect it, and promote it only after verification:

```bash
vercel deploy --prod --skip-domain
vercel curl /api/health --deployment <deployment-url>
vercel promote <deployment-url>
```

Use `vercel curl` for protected staging URLs. Keep preview protection enabled. The production alias should be checked from an unauthenticated browser before sharing it with a reviewer.

## Free-tier operation

The assignment deployment uses Vercel **Hobby** and Neon **Free**; no paid plan or automatic top-up is required. Vercel currently includes 10 GB/month of container image storage, 4 hours/month of active Function CPU, and 360 GB-hours/month of provisioned memory. These are team allowances shared with other projects. Delete obsolete images when needed and watch the dashboard; exceeding free limits can pause availability. See [Vercel pricing](https://vercel.com/pricing) and [Hobby limits](https://vercel.com/docs/plans/hobby).

Model access is separate from hosting. Sample mode makes no model calls. Vercel Gateway's free credits currently require account verification and support only eligible models. A Gateway budget is a soft cap, not a promise of zero spending. An alternative is an OpenAI-compatible Gemini API endpoint using a project explicitly marked **Free** with billing disabled; confirm the model's free quota before running it. See [Gateway pricing](https://vercel.com/docs/ai-gateway/pricing) and [Gemini billing](https://ai.google.dev/gemini-api/docs/billing).

Keep the ART worker separate from the web deployment. Saving feedback is local database work; it never starts paid inference or GPU training. The explicit training command requires a separately configured backend and should not be run for a zero-spend submission.

## Verification checklist

Check health, anonymous session creation, initial generation, all requested SVGs, two revisions, stale revision rejection, source preview, review persistence, ZIP contents, reload persistence, a fresh browser's access isolation, mobile layout, and API documentation. Check live prompts only after free provider access is configured; a working deterministic sample does not establish live-model quality.

Generation admission is shared across containers using PostgreSQL leases. Render cache, source-preview admission, and lightweight request-rate counters are per instance. A public trial remains an anonymous take-home demo rather than a full multi-tenant account platform. Deployments may cold-start after idle periods.

## Disposable PostgreSQL tests

The `--postgres` test flag connects only to a fixed local test database and truncates its application tables between API tests. It never reads production connection values.

```bash
docker run --rm --name forma-postgres-test -p 127.0.0.1:5438:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=forma-test \
  -e POSTGRES_DB=forma_test postgres:17
# In another terminal, after PostgreSQL is ready:
DATABASE_URL_UNPOOLED=postgresql://postgres:forma-test@127.0.0.1:5438/forma_test \
  uv run python -m app.migrate
uv run pytest tests/test_api.py tests/test_admission.py --postgres -q
```
