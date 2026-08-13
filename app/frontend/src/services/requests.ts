export type GenerateResponse = { image_url: string }

export async function generateImage(prompt: string): Promise<string> {
  const resp = await fetch('http://localhost:8000/Text-to-Masterpiece/generate', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt })
  })

  const data: GenerateResponse = await resp.json()
  return data.image_url
}

export type RegisterRequest = {
  user_id: string
  email: string
  password: string
}

/*
 *сделай сайт с таким же стилем, слева вместо flow shader напиши: "text to\nmasterpiece", т.е masterpiece должен быть на новой строке (без символа \n). справа вместо текста хочу оставить только одну кнопку, которая будет ввести на сайт по определенному эндпоинту. Пиши используя: ts, tsx. Нужна строгая типизация, поэтому typescript
 * */


// регистрация 
export async function registerUser(data: RegisterRequest) {
  const resp = await fetch(
    'http://localhost:8000/auth/Text-to-Masterpiece/registrate',
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }
  )

  if (!resp.ok) {
    throw new Error('Registration failed')
  }

  return await resp.json()
}


export async function loginUser(user_id: string, password: string) {
  // авторизация 
  const formData = new URLSearchParams()
  formData.append('username', user_id)
  formData.append('password', password)

  const resp = await fetch(
    'http://localhost:8000/auth/Text-to-Masterpiece/token',
    {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: formData
    }
  )

  if (!resp.ok) {
    throw new Error('Login failed')
  }

  return await resp.json()
}


export const getCurrentUser = async () => {
  const res = await fetch('/auth/Text-to-Masterpiece/token', { credentials: 'include' })
  if (!res.ok) throw new Error("Failed to get user")
  return res.json()
}
