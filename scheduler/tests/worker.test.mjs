import { test } from "node:test";
import assert from "node:assert/strict";
import worker, { chicagoClock, inspectPage, retryDecision, boundedText, checkAndDispatch, tick } from "../worker.mjs";

const DATE = "2026-10-06";
const NOW = new Date("2026-10-06T06:15:00Z"); // 1:15 a.m. CDT
const ENV = { GITHUB_TOKEN: "test-only-do-not-use" };
const LOG = { log() {}, error() {} };

function page(date = DATE, mode = "ai") {
  const selections = { lead: "tao:1", companion: "epictetus:I", echo: "heraclitus:10" };
  const readings = Object.entries(selections).map(([role, key]) =>
    `<section data-reading-role="${role}" data-selection-key="${key}"><div class="verse"><p>Original reading</p></div>${role === "echo" ? '<p class="echo-note">A note.</p>' : '<div class="movement"><p>A lens.</p></div>'}</section>`).join("");
  return `<html><head><script id="discipline-freshness" type="application/json">${JSON.stringify({ version: 1, date, editorial_mode: mode, selections })}</script></head><body>
<header data-discipline-date="${date}">${mode === "fixed" ? '<p id="editorial-status">Fixed prompts today.</p>' : ''}</header><h2 id="daily-question">What can I carry into today?</h2>${readings}
<section class="confluence"><p>Meeting and difference.</p></section>
<section class="carry"><dt>Notice</dt><dd>What do I see?</dd><dt>Surrender</dt><dd>What can I release?</dd><dt>Act</dt><dd>One honest action.</dd></section>
<details class="return"><div data-note-date="${date}"><p class="night-question">What can I entrust tonight?</p></div></details>
<details class="trail"><summary>Seven-Day Trail</summary><ul class="trail-list"><li><time datetime="${date}">Today</time></li></ul></details><footer>Disclosure</footer></body></html>`;
}

function attempt(minutesAgo = 60, overrides = {}) {
  return { head_branch: "main", event: "workflow_dispatch", status: "completed", conclusion: "failure",
    display_title: `Daily Discipline · workflow_dispatch · ensure_fresh · ${DATE}`,
    created_at: new Date(NOW.getTime() - minutesAgo * 60000).toISOString(), ...overrides };
}

function network({ live = page("2026-10-05"), repo = page("2026-10-05"), runs = [], liveStatus = 200, dispatchStatus = 204 } = {}) {
  const calls = [];
  const fetcher = async (url, init) => {
    calls.push({ url, init });
    if (url.startsWith("https://discipline.jdb-builds.com/")) return new Response(live, { status: liveStatus });
    if (url.includes("/contents/index.html")) return new Response(repo);
    if (url.includes("/runs?")) return Response.json({ workflow_runs: runs });
    if (url.endsWith("/dispatches")) return new Response(dispatchStatus === 204 ? null : "{}", { status: dispatchStatus });
    if (url === "https://alerts.example.test/hook") return new Response(null, { status: 204 });
    throw new Error("Unexpected test request");
  };
  return { calls, fetcher };
}

test("Chicago clock handles summer, winter, midnight, and both DST transitions", () => {
  assert.deepEqual(chicagoClock(NOW), { date: DATE, minutes: 75 });
  assert.deepEqual(chicagoClock(new Date("2026-12-06T07:15:00Z")), { date: "2026-12-06", minutes: 75 });
  assert.deepEqual(chicagoClock(new Date("2026-10-06T04:30:00Z")), { date: "2026-10-05", minutes: 1410 });
  assert.equal(chicagoClock(new Date("2026-03-08T08:15:00Z")).minutes, 195);
  assert.equal(chicagoClock(new Date("2026-11-01T06:15:00Z")).minutes, 75);
  assert.equal(chicagoClock(new Date("2026-11-01T07:15:00Z")).minutes, 75);
});

test("freshness needs complete content and today's matching manifest", () => {
  assert.ok(inspectPage(page(), DATE));
  assert.ok(inspectPage(page(DATE, "fixed"), DATE));
  for (const broken of [page("2026-10-05"), page().replace('data-reading-role="echo"', ''),
    page().replace('<dt>Surrender</dt>', '<dt>Missing</dt>'), page().replace('Original reading', ''),
    page().replace('</body></html>', ''), page().replace('data-selection-key="tao:1"', 'data-selection-key="tao:2"'),
    page().replace('class="trail"', 'class="missing"'), page().replace('What can I entrust tonight?', '')]) {
    assert.equal(inspectPage(broken, DATE), null);
  }
});

test("outside local window makes zero network calls", async () => {
  const net = network();
  for (const time of ["2026-10-06T05:15:00Z", "2026-10-06T12:00:00Z", "2026-12-06T06:15:00Z"]) {
    assert.equal((await checkAndDispatch(ENV, new Date(time), net.fetcher)).status, "outside_window");
  }
  assert.equal(net.calls.length, 0);
});

test("fresh live AI or fallback page needs no GitHub calls", async () => {
  for (const mode of ["ai", "fixed"]) {
    const net = network({ live: page(DATE, mode) });
    assert.equal((await checkAndDispatch(ENV, NOW, net.fetcher)).status, "fresh");
    assert.equal(net.calls.length, 1);
    assert.equal(net.calls[0].init.headers.Authorization, undefined);
    assert.equal(net.calls[0].init.redirect, "error");
  }
});

test("fresh repository plus stale live site waits for deployment, not new readings", async () => {
  const net = network({ repo: page() });
  assert.equal((await checkAndDispatch(ENV, NOW, net.fetcher)).status, "deployment_pending");
  assert.equal(net.calls.length, 2);
  assert.equal(net.calls[1].init.headers.Authorization, undefined);
});

test("queued/in-progress main run blocks another dispatch", async () => {
  for (const status of ["queued", "in_progress", "waiting", "requested"]) {
    const net = network({ runs: [attempt(60, { status, event: "schedule" })] });
    assert.equal((await checkAndDispatch(ENV, NOW, net.fetcher)).status, "run_pending");
    assert.equal(net.calls.length, 3);
  }
});

test("retries are spaced 45 minutes apart and capped at three visible attempts", () => {
  assert.equal(retryDecision([attempt(5)], DATE, NOW), "retry_cooldown");
  assert.equal(retryDecision([attempt(45)], DATE, NOW), "reserved_retry");
  assert.equal(retryDecision([attempt(60)], DATE, new Date("2026-10-06T08:15:00Z")), "dispatch");
  assert.equal(retryDecision([attempt(60), attempt(120)], DATE, new Date("2026-10-06T08:15:00Z")), "reserved_retry");
  assert.equal(retryDecision([attempt(60), attempt(120)], DATE, new Date("2026-10-06T10:15:00Z")), "dispatch");
  assert.equal(retryDecision([attempt(60), attempt(120), attempt(180)], DATE, NOW), "attempt_limit");
  assert.equal(retryDecision([attempt(5, { head_branch: "other" })], DATE, NOW), "dispatch");
});

test("stale evidence dispatches only ensure_fresh on main with explicit date", async () => {
  const net = network();
  assert.equal((await checkAndDispatch(ENV, NOW, net.fetcher)).status, "dispatched");
  const last = net.calls.at(-1);
  assert.deepEqual(JSON.parse(last.init.body), { ref: "main", inputs: { mode: "ensure_fresh", expected_date: DATE } });
  assert.equal(last.init.headers.Authorization, `Bearer ${ENV.GITHUB_TOKEN}`);
  assert.equal(last.init.redirect, "error");
});

test("dispatch supports both 204 and current 200 responses", async () => {
  const net = network({ dispatchStatus: 200 });
  assert.equal((await checkAndDispatch(ENV, NOW, net.fetcher)).status, "dispatched");
});

test("live-domain error still checks repository and does not blindly regenerate", async () => {
  const net = network({ liveStatus: 503, repo: page() });
  assert.equal((await checkAndDispatch(ENV, NOW, net.fetcher)).status, "deployment_pending");
});

test("missing secret and GitHub failures do not dispatch or leak error bodies", async () => {
  await assert.rejects(checkAndDispatch({}, NOW, async () => { throw new Error("must not call"); }), /github_secret_missing/);
  const calls = [];
  const fetcher = async (url) => { calls.push(url); return new Response("private provider data", { status: 403 }); };
  await assert.rejects(checkAndDispatch(ENV, NOW, fetcher), /http_403/);
  assert.equal(calls.some(url => url.endsWith("/dispatches")), false);
});

test("malformed run evidence stops dispatch", async () => {
  const net = network({ runs: [{}] });
  await assert.rejects(checkAndDispatch(ENV, NOW, net.fetcher), /invalid_run_evidence/);
  assert.equal(net.calls.length, 3);
});

test("an ambiguous dispatch timeout is not retried within the same tick", async () => {
  const net = network();
  let posts = 0;
  const fetcher = async (url, init) => {
    if (url.endsWith('/dispatches')) { posts++; throw new Error('ambiguous timeout'); }
    return net.fetcher(url, init);
  };
  await assert.rejects(checkAndDispatch(ENV, NOW, fetcher), /ambiguous timeout/);
  assert.equal(posts, 1);
});

test("truncated current-day evidence fails closed instead of bypassing retry caps", async () => {
  const net = network({ runs: Array.from({ length: 100 }, () => attempt(5)) });
  await assert.rejects(checkAndDispatch(ENV, NOW, net.fetcher), /run_evidence_truncated/);
});

test("6:30 stale alert contains only public metadata and no GitHub credential", async () => {
  const net = network({ repo: page() });
  const env = { ...ENV, ALERT_WEBHOOK_URL: "https://alerts.example.test/hook" };
  await tick(env, new Date("2026-10-06T11:30:00Z"), net.fetcher, LOG);
  const alert = net.calls.at(-1);
  assert.equal(alert.url, env.ALERT_WEBHOOK_URL);
  assert.equal(alert.init.headers.Authorization, undefined);
  assert.equal(alert.init.headers["Idempotency-Key"], `daily-discipline-${DATE}`);
  assert.equal(JSON.parse(alert.init.body).event, "daily_discipline_stale");
  assert.equal(alert.init.body.includes(ENV.GITHUB_TOKEN), false);
});

test("deadline works in winter and late/duplicate checks carry same idempotency key", async () => {
  for (const time of ["2026-12-06T12:30:00Z", "2026-12-06T12:45:00Z"]) {
    const net = network({ repo: page("2026-12-06") });
    await tick({ ...ENV, ALERT_WEBHOOK_URL: "https://alerts.example.test/hook" }, new Date(time), net.fetcher, LOG);
    assert.equal(net.calls.at(-1).init.headers["Idempotency-Key"], "daily-discipline-2026-12-06");
  }
});

test("fresh deadline check stays quiet; missing alert destination fails visibly", async () => {
  const fresh = network({ live: page() });
  await tick(ENV, new Date("2026-10-06T11:30:00Z"), fresh.fetcher, LOG);
  assert.equal(fresh.calls.length, 1);
  const stale = network({ repo: page() });
  await assert.rejects(tick(ENV, new Date("2026-10-06T11:30:00Z"), stale.fetcher, LOG), /alert_not_configured/);
});

test("response buffering has hard limits even without Content-Length", async () => {
  await assert.rejects(boundedText(new Response("123456"), 5), /body_limit/);
  await assert.rejects(boundedText(new Response("1", { headers: { "Content-Length": "100" } }), 5), /body_limit/);
  assert.equal(await boundedText(new Response("12345"), 5), "12345");
});

test("there is no public HTTP trigger", async () => {
  assert.equal((await worker.fetch(new Request("https://example.test/__scheduled"))).status, 404);
});
