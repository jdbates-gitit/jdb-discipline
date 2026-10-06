# Daily Discipline morning freshness controller — LOCAL DRAFT

Not deployed. No credentials or notification provider have been configured.

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
7. At 6:30 a.m., send a stale-page alert through the approved webhook if needed.

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
target, not a service-level guarantee. Existing GitHub cron attempts remain backup.

The seven fixed opening questions repeat weekly ONLY when AI is unavailable.
Source-reading selection and the existing 56-day exclusion still run normally.
Fallback Confluence is explicitly a reflection prompt, not invented interpretation.
Missing/corrupt local source files remain hard failures; never fabricate scripture.

## Permissions and approval needed before activation

- A new, expiring fine-grained GitHub token restricted to `jdb-discipline`, with
  **Actions: write** and automatically required metadata access. This permission
  can do more than dispatch (for example cancel/disable Actions); GitHub does not
  provide a dispatch-only fine-grained scope. Do not grant Contents write,
  administration, other repositories, or reuse a broad personal token.
- Store it as the Cloudflare Worker secret `GITHUB_TOKEN`, never in source,
  Wrangler vars, chat, or logs. Public content reads are unauthenticated and do
  not require a Contents permission. Review token expiration/rotation.
- Choose the actual notification service and recipient, approve it, and store
  its HTTPS JSON webhook destination as secret `ALERT_WEBHOOK_URL`. The payload
  contains only the public site URL, date, and status — no readings or notes.
- Confirm that the provider accepts the documented JSON payload. A generic
  webhook is not automatically an email/text integration. A missing webhook
  raises a logged failure at the deadline; **logs alone are not a user alert**.
- Alerts are attempted on stale checks from 6:30 through 6:45, including late
  delivery. The payload carries a per-day Idempotency-Key header; the selected
  provider must support it for once-per-day delivery. Otherwise two checks or
  duplicate Cron events can send duplicate alerts. Review Cron punctuality
  during acceptance. No outbound provider writes have been performed locally.
- Review the Cloudflare account/plan and costs before deploying the Worker.
- Approve publication of generator/workflow changes and the Worker separately.
  No DNS or Pages project changes are expected.

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

Worker API types inspected: `@cloudflare/workers-types` 5.20261006.1;
Wrangler configuration fields checked against its current published JSON schema.
The GitHub run response is bounded to 2 MiB (100 actual run records can exceed
1 MiB); HTML responses are bounded to 512 KiB. Check CPU usage on the actual
account plan during the runtime trial rather than assume the free-plan budget.
Worker runtime integration testing remains an activation prerequisite; these
dependency-free Node tests cover logic and Web APIs, not the deployed runtime.
