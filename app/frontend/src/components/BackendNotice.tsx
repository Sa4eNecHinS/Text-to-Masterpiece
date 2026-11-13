import { retryBackendReadiness } from '@/services/requests'
import { useBackendReadiness } from './useBackendReadiness'

export function BackendNotice() {
  const { status } = useBackendReadiness()
  if (status !== 'checking' && status !== 'starting' && status !== 'unavailable') return null
  return <aside className="backend-notice" role="status" aria-live="polite">
    {status !== 'unavailable' ? <>
      <strong>Starting server…</strong>
      <span>The server is waking up. You can continue preparing your prompt.</span>
    </> : <>
      <strong>Server temporarily unavailable</strong>
      <button type="button" onClick={() => { void retryBackendReadiness().catch(() => {}) }}>Try again</button>
    </>}
  </aside>
}
