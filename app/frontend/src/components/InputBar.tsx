import { useState, useRef, useEffect } from 'react'
import { generateImage } from '../services/requests'

export default function InputBar({
  onGenerated,
}: {
  onGenerated: (url: string, prompt: string) => void
}) {
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = '22px'
    el.style.height = Math.min(el.scrollHeight, 100) + 'px'
  }, [prompt])

  const submit = async () => {
    if (!prompt.trim() || loading) return
    setLoading(true)
    try {
      const url = await generateImage(prompt)
      onGenerated(url, prompt)
      setPrompt('')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="input-wrapper">
      <div className="input-pill">
        <textarea
          ref={textareaRef}
          className="prompt-input"
          placeholder="Enter text to get a masterpiece..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={1}
        />

        <button className="send-btn" onClick={submit} disabled={loading}>
          <svg viewBox="0 0 24 24" className="send-icon">
            <path
              d="M12 4 L12 18 M6 10 L12 4 L18 10"
              fill="none"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
    </div>
  )
}
