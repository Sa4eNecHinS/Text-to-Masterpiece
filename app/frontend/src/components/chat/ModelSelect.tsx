import { useId } from 'react'
import type { ImageModel } from '@/services/requests'

interface ModelSelectProps {
  models: ImageModel[]
  value: string
  loading: boolean
  error: string
  disabled: boolean
  onChange: (modelId: string) => void
  onRetry: () => void
}

export function ModelSelect({ models, value, loading, error, disabled, onChange, onRetry }: ModelSelectProps) {
  const id = useId()
  return (
    <div className="model-select" aria-busy={loading}>
      <label htmlFor={id}>Model</label>
      <select id={id} value={value} onChange={event => onChange(event.target.value)}
        disabled={disabled || loading || !!error || !models.length}>
        {!value && <option value="">{loading ? 'Loading models…' : 'No model selected'}</option>}
        {models.map(model => <option key={model.model_id} value={model.model_id}>{model.name}</option>)}
      </select>
      {loading && <span role="status">Loading models…</span>}
      {!loading && error && <span role="alert">{error} <button type="button" onClick={onRetry}>Try again</button></span>}
      {!loading && !error && !models.length && <span role="status">No models available. <button type="button" onClick={onRetry}>Reload</button></span>}
    </div>
  )
}
