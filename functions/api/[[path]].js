function backendOrigin(env) {
  const value = String(env.BACKEND_ORIGIN || '').trim().replace(/\/+$/, '');
  return /^https:\/\/[a-z0-9.-]+(?::\d+)?$/i.test(value) ? value : '';
}

async function fallbackCatalog(context) {
  const url = new URL('/catalog.js', context.request.url);
  return context.env.ASSETS.fetch(new Request(url.toString(), { method: 'GET' }));
}

export async function onRequest(context) {
  const backend = backendOrigin(context.env);
  const parts = Array.isArray(context.params.path)
    ? context.params.path
    : [context.params.path].filter(Boolean);
  const suffix = parts.map(encodeURIComponent).join('/');
  const isCatalog = suffix === 'catalog.js';

  if (!backend) {
    if (isCatalog) return fallbackCatalog(context);
    return Response.json(
      { error: 'Backend chưa được cấu hình. Hãy đặt BACKEND_ORIGIN trong Cloudflare Pages.' },
      { status: 503, headers: { 'Cache-Control': 'no-store' } }
    );
  }

  const incoming = new URL(context.request.url);
  const upstreamPath = suffix === 'healthz' ? '/healthz' : `/api/${suffix}`;
  const target = new URL(`${backend}${upstreamPath}`);
  target.search = incoming.search;

  const headers = new Headers(context.request.headers);
  headers.delete('host');
  headers.set('X-Forwarded-Host', incoming.host);
  headers.set('X-Forwarded-Proto', incoming.protocol.replace(':', '') || 'https');
  const clientIp = context.request.headers.get('CF-Connecting-IP');
  if (clientIp) headers.set('CF-Connecting-IP', clientIp);

  const init = {
    method: context.request.method,
    headers,
    redirect: 'manual'
  };
  if (!['GET', 'HEAD'].includes(context.request.method)) init.body = context.request.body;

  try {
    const upstream = await fetch(new Request(target.toString(), init));
    if (isCatalog && upstream.status >= 500) return fallbackCatalog(context);
    const outHeaders = new Headers(upstream.headers);
    outHeaders.set('Cache-Control', 'no-store');
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: outHeaders
    });
  } catch (error) {
    if (isCatalog) return fallbackCatalog(context);
    return Response.json(
      { error: 'Backend Render đang tạm thời không phản hồi.' },
      { status: 502, headers: { 'Cache-Control': 'no-store' } }
    );
  }
}
