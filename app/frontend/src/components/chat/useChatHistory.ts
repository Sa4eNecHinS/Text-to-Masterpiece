import { useEffect, useRef, useState } from 'react'
import { useAuth } from '@/components/auth/authContext'
import { getChatHistory, type ChatHistoryEntry } from '@/services/requests'

export function useChatHistory() {
  const { user } = useAuth()
  const [entries, setEntries] = useState<ChatHistoryEntry[]>([])
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
      setEntries([])
      offset.current = 0
      try {
        const rows = await getChatHistory(0, controller.signal)
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
  }, [user?.id, revision])

  const loadMore = async () => {
    if (busy.current || !hasMore) return
    busy.current = true
    const controller = new AbortController()
    request.current?.abort()
    request.current = controller
    setLoading(true)
    setError('')
    try {
      const rows = await getChatHistory(offset.current, controller.signal)
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
