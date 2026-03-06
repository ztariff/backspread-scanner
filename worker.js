/*
 * Databento CORS Proxy — Cloudflare Worker
 *
 * Deploy for free at https://workers.cloudflare.com
 *
 * Steps:
 *   1. Go to https://dash.cloudflare.com → Workers & Pages → Create
 *   2. Click "Create Worker"
 *   3. Paste this entire file, click "Deploy"
 *   4. Copy your worker URL (e.g. https://my-worker.yourname.workers.dev)
 *   5. Paste it into the "Proxy URL" field in the scanner dashboard
 */

const ALLOWED_ORIGIN = "*"; // Lock this down to your GitHub Pages URL if you want
const DATABENTO_BASE = "https://hist.databento.com";

export default {
  async fetch(request) {
    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Authorization, Content-Type, X-DBN-Key",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    try {
      const url = new URL(request.url);

      // The path after the worker URL maps to Databento API
      // e.g., /v0/timeseries.get_range?... → https://hist.databento.com/v0/timeseries.get_range?...
      const targetPath = url.pathname + url.search;
      const targetUrl = DATABENTO_BASE + targetPath;

      // Get the API key from the X-DBN-Key header (avoids exposing in URL)
      const dbnKey = request.headers.get("X-DBN-Key") || "";
      if (!dbnKey) {
        return new Response(JSON.stringify({ error: "Missing X-DBN-Key header" }), {
          status: 400,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
          },
        });
      }

      // Forward to Databento with proper auth
      const resp = await fetch(targetUrl, {
        method: request.method,
        headers: {
          "Authorization": "Basic " + btoa(dbnKey + ":"),
          "Content-Type": "application/json",
        },
        body: request.method !== "GET" ? await request.text() : undefined,
      });

      // Return response with CORS headers
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
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
        },
      });
    }
  },
};
