/*
 * Databento CORS Proxy — Cloudflare Worker
 *
 * Browser computes the Basic auth header and sends it as X-DBN-Auth.
 * Worker just forwards it as Authorization — no encoding needed here.
 */

const ALLOWED_ORIGIN = "*";
const DATABENTO_BASE = "https://hist.databento.com";

export default {
  async fetch(request) {
    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, X-DBN-Auth",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    try {
      const url = new URL(request.url);
      const targetPath = url.pathname + url.search;
      const targetUrl = DATABENTO_BASE + targetPath;

      // Browser sends pre-computed "Basic ..." in X-DBN-Auth header
      const auth = request.headers.get("X-DBN-Auth") || "";
      if (!auth) {
        return new Response(JSON.stringify({ error: "Missing X-DBN-Auth header" }), {
          status: 400,
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": ALLOWED_ORIGIN },
        });
      }

      // Forward to Databento — just pass the auth through as-is
      const resp = await fetch(targetUrl, {
        method: request.method,
        headers: { "Authorization": auth },
        body: request.method !== "GET" ? await request.text() : undefined,
      });

      const body = await resp.text();
      return new Response(body, {
        status: resp.status,
        headers: {
          "Content-Type": resp.headers.get("Content-Type") || "application/json",
          "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
          "Access-Control-Expose-Headers": "*",
        },
      });

    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), {
        status: 500,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": ALLOWED_ORIGIN },
      });
    }
  },
};
