// Local-only test bridge: never deploy this file. The production credential
// remains in Cloudflare and is never returned through RPC.
export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("Not Found", { status: 404 });
    const path = new URL(request.url).pathname;
    try {
      if (path === "/connection") return Response.json(await env.CONTROLLER.connection());
      if (path === "/dispatch") return Response.json(await env.CONTROLLER.noOpDispatch());
      if (path === "/alert") return Response.json(await env.CONTROLLER.alertTest());
      return new Response("Not Found", { status: 404 });
    } catch (error) {
      const message = String(error?.message ?? "");
      const code = message.match(/\b(?:http_\d{3}|github_secret_missing|setup_checks_disabled|no_op_precondition_failed|run_pending|email_binding_missing|invalid_run_evidence|E_[A-Z_]+)\b/)?.[0] ?? "remote_runtime_error";
      return Response.json({ status: "setup_check_failed", code }, { status: 502 });
    }
  },
};
