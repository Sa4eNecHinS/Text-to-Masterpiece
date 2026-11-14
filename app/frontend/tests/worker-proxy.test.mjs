import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

async function loadWorker() {
  const source = await readFile(new URL('../worker/index.ts', import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 },
  })
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
}

test('proxies the exact API path, query, method, body and browser security headers', async t => {
  const { default: worker } = await loadWorker()
  let forwarded
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    forwarded = { url: String(url), init }
    return new Response('created', {
      status: 201,
      headers: { 'content-type': 'text/plain', 'set-cookie': 'access_token=secret; Path=/; HttpOnly; Secure; SameSite=Lax' },
    })
  })
  const request = new Request('https://app.example/api/Text-to-Masterpiece/generate?draft=1', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      cookie: 'guest_id=abc',
      origin: 'https://app.example',
      'sec-fetch-site': 'same-origin',
      'x-forwarded-host': 'attacker.example',
      'x-forwarded-for': '203.0.113.10',
    },
    body: JSON.stringify({ prompt: 'mountains' }),
  })

  const response = await worker.fetch(request)
  assert.equal(forwarded.url, 'https://ttm-backend-du5g.onrender.com/Text-to-Masterpiece/generate?draft=1')
  assert.equal(forwarded.init.method, 'POST')
  assert.equal(forwarded.init.headers.get('cookie'), 'guest_id=abc')
  assert.equal(forwarded.init.headers.get('origin'), 'https://app.example')
  assert.equal(forwarded.init.headers.get('sec-fetch-site'), 'same-origin')
  assert.equal(forwarded.init.headers.has('x-forwarded-host'), false)
  assert.equal(forwarded.init.headers.has('x-forwarded-for'), false)
  assert.equal(await new Response(forwarded.init.body).text(), '{"prompt":"mountains"}')
  assert.equal(response.status, 201)
  assert.match(response.headers.get('set-cookie'), /HttpOnly; Secure; SameSite=Lax/i)
  assert.equal(response.headers.get('cache-control'), 'private, no-store')
})

test('maps private image requests to GET /images/{generation_id} without a body', async t => {
  const { default: worker } = await loadWorker()
  let forwarded
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    forwarded = { url: String(url), init }
    return new Response(new Uint8Array([1, 2, 3]), { headers: { 'content-type': 'image/png' } })
  })
  const response = await worker.fetch(new Request('https://app.example/api/images/42?download=1', {
    headers: { cookie: 'access_token=token' },
  }))
  assert.equal(forwarded.url, 'https://ttm-backend-du5g.onrender.com/images/42?download=1')
  assert.equal(forwarded.init.method, 'GET')
  assert.equal(forwarded.init.body, undefined)
  assert.equal(response.headers.get('content-type'), 'image/png')
  assert.deepEqual([...new Uint8Array(await response.arrayBuffer())], [1, 2, 3])
})

test('a 50-second upstream response is not cut off by a Worker timeout', async t => {
  const { default: worker } = await loadWorker()
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 0 })
  const fetch = t.mock.method(globalThis, 'fetch', async (url, init) => {
    assert.equal(init.signal, undefined)
    await new Promise(resolve => setTimeout(resolve, 50_000))
    return Response.json([{ model_id: 'model', name: 'Model' }])
  })
  let settled = false
  const pending = worker.fetch(new Request('https://app.example/api/Text-to-Masterpiece/models'))
    .then(response => { settled = true; return response })
  t.mock.timers.tick(49_000)
  await Promise.resolve()
  assert.equal(settled, false)
  t.mock.timers.tick(1000)
  const response = await pending
  assert.equal(response.status, 200)
  assert.deepEqual(await response.json(), [{ model_id: 'model', name: 'Model' }])
  assert.equal(fetch.mock.callCount(), 1)
})

for (const method of ['GET', 'POST']) {
  test(`upstream network exceptions return a sanitized uncached 502 without replaying ${method}`, async t => {
    const { default: worker } = await loadWorker()
    const fetch = t.mock.method(globalThis, 'fetch', async () => { throw new Error('secret-upstream-diagnostic') })
    const response = await worker.fetch(new Request('https://app.example/api/Text-to-Masterpiece/generate', { method }))
    assert.equal(response.status, 502)
    assert.equal(response.headers.get('cache-control'), 'private, no-store')
    assert.match(response.headers.get('content-type'), /application\/json/)
    assert.equal(response.headers.has('set-cookie'), false)
    assert.deepEqual(await response.json(), { detail: 'Backend connection unavailable. Please try again shortly.' })
    assert.equal(fetch.mock.callCount(), 1)
  })
}

test('proxy preserves a pending response stream and multiple Set-Cookie fields without buffering', async t => {
  const { default: worker } = await loadWorker()
  let controller
  const stream = new ReadableStream({ start(value) { controller = value } })
  const headers = new Headers()
  headers.append('set-cookie', 'access_token=one; Path=/; HttpOnly; Secure; SameSite=Lax')
  headers.append('set-cookie', 'guest_id=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax')
  t.mock.method(globalThis, 'fetch', async () => new Response(stream, { headers }))
  const response = await worker.fetch(new Request('https://app.example/api/images/1'))
  assert.equal(response.body, stream)
  assert.equal(response.headers.getSetCookie().length, 2)
  const reader = response.body.getReader()
  controller.enqueue(new Uint8Array([1, 2, 3]))
  assert.deepEqual([...(await reader.read()).value], [1, 2, 3])
  controller.close()
  assert.equal((await reader.read()).done, true)
})

for (const status of [500, 502, 503, 504, 520, 522, 524]) {
  test(`proxy passes upstream HTTP ${status} through unchanged without retrying`, async t => {
    const { default: worker } = await loadWorker()
    const fetch = t.mock.method(globalThis, 'fetch', async () => new Response('upstream', {
      status, headers: status === 502 ? { 'x-render-routing': 'no-deploy' } : {},
    }))
    const response = await worker.fetch(new Request('https://app.example/api/Text-to-Masterpiece/models'))
    assert.equal(response.status, status)
    assert.equal(response.headers.get('x-render-routing'), status === 502 ? 'no-deploy' : null)
    assert.equal(await response.text(), 'upstream')
    assert.equal(fetch.mock.callCount(), 1)
  })
}

test('does not act as an open proxy or accept lookalike API prefixes', async t => {
  const { default: worker } = await loadWorker()
  const fetchMock = t.mock.method(globalThis, 'fetch', async () => new Response())
  for (const path of ['/api-evil/resource', '/https://attacker.example/']) {
    const response = await worker.fetch(new Request(`https://app.example${path}`))
    assert.equal(response.status, 404)
  }
  assert.equal(fetchMock.mock.callCount(), 0)
})
