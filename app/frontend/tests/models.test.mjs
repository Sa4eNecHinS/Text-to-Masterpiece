import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

let moduleId = 0
// Use the project's TypeScript compiler and Node's test runner, without a new framework.
async function loadSource(path) {
  const source = await readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  })
  const privateImageStub = `data:text/javascript;base64,${Buffer.from('export function PrivateImage() { return null }').toString('base64')}`
  const code = outputText.replaceAll('import.meta.env.VITE_API_URL', 'undefined')
    .replace('"@/components/chat/PrivateImage"', JSON.stringify(privateImageStub))
    .replace("'@/components/chat/PrivateImage'", JSON.stringify(privateImageStub))
    .replace(/from ["'](react(?:\/[^"']+)?)["']/g, (_, specifier) => `from ${JSON.stringify(import.meta.resolve(specifier))}`)
  return import(`data:text/javascript;base64,${Buffer.from(`${code}\n// instance ${moduleId++}`).toString('base64')}`)
}

const models = [
  { model_id: 'cloudflare/flux-1-schnell', name: 'FLUX.1-schnell' },
  { model_id: 'cloudflare/flux-2-klein-4b', name: 'FLUX-2-klein-4b' },
]

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
}

test('catalogue loads anonymously from the existing API prefix', async t => {
  const api = await loadSource('services/requests.ts')
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, `${api.API_BASE_URL}/Text-to-Masterpiece/models`)
    assert.equal(options.credentials, undefined)
    return json(models)
  })
  assert.deepEqual(await api.getModels(), models)
})

test('empty catalogue is valid', async t => {
  const api = await loadSource('services/requests.ts')
  t.mock.method(globalThis, 'fetch', async () => json([]))
  assert.deepEqual(await api.getModels(), [])
})

test('catalogue errors and malformed responses are surfaced', async t => {
  const api = await loadSource('services/requests.ts')
  const fetch = t.mock.method(globalThis, 'fetch', async () => json({ detail: 'Database unavailable' }, 503))
  await assert.rejects(api.getModels(), /Database unavailable/)
  fetch.mock.mockImplementation(async () => json([{ model_id: '', name: 'Bad model' }]))
  await assert.rejects(api.getModels(), /invalid model catalogue/)
})

for (const model of models) {
  test(`generation sends only prompt and selected model: ${model.name}`, async t => {
    const api = await loadSource('services/requests.ts')
    const calls = []
    const result = { chat_id: '01900000-0000-7000-8000-000000000001', generation_id: 1, model_id: model.model_id, model_name: model.name }
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      calls.push(url)
      if (url.endsWith('/users/me')) return json({}, 401)
      if (url.endsWith('/Text-to-Masterpiece')) return json({ ok: true })
      assert.ok(url.endsWith('/Text-to-Masterpiece/generate'))
      assert.equal(options.method, 'POST')
      assert.equal(options.credentials, 'include')
      assert.deepEqual(JSON.parse(options.body), { prompt: 'city', model_id: model.model_id })
      return json(result)
    })
    assert.deepEqual(await api.generateImage('city', model.model_id), result)
    assert.equal(calls.length, 3)
  })
}

test('continuation sends chat_id but never prior messages or images', async t => {
  const api = await loadSource('services/requests.ts')
  api.rememberSession({ id: 1, email: 'user@example.com' })
  const chatId = '01900000-0000-7000-8000-000000000001'
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.deepEqual(JSON.parse(options.body), { prompt: 'second', model_id: models[0].model_id, chat_id: chatId })
    return json({ chat_id: chatId, generation_id: 2, model_id: models[0].model_id, model_name: models[0].name })
  })
  assert.equal((await api.generateImage('second', models[0].model_id, chatId)).chat_id, chatId)
})

test('generation rejects a successful response missing chat_id', async t => {
  const api = await loadSource('services/requests.ts')
  api.rememberSession({ id: 1, email: 'user@example.com' })
  t.mock.method(globalThis, 'fetch', async () => json({ generation_id: 1, model_id: models[0].model_id, model_name: models[0].name }))
  await assert.rejects(api.generateImage('city', models[0].model_id), /valid chat_id/)
})

test('chat list pagination and detail preserve server order and legacy nulls', async t => {
  const api = await loadSource('services/requests.ts')
  api.rememberSession({ id: 1, email: 'user@example.com' })
  const chatId = '01900000-0000-7000-8000-000000000001'
  const chats = [{ id: chatId, title: 'First prompt', created_at: '2020-01-01', updated_at: '2021-01-01' }]
  const entries = ['first', 'second'].map((prompt, id) => ({ id, prompt,
    created_at: '2020-01-01', model_id: null, model_name: null }))
  const controller = new AbortController()
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(options.credentials, 'include')
    assert.equal(options.signal, controller.signal)
    if (url.endsWith('/chats?limit=50&offset=50')) return json(chats)
    assert.ok(url.endsWith(`/chats/${chatId}`))
    return json(entries)
  })
  assert.deepEqual(await api.getChats(50, controller.signal), chats)
  assert.deepEqual(await api.getChat(chatId, controller.signal), entries)
})

test('chat access errors and malformed data are shown', async t => {
  const api = await loadSource('services/requests.ts')
  api.rememberSession({ id: 1, email: 'user@example.com' })
  const fetch = t.mock.method(globalThis, 'fetch', async () => json({ detail: 'Chat not found.' }, 404))
  await assert.rejects(api.getChat('missing'), /Chat not found/)
  fetch.mock.mockImplementation(async () => json([{ id: 1, title: 'Invalid ID' }]))
  await assert.rejects(api.getChats(), /invalid chat list/)
  await assert.rejects(api.getChat('bad'), /invalid chat history/)
})

test('generation failure is shown, not converted to an image', async t => {
  const api = await loadSource('services/requests.ts')
  api.rememberSession({ id: 1, email: 'user@example.com' })
  t.mock.method(globalThis, 'fetch', async () => json({ detail: 'Provider timed out' }, 502))
  await assert.rejects(api.generateImage('city', models[1].model_id), /Provider timed out/)
})

test('409 explains that generation may be running in another tab', async t => {
  const api = await loadSource('services/requests.ts')
  api.rememberSession({ id: 1, email: 'user@example.com' })
  t.mock.method(globalThis, 'fetch', async () => json({ detail: 'Image generation is already in progress.' }, 409))
  await assert.rejects(api.generateImage('city', models[0].model_id), /already in progress.*another tab/)
})

for (const detail of ['Server is busy. Please try again later.', undefined]) {
  test(`503 shows a busy message without retrying (${detail ? 'detail' : 'fallback'})`, async t => {
    const api = await loadSource('services/requests.ts')
    api.rememberSession({ id: 1, email: 'user@example.com' })
    const fetch = t.mock.method(globalThis, 'fetch', async () => json(detail ? { detail } : {}, 503))
    await assert.rejects(api.generateImage('city', models[0].model_id), /Server is busy\. Please try again later\./)
    assert.equal(fetch.mock.callCount(), 1)
  })
}

test('history preserves model names and legacy nulls', async t => {
  const api = await loadSource('services/requests.ts')
  api.rememberSession({ id: 1, email: 'user@example.com' })
  const entries = [models[0], null].map((model, index) => ({
    id: index + 1, prompt: 'city', created_at: '2026-01-01T00:00:00Z',
    model_id: model?.model_id ?? null, model_name: model?.name ?? null,
  }))
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.ok(url.endsWith('chat_history?limit=50&offset=50'))
    assert.equal(options.credentials, 'include')
    return json(entries)
  })
  assert.deepEqual(await api.getChatHistory(50), entries)
})

for (const authenticated of [false, true]) {
  test(`private Blob request uses the existing HttpOnly session (${authenticated ? 'user' : 'guest'})`, async t => {
    const api = await loadSource('services/requests.ts')
    if (authenticated) api.rememberSession({ id: 1, email: 'owner@example.com' })
    const controller = new AbortController()
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      if (url.endsWith('/users/me')) return json({}, 401)
      if (url.endsWith('/Text-to-Masterpiece')) return json({ ok: true })
      assert.equal(url, `${api.API_BASE_URL}/images/7`)
      assert.equal(options.credentials, 'include')
      assert.equal(options.signal, controller.signal)
      assert.equal(options.headers, undefined) // JWT/guest cookies are not exposed to JS.
      return new Response(new Blob(['image'], { type: 'image/png' }), { headers: { 'Content-Type': 'image/png' } })
    })
    const image = await api.getGenerationImage(7, controller.signal)
    assert.ok(image instanceof Blob)
    assert.equal(image.type, 'image/png')
  })
}

for (const [status, message] of [[401, /session has expired/], [404, /not found/], [503, /storage unavailable/]]) {
  test(`private image HTTP ${status} is shown to the caller`, async t => {
    const api = await loadSource('services/requests.ts')
    api.rememberSession({ id: 1, email: 'owner@example.com' })
    t.mock.method(globalThis, 'fetch', async () => json({ detail: 'storage unavailable' }, status))
    await assert.rejects(api.getGenerationImage(7), message)
  })
}

test('interrupted private image stream has a readable error', async t => {
  const api = await loadSource('services/requests.ts')
  api.rememberSession({ id: 1, email: 'owner@example.com' })
  t.mock.method(globalThis, 'fetch', async () => ({ ok: true, status: 200,
    blob: async () => { throw new TypeError('stream terminated') } }))
  await assert.rejects(api.getGenerationImage(7), /download was interrupted/)
})

test('model selector displays server names and the selected model', async () => {
  const { ModelSelect } = await loadSource('components/chat/ModelSelect.tsx')
  const html = renderToStaticMarkup(createElement(ModelSelect, {
    models, value: models[1].model_id, loading: false, error: '', disabled: false,
    onChange() {}, onRetry() {},
  }))
  assert.match(html, /value="cloudflare\/flux-2-klein-4b" selected=""/)
  assert.match(html, /FLUX\.1-schnell/)
  assert.doesNotMatch(html, /disabled=""/)
})

for (const state of [
  { loading: true, error: '', message: /Loading models/ },
  { loading: false, error: 'Unable to load models', message: /role="alert"/ },
  { loading: false, error: '', message: /No models available/ },
]) {
  test(`model selector handles unavailable catalogue: ${state.loading ? 'loading' : state.error || 'empty'}`, async () => {
    const { ModelSelect } = await loadSource('components/chat/ModelSelect.tsx')
    const html = renderToStaticMarkup(createElement(ModelSelect, {
      models: [], value: '', disabled: false, onChange() {}, onRetry() {}, ...state,
    }))
    assert.match(html, /disabled=""/)
    assert.match(html, state.message)
  })
}

test('send button is disabled without a valid model even when prompt is nonempty', async () => {
  const { ChatInput } = await loadSource('components/chat/ChatInput.tsx')
  const html = renderToStaticMarkup(createElement(ChatInput, {
    value: 'city', disabled: true, onChange() {}, onSend() {},
  }))
  assert.match(html, /class="send-btn" disabled=""/)
})

test('sidebar displays one first-prompt title per chat; restored generations keep legacy model fallback', async () => {
  const { ChatHistory } = await loadSource('components/chat/ChatHistory.tsx')
  const { MessageList } = await loadSource('components/chat/MessageList.tsx')
  const entries = [models[1], null].map((model, index) => ({
    id: index + 1, prompt: 'city', created_at: '2026-01-01T00:00:00Z',
    model_id: model?.model_id ?? null, model_name: model?.name ?? null,
  }))
  const history = renderToStaticMarkup(createElement(ChatHistory, {
    entries: entries.map((entry, index) => ({ id: String(index), title: `First prompt ${index}`,
      created_at: entry.created_at, updated_at: entry.created_at })),
    selectedId: '0', loading: false, error: '', hasMore: false, disabled: false,
    onSelect() {}, onLoadMore() {}, onRetry() {},
  }))
  assert.match(history, /First prompt 0/)
  assert.match(history, /First prompt 1/)
  assert.match(history, /aria-current="true"/)
  const messages = renderToStaticMarkup(createElement(MessageList, {
    messages: entries.map(entry => ({ role: 'assistant', content: 'Result:', generationId: entry.id, modelName: entry.model_name })),
    loading: false,
  }))
  assert.match(messages, /FLUX-2-klein-4b/)
  assert.match(messages, /Модель неизвестна/)
})
