export const API_BASE_URL =
  import.meta.env.VITE_API_URL ?? '/api'


export type ImageModel = { model_id: string; name: string }
export type GenerateResponse = { chat_id: string; generation_id: number; model_id: string; model_name: string }
export type ChatSummary = { id: string; title: string; created_at: string; updated_at: string }

export async function getModels(signal?: AbortSignal): Promise<ImageModel[]> {
  const response = await readAPI(`${API_BASE_URL}/Text-to-Masterpiece/models`, { signal })
  if (!response.ok) throw new Error((await responseDetail(response)) || `Unable to load models (HTTP ${response.status}).`)
  const data: unknown = await response.json()
  if (!Array.isArray(data) || !data.every(model => model && typeof model.model_id === 'string'
    && model.model_id.trim() && typeof model.name === 'string' && model.name.trim())) {
    throw new Error('The server returned an invalid model catalogue.')
  }
  return data as ImageModel[]
}
export type ChatHistoryEntry = {
  id: number
  prompt: string
  created_at: string
  model_id: string | null
  model_name: string | null
}

export async function getChatHistory(offset = 0, signal?: AbortSignal): Promise<ChatHistoryEntry[]> {
  await initializeSession()
  const response = await readAPI(`${API_BASE_URL}/Text-to-Masterpiece/chat_history?limit=50&offset=${offset}`, {
    credentials: 'include', signal,
  })
  if (!response.ok) throw new Error((await responseDetail(response)) || `Unable to load history (HTTP ${response.status}).`)
  const data: unknown = await response.json()
  if (!Array.isArray(data) || !data.every(entry => entry && typeof entry.id === 'number'
    && typeof entry.prompt === 'string' && typeof entry.created_at === 'string')) {
    throw new Error('The server returned an invalid history response.')
  }
  return data as ChatHistoryEntry[]
}

export async function getChats(offset = 0, signal?: AbortSignal): Promise<ChatSummary[]> {
  await initializeSession()
  const response = await readAPI(`${API_BASE_URL}/Text-to-Masterpiece/chats?limit=50&offset=${offset}`, {
    credentials: 'include', signal,
  })
  if (!response.ok) throw new Error((await responseDetail(response)) || `Unable to load chats (HTTP ${response.status}).`)
  const data: unknown = await response.json()
  if (!Array.isArray(data) || !data.every(chat => chat && typeof chat.id === 'string' && chat.id.trim()
    && typeof chat.title === 'string' && typeof chat.created_at === 'string' && typeof chat.updated_at === 'string')) {
    throw new Error('The server returned an invalid chat list.')
  }
  return data as ChatSummary[]
}

export async function getChat(chatId: string, signal?: AbortSignal): Promise<ChatHistoryEntry[]> {
  await initializeSession()
  const response = await readAPI(`${API_BASE_URL}/Text-to-Masterpiece/chats/${encodeURIComponent(chatId)}`, {
    credentials: 'include', signal,
  })
  if (!response.ok) throw new Error((await responseDetail(response)) || `Unable to load chat (HTTP ${response.status}).`)
  const data: unknown = await response.json()
  if (!Array.isArray(data) || !data.every(entry => entry && typeof entry.id === 'number'
    && typeof entry.prompt === 'string' && typeof entry.created_at === 'string'
    && (entry.model_id === null || typeof entry.model_id === 'string')
    && (entry.model_name === null || typeof entry.model_name === 'string'))) {
    throw new Error('The server returned an invalid chat history.')
  }
  return data as ChatHistoryEntry[]
}

// Share initialization while the browser is still waiting for its session cookie.
let guestSessionRequest: Promise<void> | undefined

async function responseDetail(resp: Response): Promise<string | undefined> {
  try {
    const data: unknown = await resp.json()
    if (data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string') {
      return data.detail
    }
  } catch {
    // Error bodies may be plain text or empty.
  }
  return undefined
}

export async function generateImage(prompt: string, modelId: string, chatId?: string | null): Promise<GenerateResponse> {
  await initializeSession()
  const resp = await fetch(`${API_BASE_URL}/Text-to-Masterpiece/generate`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, model_id: modelId, ...(chatId ? { chat_id: chatId } : {}) })
  })

  if (!resp.ok) {
    const detail = await responseDetail(resp)
    if (resp.status === 409) {
      throw new Error(`${detail || 'Image generation is already in progress.'} Please wait for it to finish; it may be running in another tab.`)
    }
    if (resp.status === 503) {
      throw new Error(detail || 'Server is busy. Please try again later.')
    }
    throw new Error(detail || `Image generation failed (HTTP ${resp.status})`)
  }

  let data: unknown
  try {
    data = await resp.json()
  } catch {
    throw new Error('Image generation returned an invalid response')
  }
  if (!data || typeof data !== 'object' || !('generation_id' in data)
    || typeof data.generation_id !== 'number' || !Number.isSafeInteger(data.generation_id) || data.generation_id <= 0) {
    throw new Error('Image generation response did not contain a valid generation_id')
  }
  if (!('model_id' in data) || typeof data.model_id !== 'string'
    || !('model_name' in data) || typeof data.model_name !== 'string') {
    throw new Error('Image generation response did not contain valid model details')
  }
  if (!('chat_id' in data) || typeof data.chat_id !== 'string' || !data.chat_id.trim()) {
    throw new Error('Image generation response did not contain a valid chat_id')
  }
  return data as GenerateResponse
}

export async function getGenerationImage(generationId: number, signal?: AbortSignal): Promise<Blob> {
  await initializeSession()
  // The existing JWT is HttpOnly: the browser sends it (or the guest identity)
  // in cookies. Never copy tokens/guest IDs into JS or into object-store URLs.
  const response = await fetch(`${API_BASE_URL}/images/${generationId}`, { credentials: 'include', signal })
  if (response.status === 401) throw new Error('Your session has expired. Please sign in again.')
  if (response.status === 404) throw new Error('Image not found or no longer available.')
  if (!response.ok) throw new Error((await responseDetail(response)) || `Unable to load image (HTTP ${response.status}).`)
  let blob: Blob
  try {
    blob = await response.blob()
  } catch (error) {
    if (signal?.aborted) throw error
    throw new Error('Image download was interrupted. Please try again.')
  }
  if (!['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(blob.type)) {
    throw new Error('The server returned an invalid image.')
  }
  return blob
}

export type User = { id: number; email: string }
export type AuthField = 'email' | 'password' | 'confirmPassword'

export class AuthError extends Error {
  status?: number
  fields: Partial<Record<AuthField, string>>

  constructor(message: string, status?: number, fields: Partial<Record<AuthField, string>> = {}) {
    super(message)
    this.status = status
    this.fields = fields
  }
}

async function authResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    if (response.status === 401) throw new AuthError('Incorrect email or password.', 401)
    if (response.status === 409) throw new AuthError('This email is already in use.', 409, { email: 'This email is already in use.' })
    if (response.status >= 500) throw new AuthError('The server is unavailable. Please try again later.', response.status)
    if (response.status === 422) {
      const fields: Partial<Record<AuthField, string>> = {}
      try {
        const data = await response.json()
        for (const issue of data.detail ?? []) {
          const field = issue.loc?.at(-1)
          if (field === 'email' || field === 'username') fields.email = 'Please enter a valid email.'
          if (field === 'password') fields.password = 'Please check your password.'
        }
      } catch { /* A validation response may not contain JSON. */ }
      throw new AuthError('Please check the form and try again.', 422, fields)
    }
    throw new AuthError('Unable to authenticate. Please try again.', response.status)
  }
  return response.json()
}

async function authFetch(path: string, options?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE_URL}/auth/Text-to-Masterpiece${path}`, { ...options, credentials: 'include' })
  } catch {
    throw new AuthError('Network error. Check your connection and try again.')
  }
}

export type RegisterRequest = {
  email: string
  password: string
}

export async function registerUser(data: RegisterRequest) {
  if (guestSessionRequest) await guestSessionRequest.catch(() => {})
  const resp = await authFetch('/registrate', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
  return authResponse<{ user: User }>(resp)
}

export async function loginUser(email: string, password: string) {
  if (guestSessionRequest) await guestSessionRequest.catch(() => {})
  const formData = new URLSearchParams()
  formData.append('username', email)
  formData.append('password', password)

  const resp = await authFetch('/token', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData
  })
  return authResponse<{ user: User }>(resp)
}

export async function logoutUser(): Promise<void> {
  if (guestSessionRequest) await guestSessionRequest.catch(() => {})
  const response = await authFetch('/logout', { method: 'POST' })
  await authResponse<{ message: string }>(response)
}

export function resetSession(): void {
  initialization = undefined
}

export const getCurrentUser = async () => {
  const res = await readAPI(`${API_BASE_URL}/auth/Text-to-Masterpiece/users/me`, { credentials: 'include' })
  if (res.status === 401) return null
  return authResponse<User>(res)
}

let initialization: Promise<User | null> | undefined

export function initializeSession(): Promise<User | null> {
  initialization ??= (async () => {
    const user = await getCurrentUser()
    if (!user) await startGuestSession()
    return user
  })().catch(error => {
    initialization = undefined
    throw error
  })
  return initialization
}

export function rememberSession(user: User): void {
  initialization = Promise.resolve(user)
}

export function startGuestSession(): Promise<void> {
  if (!guestSessionRequest) {
    guestSessionRequest = (async () => {
      // This GET can CREATE a guest: wait for readiness, but never replay an
      // ambiguous creation request automatically (e.g. lost Set-Cookie response).
      if (recoveryEnabled) await waitForReadiness()
      const resp = await fetch(`${API_BASE_URL}/Text-to-Masterpiece`, { credentials: 'include',
        ...(recoveryEnabled ? { signal: AbortSignal.timeout(10_000) } : {}),
      })
      if (!resp.ok) throw new Error((await responseDetail(resp)) || `Guest session failed (HTTP ${resp.status})`)
    })().finally(() => {
      // Do not cache forever: cookies may expire or be cleared between visits.
      guestSessionRequest = undefined
    })
  }
  return guestSessionRequest
}

// One bounded, on-demand recovery cycle for the whole application. Activated
// by AuthProvider, not a background keepalive and never used for mutation POSTs.
export const SERVER_STARTING_MESSAGE = 'The server is starting. Please try again shortly.'
export type BackendState = {
  status: 'idle' | 'checking' | 'starting' | 'ready' | 'unavailable' | 'error'
  retryVersion: number
}
let backendState: BackendState = { status: 'idle', retryVersion: 0 }
const backendListeners = new Set<() => void>()
let recoveryEnabled = false
let recoveryCycle: Promise<void> | undefined

export const getBackendState = () => backendState
export function subscribeBackend(listener: () => void) {
  backendListeners.add(listener)
  return () => { backendListeners.delete(listener) }
}
function publishBackend(status: BackendState['status'], manualSuccess = false) {
  backendState = { status, retryVersion: backendState.retryVersion + Number(manualSuccess) }
  backendListeners.forEach(listener => listener())
}
class ProbeHTTPError extends Error {
  status: number
  constructor(status: number) {
    super(`Server readiness check failed (HTTP ${status}).`)
    this.status = status
  }
}
function transientFailure(error: unknown): boolean {
  return error instanceof TypeError
    || (error instanceof Error && error.name === 'TimeoutError')
    || (error instanceof ProbeHTTPError && [502, 503, 504].includes(error.status))
}
function unavailableError() { return new Error('Server temporarily unavailable') }

function beginReadiness(manual = false, deadline = Date.now() + 120_000): Promise<void> {
  if (recoveryCycle) return recoveryCycle
  if (backendState.status === 'unavailable' && !manual) return Promise.reject(unavailableError())
  publishBackend('checking')
  recoveryCycle = (async () => {
    let attempt = 0
    while (Date.now() < deadline) {
      try {
        const response = await fetch(`${API_BASE_URL}/Text-to-Masterpiece/models`, {
          signal: AbortSignal.timeout(Math.max(1, Math.min(10_000, deadline - Date.now()))),
        })
        if (!response.ok) throw new ProbeHTTPError(response.status)
        publishBackend('ready', manual)
        return
      } catch (error) {
        if (!transientFailure(error)) {
          publishBackend('error') // 401/403 and other permanent errors are not cold start.
          throw error
        }
        publishBackend('starting')
        const remaining = deadline - Date.now()
        if (remaining <= 0) break
        const delay = Math.min(remaining, Math.min(10_000, 1000 * 2 ** attempt++) * (0.8 + Math.random() * 0.4))
        await new Promise(resolve => setTimeout(resolve, delay))
      }
    }
    publishBackend('unavailable')
    throw unavailableError()
  })().finally(() => { recoveryCycle = undefined })
  return recoveryCycle
}

export function startBackendReadiness(): Promise<void> {
  recoveryEnabled = true
  if (backendState.status === 'ready' || backendState.status === 'error') return Promise.resolve()
  return beginReadiness()
}
export function retryBackendReadiness(): Promise<void> {
  recoveryEnabled = true
  return beginReadiness(true)
}

// Cancelling a view must not cancel the shared readiness check for other views.
function abortable<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) return promise
  if (signal.aborted) return Promise.reject(signal.reason)
  return new Promise((resolve, reject) => {
    const abort = () => reject(signal.reason)
    signal.addEventListener('abort', abort, { once: true })
    promise.then(resolve, reject).finally(() => signal.removeEventListener('abort', abort))
  })
}
async function waitForReadiness(signal?: AbortSignal): Promise<void> {
  if (backendState.status === 'ready' || backendState.status === 'error') return
  await abortable(startBackendReadiness(), signal)
}

async function readAPI(url: string, options: RequestInit = {}): Promise<Response> {
  // Low-level API callers retain single-request semantics unless the app has
  // explicitly enabled recovery. AuthProvider enables it before passive effects.
  options.signal?.throwIfAborted()
  if (!recoveryEnabled) return fetch(url, options)
  const signal = options.signal ?? undefined
  const deadline = Date.now() + 120_000
  await waitForReadiness(signal)
  for (let attempt = 0; ; attempt++) {
    signal?.throwIfAborted()
    if (Date.now() >= deadline) throw unavailableError()
    try {
      const timeout = AbortSignal.timeout(Math.max(1, Math.min(10_000, deadline - Date.now())))
      const response = await fetch(url, { ...options, signal: signal ? AbortSignal.any([signal, timeout]) : timeout })
      if ([502, 503, 504].includes(response.status)) throw new ProbeHTTPError(response.status)
      return response
    } catch (error) {
      if (signal?.aborted || !transientFailure(error)) throw error
      if (attempt === 1) {
        publishBackend('unavailable')
        throw unavailableError()
      }
      await abortable(beginReadiness(false, deadline), signal)
    }
  }
}
