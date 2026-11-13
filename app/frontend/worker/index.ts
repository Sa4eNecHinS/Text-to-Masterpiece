const BACKEND_ORIGIN = 'https://ttm-backend-du5g.onrender.com'
const API_PREFIX = '/api'

const HOP_BY_HOP_HEADERS = [
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]

function backendUrl(requestUrl: string): URL | null {
  const incoming = new URL(requestUrl)
  if (incoming.pathname !== API_PREFIX && !incoming.pathname.startsWith(`${API_PREFIX}/`)) {
    return null
  }

  const target = new URL(BACKEND_ORIGIN)
  target.pathname = incoming.pathname.slice(API_PREFIX.length) || '/'
  target.search = incoming.search
  return target
}

function proxyHeaders(request: Request): Headers {
  const headers = new Headers(request.headers)
  for (const name of HOP_BY_HOP_HEADERS) headers.delete(name)

  // Never forward client-controlled routing metadata. The destination is the
  // constant above; Origin and Fetch Metadata intentionally remain untouched
  // so FastAPI can perform its own CSRF checks.
  headers.delete('host')
  headers.delete('forwarded')
  headers.delete('x-forwarded-host')
  headers.delete('x-forwarded-proto')
  headers.delete('x-forwarded-for')
  return headers
}

async function proxy(request: Request): Promise<Response> {
  const target = backendUrl(request.url)
  if (!target) {
    return new Response('Not found', { status: 404 })
  }

  let upstream: Response
  try {
    // Do not impose a short upstream timeout: Render can take 50–60s to wake.
    // No proxy retries, especially for POSTs with an ambiguous server outcome.
    upstream = await fetch(target, {
      method: request.method,
      headers: proxyHeaders(request),
      body: request.method === 'GET' || request.method === 'HEAD' ? undefined : request.body,
      redirect: 'manual',
    })
  } catch {
    // Return a controlled, retryable gateway response instead of an unhandled
    // Worker exception/HTML error page. Never expose exception text or headers.
    return Response.json({ detail: 'Backend connection unavailable. Please try again shortly.' }, {
      status: 502,
      headers: { 'cache-control': 'private, no-store' },
    })
  }

  const responseHeaders = new Headers(upstream.headers)
  const setCookies = upstream.headers.getSetCookie()
  if (setCookies.length) {
    responseHeaders.delete('set-cookie')
    for (const cookie of setCookies) responseHeaders.append('set-cookie', cookie)
  }
  responseHeaders.set('cache-control', 'private, no-store')

  // Reusing the upstream body keeps large private images streaming. Constructing
  // a response from its Headers also preserves separate Set-Cookie fields, so
  // host-only cookies are stored for the public Cloudflare hostname unchanged.
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  })
}

export default { fetch: proxy }
