# Daily Discipline morning freshness controller

October 6, 2026 acceptance: encrypted `GITHUB_TOKEN` stored by the owner;
private Cloudflare RPC authenticated to GitHub and validated the live full
edition; guarded `ensure_fresh` run 37568899207 succeeded without changing the
edition. The email test arrived in the approved Gmail inbox with SPF and DKIM
passing. No DNS, billing plan, or Pages configuration changed.

`wrangler.jsonc` is the active controller configuration. `wrangler.setup.jsonc`
is the no-cron setup configuration: deploying it pauses scheduling and enables
same-account, private setup RPC. Setup RPC is disabled in the active config.
`wrangler.probe.jsonc` / `probe-local.mjs` are localhost-only test tools, never
deployment targets. The credential remains in Cloudflare, not in the probe.

The GitHub backups are daily attempts at **4:45 and 5:45 a.m. America/Chicago**.
The 5:45 attempt is a temporary second backup approved October 7 while Cloudflare
timer delivery is investigated. Both use the complete-page gate; an already
fresh edition is left unchanged, with no additional AI generation. Review removal
of the temporary backup after real scheduled executions have been verified.
The October 7 controlled real-cron test produced no observed execution after
nearly 17 minutes; its temporary test trigger was removed. The guarded recovery
published the complete October 7 edition, but did not establish timer reliability.
Morning punctuality still needs observation; acceptance tests do not establish
a before-7 service-level guarantee.

## What it does

Cloudflare wakes the controller every 15 minutes during a broad UTC window.
The controller uses America/Chicago wall-clock time, automatically accounting
for daylight saving. It acts only from **1:15 through 6:45 a.m. Houston time**.

1. Read the custom domain, bypassing ordinary browser/cache reuse.
2. Require today's freshness contract AND three nonempty source readings,
   the opening question, Confluence, Notice/Surrender/Act, evening question,
   Seven-Day Trail, and a complete HTML document.
3. If the live page is fresh, do nothing. A fixed-prompt fallback is fresh but
   is recorded distinctly from AI editorial.
4. If GitHub already contains today's complete page, report deployment pending;
   do NOT replace its readings or assume another generation fixes Cloudflare.
5. If any generator run on main is queued/in progress, wait for it.
6. Otherwise dispatch `ensure_fresh` for today's explicit Houston date. Allow
   at most three visible controller attempts per date, at least 45 minutes apart.
   Earliest attempt slots are **1:15, 3:15, and 5:15 a.m.**; later slots are
   reserved so a brief overnight outage does not exhaust every attempt early.
7. At 6:30 a.m., send a stale-page email to the approved inbox if needed.

No public HTTP trigger: all requests return 404, workers.dev/preview URLs are
disabled, and no routes or custom domains are attached. This does not run AI
inside Cloudflare and requires neither the Anthropic key nor a Pages/DNS token.

## Retry safety and limitations

GitHub's existing concurrency group serializes generator runs. Controller
dispatches use `RUN_NOW=0`; a second queued attempt skips generation once today's
validated HTML exists. Human `force_refresh` remains an explicit override.
An automatic request delayed into another Houston date exits without generating
the wrong day's reading. The date flag is saved only after successful rendering.

GitHub run listing is not an atomic dispatch lock: duplicate Cron deliveries or
an ambiguous API timeout may enqueue extra no-op jobs before run records appear.
The workflow's serialized page gate prevents extra AI generation; the three-run
limit is a best-effort cap on visible attempts, not an absolute distributed lock.
This deliberately avoids adding a database or Durable Object for this small job.

A repo-fresh/live-stale result needs deployment or domain investigation, not
repeated content generation. A stuck active run is not cancelled automatically.
The 10-minute workflow timeout bounds running jobs, not time spent queued.
Provider outages and build failures can still miss 7 a.m.; this is a reliability
target, not a service-level guarantee. Two GitHub cron slots provide backup
attempts while the Cloudflare timer issue remains unresolved, not independent
protection against a GitHub-wide outage.

The seven fixed opening questions repeat weekly ONLY when AI is unavailable.
Source-reading selection and the existing 56-day exclusion still run normally.
Fallback Confluence is explicitly a reflection prompt, not invented interpretation.
Missing/corrupt local source files remain hard failures; never fabricate scripture.

## Credentials and alerts

- A new, expiring fine-grained GitHub token restricted to `jdb-discipline`, with
  **Actions: write** and automatically required metadata access. This permission
  can do more than dispatch (for example cancel/disable Actions); GitHub does not
  provide a dispatch-only fine-grained scope. Do not grant Contents write,
  administration, other repositories, or reuse a broad personal token.
- Store it as the Cloudflare Worker secret `GITHUB_TOKEN`, never in source,
  Wrangler vars, chat, or logs. Public content reads are unauthenticated and do
  not require a Contents permission. Review token expiration/rotation.
- `ALERT_EMAIL` is a native binding restricted to `jdbates@gmail.com`, sent
  from `discipline-alerts@jdb-builds.com`. It uses existing ready Email Routing
  and the verified destination; no paid Email Sending onboarding is needed.
  Alert content is only the public site URL, date, and status, never readings,
  personal notes, or the GitHub credential. There is no alert when fresh.
- Alerts are attempted on stale checks from 6:30 through 6:45, including late
  delivery. Persistent failure may produce two emails (or duplicates after
  duplicate Cron delivery); no durable exactly-once email outbox is claimed.
  The optional webhook path retains its per-day Idempotency-Key header, but
  the native email path does not claim that header as a deduplication guarantee.
- Owner-selected token expiration is October 6, 2027; renew before expiry.
- Cloudflare runtime testing caught unsupported `redirect: "error"`. Requests
  now use `manual` and reject all non-2xx responses, including redirects, without
  following or forwarding credentials. Dependency-free Node tests alone did
  not reveal this runtime incompatibility.

## Local checks (no installs, secrets, AI calls, or deployments)

```powershell
node --test scheduler/tests/worker.test.mjs
node --test tests/practice.test.cjs
# Use the available Python runtime:
python -X utf8 -B -m unittest discover -s tests -p 'test_*.py'
# Optional: choose a new file outside the production index:
python -X utf8 -B scheduler/build_preview.py --output C:\path\to\new-preview.html
```

Tests use fake fetch responses only. Production activation acceptance must also
include one real ensure_fresh run, live-domain contract verification, approved
notification delivery, a repeated no-op run, and inspection on several mornings.
Do not mark before-7 reliability achieved from local tests alone.
Matching local landing-card and generator-footer copy describes the labelled
AI-failure fallback. Publish that copy alongside activation; do not promise an
achieved before-7 service level on the public card before observing it.

## References checked October 6, 2026

- [Cloudflare Cron](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
- [Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/)
- [GitHub dispatch and permissions](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
- [Public content reads](https://docs.github.com/en/rest/repos/contents#get-repository-content)

Worker API types inspected: `@cloudflare/workers-types` 5.20261007.1;
Wrangler configuration fields checked against its current published JSON schema.
The GitHub run response is bounded to 2 MiB (100 actual run records can exceed
1 MiB); HTML responses are bounded to 512 KiB. Check CPU usage on the actual
account plan during the runtime trial rather than assume the free-plan budget.
Private Cloudflare runtime setup checks passed; first scheduled execution and
multi-morning punctuality remain to be observed. Dependency-free Node tests
cover logic and Web APIs, not the deployed runtime by themselves.
