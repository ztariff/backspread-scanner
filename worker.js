/*
 * Databento CORS Proxy — Cloudflare Worker
 * Visit /debug to test if auth is working
 */

const ALLOWED_ORIGIN = "*";
const DATABENTO_BASE = "https://hist.databento.com";
const DBN_KEY = "db-MQACcG6YCgCiTmJ87NUWVBhcnxAyx";

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, X-DBN-Key",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    try {
      const url = new URL(request.url);

      // Debug endpoint — test auth against Databento
      if (url.pathname === "/debug") {
        const testUrl = DATABENTO_BASE + "/v0/metadata.list_datasets?encoding=json";
        const authStr = "Basic " + btoa(DBN_KEY + ":");

        // Try with Headers object
        const headers = new Headers();
        headers.set("Authorization", authStr);

        const resp = await fetch(testUrl, { headers });
        const body = await resp.text();

        return new Response(JSON.stringify({
          test_url: testUrl,
          auth_header_sent: authStr.slice(0, 20) + "...",
          databento_status: resp.status,
          databento_response: body.slice(0, 500),
        }, null, 2), {
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": ALLOWED_ORIGIN },
        });
      }

      const targetUrl = DATABENTO_BASE + url.pathname + url.search;

      // Use explicit Headers object (workaround for CF stripping Authorization)
      const headers = new Headers();
      headers.set("Authorization", "Basic " + btoa(DBN_KEY + ":"));

      const resp = await fetch(new Request(targetUrl, {
        method: request.method,
        headers: headers,
      }));

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
