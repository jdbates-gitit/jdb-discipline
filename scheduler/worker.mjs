// Cron-only controller. No public trigger, AI key, Pages token, or DNS access.
const REPO = "https://api.github.com/repos/jdbates-gitit/jdb-discipline";
export const SITE = "https://discipline.jdb-builds.com/";
const WORKFLOW = `${REPO}/actions/workflows/discipline.yml`;
const BODY_LIMIT = 512 * 1024;
const MAX_ATTEMPTS = 3;
const RETRY_GAP_MS = 45 * 60 * 1000;

export function chicagoClock(now) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Chicago", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(now).map(part => [part.type, part.value]));
  return { date: `${parts.year}-${parts.month}-${parts.day}`, minutes: Number(parts.hour) * 60 + Number(parts.minute) };
}

function hasText(markup) {
  return Boolean(markup?.replace(/<[^>]*>/g, "").replace(/&(?:nbsp|#160);/g, " ").trim());
}

export function inspectPage(page, date) {
  try {
    const scripts = [...page.matchAll(/<script id="discipline-freshness" type="application\/json">(.*?)<\/script>/gs)];
    if (scripts.length !== 1) return null;
    const manifest = JSON.parse(scripts[0][1]);
    if (manifest.version !== 1 || manifest.date !== date || !["ai", "fixed"].includes(manifest.editorial_mode)) return null;
    if (manifest.editorial_mode === "fixed" && !page.includes('id="editorial-status"')) return null;
    const roles = ["lead", "companion", "echo"];
    const selections = manifest.selections;
    if (!selections || Object.keys(selections).sort().join() !== [...roles].sort().join() || new Set(Object.values(selections)).size !== 3) return null;
    for (const role of roles) {
      const key = selections[role];
      if (typeof key !== "string" || !/^[a-z_]+:[A-Za-z0-9_]+$/.test(key)) return null;
      const sections = [...page.matchAll(new RegExp(`<section\\b([^>]*data-reading-role="${role}"[^>]*)>(.*?)</section>`, "gs"))];
      if (sections.length !== 1 || !sections[0][1].includes(`data-selection-key="${key}"`)) return null;
      if (!hasText(sections[0][2].match(/<div class="verse">(.*?)<\/div>/s)?.[1])) return null;
      const notePattern = role === "echo" ? /<p class="echo-note">(.*?)<\/p>/s : /<div class="movement">.*?<p>(.*?)<\/p>/s;
      if (!hasText(sections[0][2].match(notePattern)?.[1])) return null;
    }
    const carry = page.match(/<section class="carry"[^>]*>(.*?)<\/section>/s)?.[1];
    for (const label of ["Notice", "Surrender", "Act"]) {
      if (!hasText(carry?.match(new RegExp(`<dt>${label}</dt><dd>(.*?)</dd>`, "s"))?.[1])) return null;
    }
    const evening = page.match(/<details class="return">(.*?)<\/details>/s)?.[1];
    if (!evening?.includes(`data-note-date="${date}"`) || !hasText(evening.match(/<p class="night-question">(.*?)<\/p>/s)?.[1])) return null;
    if (!hasText(page.match(/<h2 id="daily-question">(.*?)<\/h2>/s)?.[1]) ||
        !hasText(page.match(/<section class="confluence"[^>]*>.*?<p>(.*?)<\/p>/s)?.[1]) ||
        !hasText(page.match(/<details class="trail">(.*?)<\/details>/s)?.[1]) ||
        !page.includes(`data-discipline-date="${date}"`) || !page.includes("</body></html>")) return null;
    const trail = page.match(/<details class="trail">(.*?)<\/details>\s*<footer>/s)?.[1];
    if (!trail?.includes('<ul class="trail-list">') || !trail.includes(`datetime="${date}"`)) return null;
    return manifest;
  } catch {
    return null;
  }
}

export async function boundedText(response, limit = BODY_LIMIT) {
  if (Number(response.headers.get("content-length")) > limit) {
    await response.body?.cancel();
    throw new Error("body_limit");
  }
  if (!response.body) return "";
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let bytes = 0, text = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > limit) { await reader.cancel(); throw new Error("body_limit"); }
      text += decoder.decode(value, { stream: true });
    }
    return text + decoder.decode();
  } finally {
    reader.releaseLock();
  }
}

async function request(fetcher, url, init = {}) {
  const response = await fetcher(url, { ...init, redirect: "error", signal: AbortSignal.timeout(12000) });
  if (!response.ok) {
    await response.body?.cancel();
    throw new Error(`http_${response.status}`);
  }
  return response;
}

function githubHeaders(token, accept = "application/vnd.github+json") {
  return { Accept: accept, Authorization: `Bearer ${token}`, "User-Agent": "daily-discipline-scheduler", "X-GitHub-Api-Version": "2026-03-10" };
}

export function retryDecision(runs, date, now) {
  // Any active main-branch generator, including a human run, blocks dispatch.
  if (runs.some(run => run.head_branch === "main" && run.status !== "completed")) return "run_pending";
  const attempts = runs.filter(run => run.head_branch === "main" && run.event === "workflow_dispatch" &&
    run.display_title === `Daily Discipline · workflow_dispatch · ensure_fresh · ${date}`);
  if (attempts.length >= MAX_ATTEMPTS) return "attempt_limit";
  if (attempts.some(run => now.getTime() - Date.parse(run.created_at) < RETRY_GAP_MS)) return "retry_cooldown";
  // Reserve recovery opportunities later in the morning instead of exhausting
  // all three attempts during a short overnight provider outage.
  if (chicagoClock(now).minutes < [75, 195, 315][attempts.length]) return "reserved_retry";
  return "dispatch";
}

export async function checkAndDispatch(env, now = new Date(), fetcher = fetch) {
  const clock = chicagoClock(now);
  // One UTC cron covers both offsets; actual local time decides the action.
  if (clock.minutes < 75 || clock.minutes > 405) return { status: "outside_window", date: clock.date };
  if (!env.GITHUB_TOKEN) throw new Error("github_secret_missing");
  const liveURL = new URL(SITE);
  liveURL.searchParams.set("freshness_check", `${clock.date}-${now.getTime()}`);
  let live = null;
  try {
    const response = await request(fetcher, liveURL.href, { headers: { "Cache-Control": "no-cache" }, cf: { cacheTtl: 0 } });
    live = inspectPage(await boundedText(response), clock.date);
  } catch {
    // Still inspect repository evidence if the custom-domain request failed.
  }
  if (live) return { status: "fresh", date: clock.date, mode: live.editorial_mode };

  // Public repository read is deliberately unauthenticated: no Contents scope.
  const repoResponse = await request(fetcher, `${REPO}/contents/index.html?ref=main`, {
    headers: { Accept: "application/vnd.github.raw+json", "User-Agent": "daily-discipline-scheduler", "X-GitHub-Api-Version": "2026-03-10" },
  });
  if (inspectPage(await boundedText(repoResponse), clock.date)) {
    return { status: "deployment_pending", date: clock.date };
  }
  const runResponse = await request(fetcher, `${WORKFLOW}/runs?branch=main&per_page=100`, { headers: githubHeaders(env.GITHUB_TOKEN) });
  // GitHub repeats repository metadata in each run; 100 real records can exceed
  // the smaller page-body limit. Still bound this response, never buffer freely.
  const data = JSON.parse(await boundedText(runResponse, 2 * 1024 * 1024));
  if (!Array.isArray(data.workflow_runs) || data.workflow_runs.some(run =>
      typeof run.status !== "string" || typeof run.head_branch !== "string" || !Number.isFinite(Date.parse(run.created_at)))) {
    throw new Error("invalid_run_evidence");
  }
  if (data.workflow_runs.length === 100 && data.workflow_runs.every(run =>
      chicagoClock(new Date(run.created_at)).date === clock.date)) throw new Error("run_evidence_truncated");
  const decision = retryDecision(data.workflow_runs, clock.date, now);
  if (decision !== "dispatch") return { status: decision, date: clock.date };
  // Ambiguous network failure is not retried in this invocation. Next tick reads
  // run evidence again; the serialized ensure_fresh workflow is the final guard.
  const dispatched = await request(fetcher, `${WORKFLOW}/dispatches`, {
    method: "POST", headers: { ...githubHeaders(env.GITHUB_TOKEN), "Content-Type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs: { mode: "ensure_fresh", expected_date: clock.date } }),
  });
  await dispatched.body?.cancel();
  return { status: "dispatched", date: clock.date };
}

export async function tick(env, now = new Date(), fetcher = fetch, logger = console) {
  let result;
  try { result = await checkAndDispatch(env, now, fetcher); }
  catch { result = { status: "check_failed", date: chicagoClock(now).date }; }
  const clock = chicagoClock(now);
  const deadline = clock.minutes >= 390 && clock.minutes <= 405;
  if (deadline && result.status !== "fresh") {
    logger.error(JSON.stringify({ event: "freshness_deadline_missed", ...result }));
    // Recipient/service must be selected and approved before activation.
    if (!env.ALERT_WEBHOOK_URL) throw new Error("deadline_missed_alert_not_configured");
    const url = new URL(env.ALERT_WEBHOOK_URL);
    if (url.protocol !== "https:" || url.username || url.password) throw new Error("invalid_alert_destination");
    const response = await request(fetcher, url.href, {
      method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": `daily-discipline-${clock.date}` },
      body: JSON.stringify({ event: "daily_discipline_stale", date: clock.date, site: SITE, status: result.status,
        message: "Daily Discipline has not been verified fresh by 6:30 a.m. America/Chicago." }),
    });
    await response.body?.cancel();
  } else if (result.status === "check_failed") {
    logger.error(JSON.stringify({ event: "freshness_check", ...result }));
    throw new Error("freshness_check_failed");
  } else {
    logger.log(JSON.stringify({ event: "freshness_check", ...result }));
  }
  return result;
}

export default {
  async fetch() { return new Response("Not Found", { status: 404 }); },
  async scheduled(controller, env) {
    // Wall-clock time protects against delayed/replayed events crossing dates.
    await tick(env);
  },
};
