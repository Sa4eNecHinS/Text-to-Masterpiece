import { useEffect, useRef } from 'react'
import type { KeyboardEvent } from 'react'
import type { ImageModel } from '@/services/requests'

export interface ModelSelectProps {
  models: ImageModel[]
  value: string
  loading: boolean
  error: string
  disabled: boolean
  onChange: (modelId: string) => void
  onRetry: () => void
}

export function ModelSelect({ models, value, loading, error, disabled, onChange, onRetry }: ModelSelectProps) {
  const menu = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const target = menu.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]:not(:disabled)')
      ?? menu.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')
    target?.focus()
  }, [loading, error, models])

  const navigate = (event: KeyboardEvent) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const buttons = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
      : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length
    buttons[next]?.focus()
  }

  return (
    <div className="model-select" ref={menu} role="menu" aria-label="Model" aria-busy={loading}
      tabIndex={-1} onKeyDown={navigate}>
      <div className="model-menu-heading">Model <span>/model ⇥</span></div>
      {loading && <p role="status">Loading models…</p>}
      {!loading && error && <p role="alert">{error} <button type="button" role="menuitem" onClick={onRetry}>Try again</button></p>}
      {!loading && !error && !models.length && <p role="status">No models available. <button type="button" role="menuitem" onClick={onRetry}>Reload</button></p>}
      {!loading && !error && models.map(model => (
        <button type="button" role="menuitemradio" aria-checked={value === model.model_id}
          key={model.model_id} disabled={disabled} onClick={() => onChange(model.model_id)}>
          <span>{model.name}</span><span aria-hidden="true">{value === model.model_id ? '✓' : ''}</span>
        </button>
      ))}
    </div>
  )
}
