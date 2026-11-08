import { useEffect, useRef, useState } from 'react'
import { useAuth } from '@/components/auth/authContext'
import { getGenerationImage } from '@/services/requests'

type ImageResult = { id: number; owner: number | null; attempt: number; url?: string; error?: string }

export function PrivateImage({ generationId }: { generationId: number }) {
  const { user } = useAuth()
  const owner = user?.id ?? null
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<ImageResult | null>(null)
  const liveUrl = useRef<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | undefined
    const release = () => {
      if (objectUrl && liveUrl.current === objectUrl) {
        URL.revokeObjectURL(objectUrl)
        liveUrl.current = null
      }
    }
    const load = async () => {
      try {
        const blob = await getGenerationImage(generationId, controller.signal)
        if (controller.signal.aborted) return
        objectUrl = URL.createObjectURL(blob)
        liveUrl.current = objectUrl
        setResult({ id: generationId, owner, attempt, url: objectUrl })
      } catch (error) {
        if (!controller.signal.aborted) setResult({ id: generationId, owner, attempt,
          error: error instanceof Error ? error.message : 'Unable to load image.' })
      }
    }
    void load()
    return () => {
      controller.abort()
      release()
    }
  }, [generationId, owner, attempt])

  // Hide the previous image immediately on a prop/owner change, even before
  // React runs effect cleanup. A stale fetch never creates a Blob URL.
  const current = result?.id === generationId && result.owner === owner && result.attempt === attempt ? result : null
  if (current?.error) return <div role="alert">
    <p>{current.error}</p>
    <button onClick={() => setAttempt(value => value + 1)}>Try again</button>
  </div>
  if (!current?.url) return <p role="status">Loading image…</p>
  const url = current.url
  return <img className="generated-image" src={url} alt="Generated"
    onError={() => {
      if (liveUrl.current === url) {
        URL.revokeObjectURL(url)
        liveUrl.current = null
      }
      setResult(previous => previous?.id === generationId && previous.owner === owner && previous.attempt === attempt
        ? { ...previous, error: 'Unable to display image.' } : previous)
    }}
    style={{ borderRadius: '12px', maxWidth: '100%', width: '512px', maxHeight: '512px',
      objectFit: 'cover', border: '1px solid var(--border)', display: 'block', boxShadow: '0 4px 20px rgba(0,0,0,0.5)' }} />
}
