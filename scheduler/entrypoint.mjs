import { WorkerEntrypoint } from "cloudflare:workers";
import worker, { SITE, REPO, WORKFLOW, chicagoClock, inspectPage, boundedText, request, githubHeaders, sendEmailAlert } from "./worker.mjs";

// No public HTTP endpoints. Setup RPC is callable only through an authorized
// same-account service binding, and is disabled in the active configuration.
export class SetupChecks extends WorkerEntrypoint {
  #requireSetup() {
    if (this.env.SETUP_CHECKS !== "true") throw new Error("setup_checks_disabled");
    if (!this.env.GITHUB_TOKEN) throw new Error("github_secret_missing");
  }

  async connection() {
    let stage = "bindings";
    try {
    this.#requireSetup();
    stage = "clock";
    const date = chicagoClock(new Date()).date;
    stage = "live";
    const live = await request(fetch, `${SITE}?setup_check=${Date.now()}`, { headers: { "Cache-Control": "no-cache" }, cf: { cacheTtl: 0 } });
    const manifest = inspectPage(await boundedText(live), date);
    stage = "github";
    const runs = await request(fetch, `${WORKFLOW}/runs?branch=main&per_page=10`, { headers: githubHeaders(this.env.GITHUB_TOKEN) });
    const evidence = JSON.parse(await boundedText(runs, 2 * 1024 * 1024));
    if (!Array.isArray(evidence.workflow_runs)) throw new Error("invalid_run_evidence");
    return { github: "authenticated", date, live: manifest ? "fresh" : "not_fresh", mode: manifest?.editorial_mode ?? null };
    } catch (error) {
      const code = String(error?.message ?? "").match(/\b(?:http_\d{3}|github_secret_missing|setup_checks_disabled|body_limit|invalid_run_evidence)\b/)?.[0] ?? "runtime_error";
      return { status: "connection_failed", stage, code, kind: error instanceof TypeError ? "type_error" : error instanceof RangeError ? "range_error" : "other" };
    }
  }

  async noOpDispatch() {
    this.#requireSetup();
    const date = chicagoClock(new Date()).date;
    const live = await request(fetch, `${SITE}?setup_check=${Date.now()}`, { cf: { cacheTtl: 0 } });
    const repo = await request(fetch, `${REPO}/contents/index.html?ref=main`, { headers: { Accept: "application/vnd.github.raw+json", "User-Agent": "daily-discipline-scheduler" } });
    if (!inspectPage(await boundedText(live), date) || !inspectPage(await boundedText(repo), date)) throw new Error("no_op_precondition_failed");
    const runs = await request(fetch, `${WORKFLOW}/runs?branch=main&per_page=10`, { headers: githubHeaders(this.env.GITHUB_TOKEN) });
    const evidence = JSON.parse(await boundedText(runs, 2 * 1024 * 1024));
    if (!Array.isArray(evidence.workflow_runs) || evidence.workflow_runs.some(run => run.status !== "completed")) throw new Error("run_pending");
    const dispatched = await request(fetch, `${WORKFLOW}/dispatches`, {
      method: "POST", headers: { ...githubHeaders(this.env.GITHUB_TOKEN), "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main", inputs: { mode: "ensure_fresh", expected_date: date } }),
    });
    await dispatched.body?.cancel();
    return { status: "dispatched_ensure_fresh", date };
  }

  async alertTest() {
    this.#requireSetup();
    await sendEmailAlert(this.env, chicagoClock(new Date()).date, "setup_test", true);
    return { status: "test_email_accepted" };
  }
}

export default worker;
