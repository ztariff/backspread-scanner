/*
 * Databento CORS Proxy — Cloudflare Worker
 * Receives X-DBN-Key header, converts to Basic auth, forwards to Databento.
 */

const ALLOWED_ORIGIN = "*";
const DATABENTO_BASE = "https://hist.databento.com";

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
      const targetUrl = DATABENTO_BASE + url.pathname + url.search;

      const dbnKey = request.headers.get("X-DBN-Key") || "";
      if (!dbnKey) {
        return new Response(JSON.stringify({ error: "Missing X-DBN-Key header" }), {
          status: 400,
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": ALLOWED_ORIGIN },
        });
      }

      const authString = "Basic " + btoa(dbnKey + ":");

      // Forward to Databento — NO Content-Type on GET (was causing 401)
      const resp = await fetch(targetUrl, {
        method: request.method,
        headers: { "Authorization": authString },
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
