import type { ChatSummary } from '@/services/requests'

export interface ChatHistoryProps {
  entries: ChatSummary[]
  selectedId: string | null
  loading: boolean
  error: string
  hasMore: boolean
  disabled: boolean
  onSelect: (entry: ChatSummary) => void
  onLoadMore: () => void
  onRetry: () => void
}

export const ChatHistory = ({ entries, selectedId, loading, error, hasMore, disabled, onSelect, onLoadMore, onRetry }: ChatHistoryProps) => (
  <nav className="chat-history visible" aria-label="Chats" aria-busy={loading}>
    <div className="chat-history-title">History</div>
    <div className="chat-history-list">
      {entries.map(entry => (
        <button key={entry.id} className={`chat-history-item ${selectedId === entry.id ? 'active' : ''}`}
          title={entry.title} aria-current={selectedId === entry.id ? 'true' : undefined}
          disabled={disabled} onClick={() => onSelect(entry)}>
          {entry.title.length > 80 ? `${entry.title.slice(0, 80)}…` : entry.title}
          <small className="generation-model">{new Date(entry.updated_at).toLocaleDateString()}</small>
        </button>
      ))}
      {loading && <p className="chat-history-status" role="status">Loading history…</p>}
      {!loading && !error && !entries.length && <p className="chat-history-status">No creations yet.</p>}
      {error && <div className="chat-history-status" role="alert">
        <p>{error}</p>
        <button className="chat-history-item" disabled={loading} onClick={onRetry}>Try again</button>
      </div>}
      {!error && hasMore && <button className="chat-history-item" disabled={loading} onClick={onLoadMore}>Load more</button>}
    </div>
  </nav>
)
