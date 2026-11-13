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

test('does not act as an open proxy or accept lookalike API prefixes', async t => {
  const { default: worker } = await loadWorker()
  const fetchMock = t.mock.method(globalThis, 'fetch', async () => new Response())
  for (const path of ['/api-evil/resource', '/https://attacker.example/']) {
    const response = await worker.fetch(new Request(`https://app.example${path}`))
    assert.equal(response.status, 404)
  }
  assert.equal(fetchMock.mock.callCount(), 0)
})
