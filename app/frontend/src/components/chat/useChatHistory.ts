import { useEffect, useRef, useState } from 'react'
import { useAuth } from '@/components/auth/authContext'
import { getChats, type ChatSummary } from '@/services/requests'
import { useBackendReadiness } from '@/components/useBackendReadiness'

export function useChatHistory() {
  const { user } = useAuth()
  const backend = useBackendReadiness()
  const previousOwner = useRef(user?.id)
  const [entries, setEntries] = useState<ChatSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [hasMore, setHasMore] = useState(false)
  const [revision, setRevision] = useState(0)
  const request = useRef<AbortController | null>(null)
  const offset = useRef(0)
  const busy = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    request.current?.abort()
    request.current = controller
    busy.current = true
    const load = async () => {
      setLoading(true)
      setError('')
      if (previousOwner.current !== user?.id) {
        setEntries([])
        previousOwner.current = user?.id
      }
      offset.current = 0
      try {
        const rows = await getChats(0, controller.signal)
        if (controller.signal.aborted) return
        setEntries(rows)
        offset.current = rows.length
        setHasMore(rows.length === 50)
      } catch (error) {
        if (!controller.signal.aborted) setError(error instanceof Error ? error.message : 'Unable to load history.')
      } finally {
        if (!controller.signal.aborted) { busy.current = false; setLoading(false) }
      }
    }
    void load()
    return () => { controller.abort(); request.current?.abort() }
  }, [user?.id, revision, backend.retryVersion])

  const loadMore = async () => {
    if (busy.current || !hasMore) return
    busy.current = true
    const controller = new AbortController()
    request.current?.abort()
    request.current = controller
    setLoading(true)
    setError('')
    try {
      const rows = await getChats(offset.current, controller.signal)
      if (controller.signal.aborted) return
      setEntries(previous => [...previous, ...rows.filter(row => !previous.some(entry => entry.id === row.id))])
      offset.current += rows.length
      setHasMore(rows.length === 50)
    } catch (error) {
      if (!controller.signal.aborted) setError(error instanceof Error ? error.message : 'Unable to load history.')
    } finally {
      if (!controller.signal.aborted) { busy.current = false; setLoading(false) }
    }
  }

  return { entries, loading, error, hasMore, refresh: () => setRevision(value => value + 1), loadMore }
}
