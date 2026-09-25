function backendOrigin(env) {
  const value = String(env.BACKEND_ORIGIN || '').trim().replace(/\/+$/, '');
  return /^https:\/\/[a-z0-9.-]+(?::\d+)?$/i.test(value) ? value : '';
}

export async function onRequest(context) {
  const backend = backendOrigin(context.env);
  if (!backend) return context.env.ASSETS.fetch(context.request);

  const parts = Array.isArray(context.params.path)
    ? context.params.path
    : [context.params.path].filter(Boolean);
  const suffix = parts.map(encodeURIComponent).join('/');
  const incoming = new URL(context.request.url);
  const target = new URL(`${backend}/images/${suffix}`);
  target.search = incoming.search;

  const headers = new Headers(context.request.headers);
  headers.delete('host');
  const init = { method: context.request.method, headers, redirect: 'manual' };

  try {
    const upstream = await fetch(new Request(target.toString(), init));
    if (upstream.status === 404) return context.env.ASSETS.fetch(context.request);
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: upstream.headers
    });
  } catch (error) {
    return context.env.ASSETS.fetch(context.request);
  }
}
