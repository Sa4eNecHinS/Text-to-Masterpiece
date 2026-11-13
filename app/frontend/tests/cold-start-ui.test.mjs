import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import { act, createElement as h, StrictMode } from 'react'
import { create } from 'react-test-renderer'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

let instance = 0
const url = text => `data:text/javascript;base64,${Buffer.from(text).toString('base64')}`
async function module(path, imports = {}) {
  const source = (await readFile(new URL(`../src/${path}`, import.meta.url), 'utf8'))
    .replace(/import\s+["'][^"']+\.css["'];?/g, '')
  const code = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText.replaceAll('import.meta.env.VITE_API_URL', 'undefined')
    .replace(/from ["']([^"']+)["']/g, (_, name) => {
      const target = imports[name] ?? (name.startsWith('react') ? import.meta.resolve(name) : undefined)
      assert.ok(target, `Unmapped import: ${name}`)
      return `from ${JSON.stringify(target)}`
    })
  return url(code + `\n// ${instance++}`)
}
const json = (body, status = 200) => new Response(JSON.stringify(body), { status })
const flush = () => new Promise(resolve => setImmediate(resolve))

async function setup(t, initiallyAvailable = false) {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 0 })
  t.mock.method(Math, 'random', () => 0.5)
  const oldStorage = globalThis.sessionStorage, oldAct = globalThis.IS_REACT_ACT_ENVIRONMENT
  const storage = new Map()
  globalThis.sessionStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) }
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  const originalError = console.error
  t.mock.method(console, 'error', (...args) => {
    if (!String(args[0]).startsWith('react-test-renderer is deprecated')) originalError(...args)
  })
  let available = initiallyAvailable
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    options?.signal?.throwIfAborted()
    calls.push([path, options])
    if (!available) return json({}, 503)
    if (path.endsWith('/models')) return json([{ model_id: 'cloudflare/flux-1-schnell', name: 'FLUX.1-schnell' }])
    if (path.endsWith('/users/me')) return json({}, 401)
    if (path.endsWith('/Text-to-Masterpiece')) return json({ ok: true })
    if (path.includes('/chats?')) return json([])
    throw new Error(`Unexpected request: ${path}`)
  })
  const apiUrl = await module('services/requests.ts')
  const api = await import(apiUrl)
  const hook = await module('components/useBackendReadiness.ts', { '@/services/requests': apiUrl })
  const context = await module('components/auth/authContext.ts')
  const auth = await module('components/auth/AuthProvider.tsx', {
    '@/services/requests': apiUrl, './authContext': context, '@/components/useBackendReadiness': hook,
  })
  const notice = await module('components/BackendNotice.tsx', {
    '@/services/requests': apiUrl, './useBackendReadiness': hook,
  })
  const history = await module('components/chat/useChatHistory.ts', {
    '@/services/requests': apiUrl, '@/components/auth/authContext': context, '@/components/useBackendReadiness': hook,
  })
  const currentChat = await module('utils/currentChat.ts')
  const visuals = url(`import { createElement } from ${JSON.stringify(import.meta.resolve('react'))};\n` +
    ['AppLayout', 'ChatInput', 'MessageList'].map(name =>
      `export function ${name}(props) { return createElement('${name}', props, props.children); }`).join('\n'))
  const generate = await module('pages/generate/GeneratePage.tsx', {
    '@/services/requests': apiUrl, '@/components/auth/authContext': context,
    '@/components/useBackendReadiness': hook, '@/components/chat/useChatHistory': history,
    '@/utils/currentChat': currentChat, '@/components/layout/AppLayout': visuals,
    '@/components/chat/ChatInput': visuals, '@/components/chat/MessageList': visuals,
  })
  const home = await module('pages/home/home.tsx', { '@/assets/b2_1786608771b8b1.png': url('export default "test.png"') })
  const AuthProvider = (await import(auth)).AuthProvider
  const BackendNotice = (await import(notice)).BackendNotice
  const Home = (await import(home)).Home
  const Generate = (await import(generate)).default
  const useAuth = (await import(context)).useAuth
  const Probe = () => h('AuthProbe', useAuth())
  let tree
  t.after(async () => {
    // No pending timers or requests survive the mounted application test.
    available = true
    if (api.getBackendState().status === 'starting') {
      await act(async () => { t.mock.timers.tick(120_000); await flush() })
    }
    if (tree) await act(async () => tree.unmount())
    globalThis.sessionStorage = oldStorage
    globalThis.IS_REACT_ACT_ENVIRONMENT = oldAct
  })
  await act(async () => {
    tree = create(h(StrictMode, null, h(AuthProvider, null,
      h(MemoryRouter, null, h(BackendNotice), h(Probe), h(Routes, null,
        h(Route, { path: '/', element: h(Home) }),
        h(Route, { path: '/Text-to-Masterpiece', element: h(Generate) }),
      )),
    )))
  })
  return {
    tree, api, calls,
    text: () => JSON.stringify(tree.toJSON()),
    input: () => tree.root.findByType('ChatInput').props,
    auth: () => tree.root.findByType('AuthProbe').props,
    layout: () => tree.root.findByType('AppLayout').props,
    available: () => { available = true },
    create: async () => act(async () => tree.root.findByType('a').props.onClick({
      button: 0, defaultPrevented: false, preventDefault() { this.defaultPrevented = true },
    })),
  }
}

test('real Home Create navigation stays usable during cold start; StrictMode does not duplicate recovery or guests', async t => {
  const app = await setup(t)
  assert.match(app.text(), /Starting server/)
  assert.match(app.text(), /continue preparing your prompt/)
  assert.equal(app.calls.length, 1)
  await app.create()
  assert.equal(app.input().loading, false)
  await act(async () => app.input().onChange('a draft before the server wakes'))
  await act(async () => app.input().onSend())
  assert.equal(app.input().value, 'a draft before the server wakes')
  assert.match(app.text(), /The server is starting. Please try again shortly./)
  app.available()
  await act(async () => { t.mock.timers.tick(1000); await flush() })
  assert.equal(app.api.getBackendState().status, 'ready')
  assert.doesNotMatch(app.text(), /Starting server|The server is starting/)
  assert.equal(app.input().value, 'a draft before the server wakes')
  assert.equal(app.input().modelSelect.models.length, 1)
  assert.equal(app.layout().history.loading, false)
  assert.equal(app.auth().sessionError, '')
  assert.equal(app.calls.filter(([path]) => path.endsWith('/users/me')).length, 1)
  assert.equal(app.calls.filter(([path]) => path.endsWith('/Text-to-Masterpiece')).length, 1)
  assert.equal(app.calls.filter(([path]) => path.includes('/chats?')).length, 1)
  assert.equal(app.calls.filter(([, options]) => options?.method === 'POST').length, 0)
  const count = app.calls.length
  await act(async () => { t.mock.timers.tick(600_000); await flush() })
  assert.equal(app.calls.length, count)
})

test('exhaustion exposes Try again; clicking it restores failed views without losing the draft or posting', async t => {
  const app = await setup(t)
  await app.create()
  await act(async () => app.input().onChange('keep my draft'))
  for (let elapsed = 0; elapsed < 120_000; elapsed += 1000) {
    await act(async () => { t.mock.timers.tick(1000); await flush() })
  }
  assert.equal(app.api.getBackendState().status, 'unavailable')
  assert.match(app.text(), /Server temporarily unavailable/)
  assert.equal(app.input().value, 'keep my draft')
  assert.equal(app.input().loading, false)
  const retry = app.tree.root.findAllByType('button').filter(button => button.children.includes('Try again'))
  assert.equal(retry.length, 1)
  app.available()
  await act(async () => { retry[0].props.onClick(); await flush() })
  assert.equal(app.api.getBackendState().status, 'ready')
  assert.equal(app.input().value, 'keep my draft')
  assert.equal(app.input().modelSelect.models.length, 1)
  assert.equal(app.layout().history.error, '')
  assert.equal(app.auth().sessionError, '')
  assert.doesNotMatch(app.text(), /Server temporarily unavailable|Starting server/)
  assert.equal(app.calls.filter(([, options]) => options?.method === 'POST').length, 0)
  assert.equal(app.calls.filter(([path]) => path.endsWith('/Text-to-Masterpiece')).length, 1)
})

test('immediate availability does not show a cold-start warning or block Create', async t => {
  const app = await setup(t, true)
  assert.equal(app.api.getBackendState().status, 'ready')
  assert.doesNotMatch(app.text(), /Starting server|Server temporarily unavailable/)
  await app.create()
  assert.equal(app.input().loading, false)
  assert.equal(app.input().modelSelect.models.length, 1)
})
