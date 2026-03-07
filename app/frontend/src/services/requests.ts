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


