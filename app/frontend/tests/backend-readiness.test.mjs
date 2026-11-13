import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

let instance = 0
const models = [{ model_id: 'cloudflare/flux-1-schnell', name: 'FLUX.1-schnell' }]
const json = (body, status = 200) => new Response(JSON.stringify(body), { status })
const flush = () => new Promise(resolve => setImmediate(resolve))

async function apiModule(t, development = false) {
  const source = await readFile(new URL('../src/services/requests.ts', import.meta.url), 'utf8')
  const code = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022,
  } }).outputText.replaceAll('import.meta.env.VITE_API_URL', 'undefined')
    .replaceAll('import.meta.env.DEV', String(development))
  const api = await import(`data:text/javascript;base64,${Buffer.from(code + `\n// ${instance++}`).toString('base64')}`)
  t.mock.timers.enable({ apis: ['Date', 'setTimeout'], now: 0 })
  t.mock.method(Math, 'random', () => 0.5)
  return api
}

async function exhaust(t, api) {
  await flush()
  for (let elapsed = 0; elapsed < 120_000 && api.getBackendState().status !== 'unavailable'; elapsed += 1000) {
    t.mock.timers.tick(1000)
    await flush()
  }
  assert.equal(api.getBackendState().status, 'unavailable')
}

test('immediate readiness probes once, shares callers and never keeps Render awake', async t => {
  const api = await apiModule(t)
  const fetch = t.mock.method(globalThis, 'fetch', async () => json(models))
  await Promise.all([api.startBackendReadiness(), api.startBackendReadiness(), api.startBackendReadiness()])
  assert.equal(api.getBackendState().status, 'ready')
  assert.equal(fetch.mock.callCount(), 1)
  t.mock.timers.tick(600_000)
  await flush()
  assert.equal(fetch.mock.callCount(), 1)
})

for (const failure of [502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527, 528, 529, 530,
  'network', 'timeout', 'abort', 'html', 'malformed-json', 'invalid-catalogue']) {
  test(`recovers from ${failure} using one shared backoff cycle`, async t => {
    const api = await apiModule(t)
    let attempts = 0
    const calls = []
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      calls.push([url, options])
      assert.equal(options?.method, undefined)
      if (url.endsWith('/models') && ++attempts === 1) {
        if (failure === 'network') throw new TypeError('Failed to fetch')
        if (failure === 'timeout') throw new DOMException('Timeout', 'TimeoutError')
        if (failure === 'abort') throw new DOMException('Aborted', 'AbortError')
        if (failure === 'html') return new Response('<html>Starting</html>', { headers: { 'content-type': 'text/html' } })
        if (failure === 'malformed-json') return new Response('{')
        if (failure === 'invalid-catalogue') return json([{ model_id: '', name: 'Invalid' }])
        return json({}, failure)
      }
      if (url.endsWith('/models')) return json(models)
      if (url.endsWith('/users/me')) return json({ id: 1, email: 'owner@example.com' })
      if (url.includes('/chats?')) return json([])
      throw new Error(`Unexpected URL: ${url}`)
    })
    const first = api.startBackendReadiness()
    const second = api.startBackendReadiness()
    const catalogue = api.getModels()
    const session = api.initializeSession()
    const chats = api.getChats()
    await flush()
    assert.equal(api.getBackendState().status, 'starting')
    assert.equal(calls.length, 1)
    t.mock.timers.tick(999)
    await flush()
    assert.equal(calls.length, 1)
    t.mock.timers.tick(1)
    await Promise.all([first, second, catalogue, session, chats])
    assert.equal(api.getBackendState().status, 'ready')
    assert.equal(calls.filter(([url]) => url.endsWith('/models')).length, 3) // 2 probes + catalogue.
    assert.equal(calls.filter(([url]) => url.endsWith('/users/me')).length, 1)
    assert.equal(calls.filter(([url]) => url.includes('/chats?')).length, 1)
    assert.ok(calls.every(([, options]) => !options?.method || options.method === 'GET'))
  })
}

test('a hanging readiness fetch times out at 65s; the next probe is capped by the 120s budget', async t => {
  const api = await apiModule(t)
  const timeouts = []
  t.mock.method(AbortSignal, 'timeout', milliseconds => {
    timeouts.push(milliseconds)
    const controller = new AbortController()
    setTimeout(() => controller.abort(new DOMException('Timeout', 'TimeoutError')), milliseconds)
    return controller.signal
  })
  let calls = 0
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (++calls > 1) return json(models)
    return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true }))
  })
  const readiness = api.startBackendReadiness()
  t.mock.timers.tick(65_000)
  await flush()
  assert.equal(api.getBackendState().status, 'starting')
  assert.equal(calls, 1)
  t.mock.timers.tick(1000)
  await readiness
  assert.equal(api.getBackendState().status, 'ready')
  assert.deepEqual(timeouts, [65_000, 54_000])
})

test('timeouts cannot extend the shared readiness budget beyond 120 seconds', async t => {
  const api = await apiModule(t)
  t.mock.method(AbortSignal, 'timeout', milliseconds => {
    const controller = new AbortController()
    setTimeout(() => controller.abort(new DOMException('Timeout', 'TimeoutError')), milliseconds)
    return controller.signal
  })
  let calls = 0
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls++
    return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true }))
  })
  const failure = assert.rejects(api.startBackendReadiness(), /Server temporarily unavailable/)
  t.mock.timers.tick(65_000)
  await flush()
  assert.equal(api.getBackendState().status, 'starting')
  t.mock.timers.tick(1000)
  await flush()
  assert.equal(calls, 2)
  t.mock.timers.tick(53_999)
  await flush()
  assert.notEqual(api.getBackendState().status, 'unavailable')
  t.mock.timers.tick(1)
  await failure
  assert.equal(Date.now(), 120_000)
  assert.equal(api.getBackendState().status, 'unavailable')
})

test('HTML returned by a catalogue read after a valid probe is retried within the budget', async t => {
  const api = await apiModule(t)
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => ++calls === 2 ? new Response('<html>edge page</html>') : json(models))
  await api.startBackendReadiness()
  const catalogue = api.getModels()
  await flush()
  assert.equal(api.getBackendState().status, 'starting')
  t.mock.timers.tick(1000)
  assert.deepEqual(await catalogue, models)
  assert.equal(api.getBackendState().status, 'ready')
  assert.equal(calls, 4)
})

for (const development of [false, true]) {
  test(`readiness diagnostics are ${development ? 'sanitized in development' : 'disabled in production'}`, async t => {
    const api = await apiModule(t, development)
    const log = t.mock.method(console, 'debug', () => {})
    let calls = 0
    t.mock.method(globalThis, 'fetch', async () => {
      if (++calls === 1) throw new TypeError('secret-cookie=do-not-log-me')
      return json(models)
    })
    const ready = api.startBackendReadiness()
    await flush()
    t.mock.timers.tick(1000)
    await ready
    const entries = log.mock.calls.map(call => call.arguments)
    if (!development) assert.deepEqual(entries, [])
    else {
      assert.ok(entries.some(([, event]) => event === 'cycle-start'))
      assert.ok(entries.some(([, event, fields]) => event === 'probe-end' && fields.reason === 'network' && fields.durationMs === 0))
      assert.ok(entries.some(([, event, fields]) => event === 'retry' && fields.delayMs === 1000))
      assert.ok(entries.some(([, event, fields]) => event === 'cycle-ready' && fields.elapsedMs === 1000))
      assert.doesNotMatch(JSON.stringify(entries), /secret-cookie|do-not-log-me|https?:/)
    }
  })
}

test('an application HTTP 500 on a safe session read is surfaced without a recovery loop', async t => {
  const api = await apiModule(t)
  const fetch = t.mock.method(globalThis, 'fetch', async url => url.endsWith('/models') ? json(models) : json({}, 500))
  await api.startBackendReadiness()
  await assert.rejects(api.getCurrentUser(), error => error.status === 500)
  t.mock.timers.tick(120_000)
  await flush()
  assert.equal(fetch.mock.callCount(), 2)
  assert.notEqual(api.getBackendState().status, 'unavailable')
})

test('120 second budget stops retry; manual retry resumes failed session, models and history', async t => {
  const api = await apiModule(t)
  let available = false
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push([url, options])
    if (!available) return json({}, 503)
    if (url.endsWith('/models')) return json(models)
    if (url.endsWith('/users/me')) return json({}, 401)
    if (url.endsWith('/Text-to-Masterpiece')) return json({ ok: true })
    if (url.includes('/chats?')) return json([])
    throw new Error(`Unexpected URL: ${url}`)
  })
  const startup = api.startBackendReadiness().catch(error => error)
  const session = api.initializeSession().catch(error => error)
  const catalogue = api.getModels().catch(error => error)
  const history = api.getChats().catch(error => error)
  await exhaust(t, api)
  for (const error of await Promise.all([startup, session, catalogue, history])) {
    assert.match(error.message, /Server temporarily unavailable/)
  }
  assert.ok(calls.length <= 20)
  const exhaustedCount = calls.length
  t.mock.timers.tick(600_000)
  await flush()
  assert.equal(calls.length, exhaustedCount)
  await assert.rejects(api.getModels(), /Server temporarily unavailable/)
  assert.equal(calls.length, exhaustedCount)
  available = true
  await api.retryBackendReadiness()
  assert.equal(api.getBackendState().retryVersion, 1)
  await Promise.all([api.initializeSession(), api.initializeSession(), api.getModels(), api.getChats()])
  assert.equal(calls.filter(([url]) => url.endsWith('/Text-to-Masterpiece')).length, 1)
  assert.equal(api.getBackendState().status, 'ready')
  assert.ok(calls.every(([, options]) => options?.method !== 'POST'))
})

for (const status of [401, 403, 404, 500]) {
  test(`readiness HTTP ${status} is not classified as cold start or retried`, async t => {
    const api = await apiModule(t)
    const fetch = t.mock.method(globalThis, 'fetch', async () => json({}, status))
    await assert.rejects(api.startBackendReadiness(), new RegExp(`HTTP ${status}`))
    assert.equal(api.getBackendState().status, 'error')
    t.mock.timers.tick(120_000)
    await flush()
    assert.equal(fetch.mock.callCount(), 1)
  })
}

test('safe session read retries after a transient failure; guest creation is not replayed', async t => {
  const api = await apiModule(t)
  let meCalls = 0, guestCalls = 0
  t.mock.method(globalThis, 'fetch', async url => {
    if (url.endsWith('/models')) return json(models)
    if (url.endsWith('/users/me')) return ++meCalls === 1 ? json({}, 503) : json({}, 401)
    guestCalls++
    throw new TypeError('Lost guest acknowledgement')
  })
  await api.startBackendReadiness()
  const failure = assert.rejects(api.initializeSession(), /Lost guest acknowledgement/)
  await flush()
  t.mock.timers.tick(1000)
  await failure
  assert.equal(meCalls, 2)
  assert.equal(guestCalls, 1)
  t.mock.timers.tick(120_000)
  await flush()
  assert.equal(guestCalls, 1)
})

test('two failed safe GETs do not terminate recovery before a third succeeds', async t => {
  const api = await apiModule(t)
  let reads = 0
  t.mock.method(globalThis, 'fetch', async url => {
    if (url.endsWith('/models')) return json(models)
    return ++reads <= 2 ? json({}, 503) : json({ id: 1, email: 'owner@example.com' })
  })
  await api.startBackendReadiness()
  const user = api.getCurrentUser()
  await flush()
  t.mock.timers.tick(1000)
  await flush()
  assert.equal(reads, 2)
  assert.notEqual(api.getBackendState().status, 'unavailable')
  t.mock.timers.tick(2000)
  assert.deepEqual(await user, { id: 1, email: 'owner@example.com' })
  assert.equal(api.getBackendState().status, 'ready')
  assert.equal(reads, 3)
})

test('repeated endpoint 503 cannot create an infinite probe/read loop', async t => {
  const api = await apiModule(t)
  let calls = 0
  t.mock.method(globalThis, 'fetch', async url => {
    calls++
    return url.endsWith('/models') ? json(models) : json({}, 503)
  })
  await api.startBackendReadiness()
  const failure = assert.rejects(api.getCurrentUser(), /Server temporarily unavailable/)
  await flush()
  t.mock.timers.tick(1000)
  await flush()
  assert.ok(calls >= 4) // More than one failed safe read does not exhaust 120 seconds.
  assert.notEqual(api.getBackendState().status, 'unavailable')
  await exhaust(t, api)
  await failure
  assert.ok(calls < 50)
  const exhaustedCount = calls
  t.mock.timers.tick(120_000)
  await flush()
  assert.equal(calls, exhaustedCount)
})

test('aborting one view does not cancel the shared recovery loop', async t => {
  const api = await apiModule(t)
  let calls = 0
  t.mock.method(globalThis, 'fetch', async () => ++calls === 1 ? json({}, 503) : json(models))
  const ready = api.startBackendReadiness()
  const controller = new AbortController()
  const cancelled = api.getModels(controller.signal)
  controller.abort()
  await assert.rejects(cancelled, { name: 'AbortError' })
  await flush()
  t.mock.timers.tick(1000)
  await ready
  assert.equal(api.getBackendState().status, 'ready')
  assert.equal(calls, 2)
})

test('generation is never retried after an ambiguous network failure', async t => {
  const api = await apiModule(t)
  const fetch = t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url.endsWith('/models')) return json(models)
    assert.ok(url.endsWith('/generate'))
    assert.equal(options.method, 'POST')
    throw new TypeError('Lost generation acknowledgement')
  })
  await api.startBackendReadiness()
  api.rememberSession({ id: 1, email: 'owner@example.com' })
  await assert.rejects(api.generateImage('draft', models[0].model_id), /Lost generation acknowledgement/)
  t.mock.timers.tick(120_000)
  await flush()
  assert.equal(fetch.mock.callCount(), 2) // One readiness GET, exactly one POST.
})
