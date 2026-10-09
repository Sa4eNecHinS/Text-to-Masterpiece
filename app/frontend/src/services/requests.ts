export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export type GenerateResponse = { image_url: string }

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

export async function generateImage(prompt: string): Promise<string> {
  if (guestSessionRequest) await guestSessionRequest
  const resp = await fetch(`${API_BASE_URL}/Text-to-Masterpiece/generate`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt })
  })

  if (!resp.ok) {
    const detail = await responseDetail(resp)
    throw new Error(detail || `Image generation failed (HTTP ${resp.status})`)
  }

  let data: unknown
  try {
    data = await resp.json()
  } catch {
    throw new Error('Image generation returned an invalid response')
  }
  if (!data || typeof data !== 'object' || !('image_url' in data) || typeof data.image_url !== 'string' || !data.image_url.trim()) {
    throw new Error('Image generation response did not contain a valid image_url')
  }
  return data.image_url
}

export type RegisterRequest = {
  user_id: string
  email: string
  password: string
}

export async function registerUser(data: RegisterRequest) {
  const resp = await fetch(`${API_BASE_URL}/auth/Text-to-Masterpiece/registrate`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
  if (!resp.ok) {
    throw new Error((await responseDetail(resp)) || 'Registration failed')
  }
  return await resp.json()
}

export async function loginUser(user_id: string, password: string) {
  const formData = new URLSearchParams()
  formData.append('username', user_id)
  formData.append('password', password)

  const resp = await fetch(`${API_BASE_URL}/auth/Text-to-Masterpiece/token`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData
  })
  if (!resp.ok) {
    throw new Error((await responseDetail(resp)) || 'Login failed')
  }
  return await resp.json()
}

export const getCurrentUser = async () => {
  const res = await fetch(`${API_BASE_URL}/auth/Text-to-Masterpiece/users/me`, { credentials: 'include' })
  if (!res.ok) throw new Error((await responseDetail(res)) || 'Failed to get user')
  return res.json()
}

export function startGuestSession(): Promise<void> {
  if (!guestSessionRequest) {
    guestSessionRequest = (async () => {
      const resp = await fetch(`${API_BASE_URL}/Text-to-Masterpiece`, { credentials: 'include' })
      if (!resp.ok) throw new Error((await responseDetail(resp)) || `Guest session failed (HTTP ${resp.status})`)
    })().finally(() => {
      // Do not cache forever: cookies may expire or be cleared between visits.
      guestSessionRequest = undefined
    })
  }
  return guestSessionRequest
}
