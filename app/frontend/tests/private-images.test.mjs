import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'
import { act, createElement } from 'react'
import { create } from 'react-test-renderer'

let instance = 0
const blob = () => new Blob(['image-data'], { type: 'image/png' })
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const moduleUrl = text => `data:text/javascript;base64,${Buffer.from(text).toString('base64')}`
async function sourceModule(path, imports = {}) {
  const source = await readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')
  const { outputText } = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX,
  } })
  return moduleUrl(outputText.replace(/from ["']([^"']+)["']/g, (_, name) =>
    `from ${JSON.stringify(imports[name] || import.meta.resolve(name))}`) + `\n// ${instance++}`)
}

async function harness(t, options = {}) {
  const key = `__t2mImages${instance++}`
  const fixture = { user: { id: 1 }, calls: [], getImage: async () => blob(), ...options }
  globalThis[key] = fixture
  const oldAct = globalThis.IS_REACT_ACT_ENVIRONMENT
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
  const originalError = console.error
  t.mock.method(console, 'error', (...args) => {
    if (!String(args[0]).startsWith('react-test-renderer is deprecated')) originalError(...args)
  })
  const created = [], revoked = []
  t.mock.method(URL, 'createObjectURL', value => {
    assert.ok(value instanceof Blob)
    const url = `blob:test-${created.length + 1}`
    created.push(url)
    return url
  })
  t.mock.method(URL, 'revokeObjectURL', url => revoked.push(url))
  const state = `globalThis[${JSON.stringify(key)}]`
  const api = moduleUrl(`export const getGenerationImage = (...args) => {
    ${state}.calls.push(args); return ${state}.getImage(...args);
  };`)
  const auth = moduleUrl(`export const useAuth = () => ({ user: ${state}.user });`)
  const imageUrl = await sourceModule('components/chat/PrivateImage.tsx', {
    '@/services/requests': api, '@/components/auth/authContext': auth,
  })
  const { PrivateImage } = await import(imageUrl)
  const { MessageList } = await import(await sourceModule('components/chat/MessageList.tsx', {
    '@/components/chat/PrivateImage': imageUrl,
  }))
  const { generationMessages } = await import(await sourceModule('utils/currentChat.ts'))
  const Component = options.history ? MessageList : PrivateImage
  let tree
  const props = options.history ? { messages: generationMessages(options.history), loading: false } : { generationId: 1 }
  await act(async () => { tree = create(createElement(Component, props)) })
  t.after(async () => {
    if (tree) await act(async () => tree.unmount())
    delete globalThis[key]
    globalThis.IS_REACT_ACT_ENVIRONMENT = oldAct
  })
  return {
    fixture, created, revoked,
    images: () => tree.root.findAllByType('img'),
    alerts: () => tree.root.findAll(node => node.props.role === 'alert'),
    retry: async () => { await act(async () => tree.root.findByType('button').props.onClick()) },
    update: async next => { await act(async () => tree.update(createElement(Component, next))) },
    unmount: async () => { await act(async () => tree.unmount()); tree = null },
  }
}

test('private images render Blob URLs, do not refetch per render, and revoke on unmount', async t => {
  const h = await harness(t)
  assert.equal(h.images()[0].props.src, 'blob:test-1')
  await h.update({ generationId: 1 })
  assert.equal(h.fixture.calls.length, 1)
  await h.unmount()
  assert.deepEqual(h.revoked, ['blob:test-1'])
})

test('history fetches each generation by ID and New chat releases every Blob', async t => {
  const h = await harness(t, { history: [1, 2].map(id => ({ id, prompt: `prompt-${id}`, model_name: null })) })
  assert.deepEqual(h.fixture.calls.map(call => call[0]), [1, 2])
  assert.equal(h.images().length, 2)
  await h.update({ messages: [], loading: false })
  assert.equal(h.images().length, 0)
  assert.deepEqual(h.revoked.sort(), h.created.sort())
})

test('switching chats aborts old fetches; late responses never create or display a Blob', async t => {
  const first = deferred(), second = deferred(), third = deferred()
  const queue = [first, second, third]
  const h = await harness(t, { getImage: () => queue.shift().promise })
  await h.update({ generationId: 2 })
  assert.equal(h.fixture.calls[0][1].aborted, true)
  await act(async () => second.resolve(blob()))
  assert.equal(h.images()[0].props.src, 'blob:test-1')
  await act(async () => first.resolve(blob()))
  assert.equal(h.created.length, 1)
  await h.update({ generationId: 3 })
  assert.equal(h.images().length, 0)
  assert.deepEqual(h.revoked, ['blob:test-1'])
  await h.unmount()
  await act(async () => third.resolve(blob()))
  assert.equal(h.created.length, 1)
})

test('guest sign-in refetches the transferred image; logout removes the previous owner Blob', async t => {
  const h = await harness(t, { user: null })
  h.fixture.user = { id: 5 }
  await h.update({ generationId: 1 })
  assert.equal(h.fixture.calls.length, 2)
  assert.deepEqual(h.revoked, ['blob:test-1'])
  assert.equal(h.images()[0].props.src, 'blob:test-2')
  h.fixture.user = null
  h.fixture.getImage = async () => { throw new Error('Image not found or no longer available.') }
  await h.update({ generationId: 1 })
  assert.equal(h.images().length, 0)
  assert.equal(h.alerts().length, 1)
  assert.deepEqual(h.revoked, ['blob:test-1', 'blob:test-2'])
})

for (const error of ['Your session has expired.', 'Image not found.', 'Image storage is unavailable.']) {
  test(`image errors are displayed without automatic retries: ${error}`, async t => {
    const h = await harness(t, { getImage: async () => { throw new Error(error) } })
    assert.equal(h.images().length, 0)
    assert.equal(h.alerts().length, 1)
    assert.equal(h.fixture.calls.length, 1)
    h.fixture.getImage = async () => blob()
    await h.retry()
    assert.equal(h.images().length, 1)
    assert.equal(h.fixture.calls.length, 2)
  })
}

test('browser decode failures are handled and their Blob is revoked on retry', async t => {
  const h = await harness(t)
  const staleError = h.images()[0].props.onError
  await act(async () => staleError())
  assert.equal(h.alerts().length, 1)
  await h.retry()
  assert.deepEqual(h.revoked, ['blob:test-1'])
  assert.equal(h.images()[0].props.src, 'blob:test-2')
  await act(async () => staleError())
  assert.equal(h.images()[0].props.src, 'blob:test-2')
})
