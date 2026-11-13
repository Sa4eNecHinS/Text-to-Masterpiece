import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import { act, createElement } from 'react'
import { create } from 'react-test-renderer'

const A = '01900000-0000-7000-8000-000000000001'
const B = '01900000-0000-7000-8000-000000000002'
const model = { model_id: 'cloudflare/flux-1-schnell', name: 'FLUX.1-schnell' }
const summary = id => ({ id, title: `First ${id}`, created_at: '2020-01-01', updated_at: '2021-01-01' })
const rows = prefix => [0, 1].map(id => ({ id: id + 1, prompt: `${prefix}-${id}`,
  model_id: null, model_name: null, created_at: '2020-01-01' }))
const result = id => ({ chat_id: id, generation_id: 1, model_id: model.model_id, model_name: model.name })
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const moduleUrl = source => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
let instance = 0

async function sourceModule(path, imports = {}) {
  const source = await readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } })
  return moduleUrl(outputText.replace(/from ["']([^"']+)["']/g, (_, name) => {
    const url = imports[name] || (name.startsWith('react') ? import.meta.resolve(name) : undefined)
    assert.ok(url, `Unmapped test import: ${name}`)
    return `from ${JSON.stringify(url)}`
  }) + `\n// instance ${instance++}`)
}

// Mount real React hooks/page logic; only HTTP/auth and visual leaf components
// are replaced. No browser, real API, or Cloudflare is involved.
async function harness(t, options = {}) {
  const key = `__t2mChatTest${instance++}`
  const fixture = {
    user: { id: 1, email: 'owner@example.com' }, backend: { status: 'ready', retryVersion: 0 },
    generateCalls: [], chatCalls: [], listCalls: [],
    getModels: async () => [model], getChats: async () => [], getChat: async () => [],
    generateImage: async (prompt, modelId, chatId) => result(chatId || A), ...options,
  }
  fixture.initializeSession ??= async () => fixture.user
  globalThis[key] = fixture
  const previousStorage = globalThis.sessionStorage
  const previousActEnvironment = globalThis.IS_REACT_ACT_ENVIRONMENT
  const storage = new Map()
  globalThis.sessionStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) }
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  const originalError = console.error
  t.mock.method(console, 'error', (...args) => {
    if (!String(args[0]).startsWith('react-test-renderer is deprecated')) originalError(...args)
  })
  let tree
  t.after(async () => {
    if (tree) await act(async () => tree.unmount())
    globalThis.sessionStorage = previousStorage
    globalThis.IS_REACT_ACT_ENVIRONMENT = previousActEnvironment
    delete globalThis[key]
  })
  const state = `globalThis[${JSON.stringify(key)}]`
  const api = moduleUrl(`export const SERVER_STARTING_MESSAGE = 'The server is starting. Please try again shortly.'; export const retryBackendReadiness = async () => {};\n` + ['getModels', 'initializeSession', 'getChats', 'getChat', 'generateImage'].map(name =>
    `export const ${name} = (...args) => {
      ${name === 'getChat' ? `${state}.chatCalls.push(args);` : ''}
      ${name === 'getChats' ? `${state}.listCalls.push(args);` : ''}
      ${name === 'generateImage' ? `${state}.generateCalls.push(args);` : ''}
      return ${state}.${name}(...args);
    };`).join('\n'))
  const auth = moduleUrl(`export const useAuth = () => ({ user: ${state}.user });`)
  const backend = moduleUrl(`export const useBackendReadiness = () => ${state}.backend;`)
  const hook = await sourceModule('components/chat/useChatHistory.ts', {
    '@/components/auth/authContext': auth, '@/services/requests': api,
    '@/components/useBackendReadiness': backend,
  })
  const currentChatUrl = await sourceModule('utils/currentChat.ts')
  const currentChat = await import(currentChatUrl)
  if (options.saved) currentChat.saveCurrentChat(options.saved)
  const visuals = moduleUrl(`import { createElement } from ${JSON.stringify(import.meta.resolve('react'))};\n` +
    ['AppLayout', 'ChatInput', 'MessageList', 'ModelSelect'].map(name =>
      `export function ${name}(props) { return createElement(${JSON.stringify(name)}, props, props.children); }`).join('\n'))
  const page = await sourceModule('pages/generate/GeneratePage.tsx', {
    '@/services/requests': api, '@/components/auth/authContext': auth,
    '@/components/useBackendReadiness': backend,
    '@/components/chat/useChatHistory': hook, '@/utils/currentChat': currentChatUrl,
    '@/components/layout/AppLayout': visuals, '@/components/chat/ChatInput': visuals,
    '@/components/chat/MessageList': visuals, '@/components/chat/ModelSelect': visuals,
  })
  let Component = (await import(page)).default
  if (options.probe) {
    const { useChatHistory } = await import(hook)
    Component = () => createElement('HistoryProbe', useChatHistory())
  }
  await act(async () => { tree = create(createElement(Component)) })
  return {
    fixture, currentChat, storage,
    layout: () => tree.root.findByType('AppLayout').props,
    input: () => tree.root.findByType('ChatInput').props,
    messages: () => tree.root.findAllByType('MessageList')[0]?.props.messages ?? [],
    history: () => tree.root.findByType('HistoryProbe').props,
    text: () => JSON.stringify(tree.toJSON()),
    updateBackend: async backend => {
      fixture.backend = backend
      await act(async () => { tree.update(createElement(Component)) })
    },
    updateOwner: async user => {
      fixture.user = user
      await act(async () => { tree.update(createElement(Component)) })
    },
  }
}

async function send(h, prompt) {
  await act(async () => h.input().onChange(prompt))
  await act(async () => { await h.input().onSend() })
}

test('first success remembers chat_id; continuation reuses it; New chat resets it', async t => {
  let nextChat = 0
  const h = await harness(t, { generateImage: async (prompt, modelId, chatId) => result(chatId || [A, B][nextChat++]) })
  await send(h, 'first')
  assert.equal(h.layout().history.selectedId, A)
  await send(h, 'second')
  assert.equal(h.messages().length, 4)
  assert.deepEqual(h.fixture.generateCalls.map(call => call[2]), [null, A])
  await act(async () => h.layout().onNewChat())
  assert.equal(h.layout().history.selectedId, null)
  assert.deepEqual(h.messages(), [])
  await send(h, 'new first')
  assert.equal(h.layout().history.selectedId, B)
  assert.equal(h.fixture.generateCalls[2][2], null)
  assert.equal(h.currentChat.readCurrentChat(1).selectedId, B)
})

test('rapid chat switching and New chat discard stale asynchronous responses', async t => {
  const first = deferred(), second = deferred(), third = deferred()
  const queue = [first, second, third]
  const h = await harness(t, { getChat: () => queue.shift().promise })
  await act(async () => h.layout().history.onSelect(summary(A)))
  await act(async () => h.layout().history.onSelect(summary(B)))
  assert.equal(h.fixture.chatCalls[0][1].aborted, true)
  await act(async () => second.resolve(rows('B')))
  assert.deepEqual(h.messages().filter(row => row.role === 'user').map(row => row.content), ['B-0', 'B-1'])
  await act(async () => first.resolve(rows('A')))
  assert.equal(h.layout().history.selectedId, B)
  assert.equal(h.messages()[0].content, 'B-0')
  await act(async () => h.layout().history.onSelect(summary(A)))
  await act(async () => h.layout().onNewChat())
  await act(async () => third.resolve(rows('late')))
  assert.deepEqual(h.messages(), [])
  assert.equal(h.layout().history.selectedId, null)
})

test('a failed chat load blocks sending and can be retried without creating another chat', async t => {
  let fail = true
  const h = await harness(t, { getChat: async () => {
    if (fail) throw new Error('Unable to load chat.')
    return rows('retry')
  } })
  await act(async () => h.layout().history.onSelect(summary(A)))
  assert.equal(h.input().disabled, true)
  await send(h, 'must not send')
  assert.deepEqual(h.fixture.generateCalls, [])
  fail = false
  await act(async () => h.layout().history.onSelect(summary(A)))
  assert.equal(h.input().disabled, false)
  assert.equal(h.layout().history.selectedId, A)
  assert.equal(h.messages().length, 4)
  assert.equal(h.fixture.chatCalls.length, 2)
})

test('reload refetches every generation, rather than trusting cached images', async t => {
  const h = await harness(t, {
    saved: { owner: 1, selectedId: A, messages: [{ role: 'user', content: 'stale' }], input: 'draft' },
    getChat: async () => rows('server'),
  })
  assert.equal(h.layout().history.selectedId, A)
  assert.equal(h.input().value, 'draft')
  assert.equal(h.messages().length, 4)
  assert.equal(h.messages()[0].content, 'server-0')
  assert.equal(h.fixture.chatCalls[0][0], A)
  assert.equal(h.currentChat.readCurrentChat(2), null)
  h.storage.set('ttm.current-chat.v3', JSON.stringify({ owner: 1, selectedId: 123, input: '', messages: [] }))
  assert.equal(h.currentChat.readCurrentChat(1), null)
})

test('logout clears the previous owner and ignores its pending detail response', async t => {
  const pending = deferred()
  const h = await harness(t, { getChat: () => pending.promise })
  h.fixture.getChats = async () => h.fixture.user ? [summary(A)] : []
  await act(async () => h.layout().history.onSelect(summary(A)))
  await act(async () => h.layout().onSignedOut())
  await h.updateOwner(null)
  await act(async () => pending.resolve(rows('previous-owner')))
  assert.equal(h.layout().history.selectedId, null)
  assert.deepEqual(h.messages(), [])
  assert.deepEqual(h.layout().history.entries, [])
  assert.equal(h.currentChat.readCurrentChat(null).selectedId, null)
})

test('logout remains ready if the auth update commits before the signed-out callback', async t => {
  const h = await harness(t)
  await send(h, 'previous owner')
  await h.updateOwner(null)
  await act(async () => h.layout().onSignedOut())
  assert.equal(h.input().loading, false)
  assert.equal(h.layout().history.disabled, false)
  assert.equal(h.layout().history.selectedId, null)
  assert.deepEqual(h.messages(), [])
})

test('guest sign-in reloads the transferred active chat under the new owner', async t => {
  const h = await harness(t, {
    user: null, saved: { owner: null, selectedId: A, input: '', messages: [] },
    getChat: async () => rows('guest'),
  })
  await h.updateOwner({ id: 2, email: 'registered@example.com' })
  assert.equal(h.layout().history.selectedId, A)
  assert.equal(h.messages().length, 4)
  assert.equal(h.fixture.chatCalls.length, 2)
  assert.equal(h.currentChat.readCurrentChat(2).selectedId, A)
})

test('owner change ignores a late generation result', async t => {
  const pending = deferred()
  const h = await harness(t, { generateImage: () => pending.promise })
  await act(async () => h.input().onChange('old-owner'))
  await act(async () => { void h.input().onSend() })
  await h.updateOwner({ id: 2, email: 'other@example.com' })
  await act(async () => pending.resolve(result(A)))
  assert.deepEqual(h.messages(), [])
  assert.equal(h.layout().history.selectedId, null)
  assert.equal(h.input().loading, false)
})

test('cold start leaves the composer editable and restores models/session/history without sending the draft', async t => {
  const session = deferred(), catalogue = deferred(), history = deferred()
  const h = await harness(t, {
    backend: { status: 'starting', retryVersion: 0 },
    saved: { owner: 1, selectedId: A, input: 'old saved draft', messages: [] },
    initializeSession: () => session.promise,
    getModels: () => catalogue.promise,
    getChats: () => history.promise,
    getChat: async () => rows('restored'),
  })
  assert.equal(h.input().loading, false)
  assert.equal(h.input().disabled, false)
  await send(h, 'my prompt while Render wakes up')
  assert.equal(h.input().value, 'my prompt while Render wakes up')
  assert.match(h.text(), /The server is starting. Please try again shortly./)
  assert.deepEqual(h.fixture.generateCalls, [])
  await h.updateBackend({ status: 'ready', retryVersion: 0 })
  await act(async () => {
    session.resolve(h.fixture.user)
    catalogue.resolve([model])
    history.resolve([summary(A)])
  })
  assert.equal(h.input().value, 'my prompt while Render wakes up')
  assert.equal(h.layout().history.selectedId, A)
  assert.equal(h.layout().history.entries.length, 1)
  assert.equal(h.input().modelSelect.models.length, 1)
  assert.equal(h.messages().length, 4)
  assert.doesNotMatch(h.text(), /The server is starting/)
  assert.deepEqual(h.fixture.generateCalls, [])
  await act(async () => { await h.input().onSend() })
  assert.deepEqual(h.fixture.generateCalls[0], ['my prompt while Render wakes up', model.model_id, A])
})

test('manual recovery reloads failed initialization without overwriting edits or the saved selection', async t => {
  const fail = async () => { throw new Error('Server temporarily unavailable') }
  const h = await harness(t, {
    backend: { status: 'unavailable', retryVersion: 0 },
    saved: { owner: 1, selectedId: A, input: 'old saved draft', messages: [] },
    initializeSession: fail, getModels: fail, getChats: fail,
  })
  await send(h, 'keep this new draft')
  assert.equal(h.input().loading, false)
  assert.deepEqual(h.fixture.generateCalls, [])
  h.fixture.initializeSession = async () => h.fixture.user
  h.fixture.getModels = async () => [model]
  h.fixture.getChats = async () => [summary(A)]
  h.fixture.getChat = async () => rows('recovered')
  await h.updateBackend({ status: 'ready', retryVersion: 1 })
  assert.equal(h.input().value, 'keep this new draft')
  assert.equal(h.layout().history.selectedId, A)
  assert.equal(h.layout().history.error, '')
  assert.equal(h.input().modelSelect.error, '')
  assert.doesNotMatch(h.text(), /Server temporarily unavailable|Unable to restore/)
  assert.deepEqual(h.fixture.generateCalls, [])
  assert.equal(h.fixture.listCalls.length, 2)
})

test('recovery preserves the current chat, draft and model selection for an initialized owner', async t => {
  const h = await harness(t, {
    saved: { owner: 1, selectedId: A, input: 'draft', messages: [] },
    getChat: async () => rows('chat'),
    getModels: async () => [model, { model_id: 'second', name: 'Second' }],
  })
  await act(async () => {
    h.input().modelSelect.onChange('second')
    h.input().onChange('still editing')
  })
  await h.updateBackend({ status: 'unavailable', retryVersion: 0 })
  await h.updateBackend({ status: 'ready', retryVersion: 1 })
  assert.equal(h.layout().history.selectedId, A)
  assert.equal(h.input().value, 'still editing')
  assert.equal(h.input().modelSelect.value, 'second')
  assert.deepEqual(h.fixture.generateCalls, [])
})

test('a permanent session error is not presented as a cold start when sending', async t => {
  const h = await harness(t, {
    backend: { status: 'error', retryVersion: 0 },
    initializeSession: async () => { throw new Error('Access denied (HTTP 403).') },
  })
  await send(h, 'draft')
  assert.equal(h.input().value, 'draft')
  assert.match(h.text(), /Access denied/)
  assert.doesNotMatch(h.text(), /The server is starting/)
  assert.deepEqual(h.fixture.generateCalls, [])
})

test('sidebar pagination uses chats, deduplicates IDs, and resets for another owner', async t => {
  const firstPage = Array.from({ length: 50 }, (_, index) => summary(`chat-${index}`))
  const h = await harness(t, { probe: true, getChats: async offset => offset ? [firstPage[49], summary(B)] : firstPage })
  assert.equal(h.history().entries.length, 50)
  assert.equal(h.history().hasMore, true)
  await act(async () => { await h.history().loadMore() })
  assert.equal(h.history().entries.length, 51)
  assert.equal(h.fixture.listCalls[1][0], 50)
  const pending = deferred()
  h.fixture.getChats = async () => pending.promise
  await act(async () => h.history().refresh())
  h.fixture.getChats = async () => []
  await h.updateOwner(null)
  await act(async () => pending.resolve(firstPage))
  assert.deepEqual(h.history().entries, [])
  assert.equal(h.history().hasMore, false)
})
