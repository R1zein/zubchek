// Transparent relay to the Anthropic API — see wrangler.toml for why it exists.

const UPSTREAM = "https://api.anthropic.com";

// Headers that would leak the caller's origin or confuse the upstream.
const DROP_HEADERS = ["host", "cf-connecting-ip", "x-forwarded-for", "x-real-ip", "forwarded"];

export default {
  async fetch(request, env) {
    const prefix = env.RELAY_PREFIX ? `/${env.RELAY_PREFIX}` : null;
    const url = new URL(request.url);

    // Unknown path or relay not configured: look like nothing is here.
    if (!prefix || !url.pathname.startsWith(`${prefix}/`)) {
      return new Response("Not found", { status: 404 });
    }

    const target = new URL(url.pathname.slice(prefix.length) + url.search, UPSTREAM);
    const headers = new Headers(request.headers);
    for (const h of DROP_HEADERS) headers.delete(h);

    return fetch(target, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      redirect: "manual",
    });
  },
};
