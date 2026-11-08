import type { Message } from '@/types/message'
import type { ChatHistoryEntry } from '@/services/requests'

export function generationMessages(entries: ChatHistoryEntry[]): Message[] {
  return entries.flatMap(entry => [
    { role: 'user' as const, content: entry.prompt },
    { role: 'assistant' as const, content: 'Result:', generationId: entry.id, modelName: entry.model_name },
  ])
}

// Old versions stored image URLs. Persist identifiers only, never Blob URLs.
const KEY = 'ttm.current-chat.v3'
export type CurrentChat = {
  owner: number | null
  messages: Message[]
  input: string
  selectedId: string | null
}

// Tab-scoped: persists across reloads without mixing independent browser tabs.
export function readCurrentChat(owner: number | null): CurrentChat | null {
  try {
    const data = JSON.parse(sessionStorage.getItem(KEY) || 'null')
    if (!data || data.owner !== owner || typeof data.input !== 'string'
      || !(data.selectedId === null || (typeof data.selectedId === 'string' && data.selectedId.trim())) || !Array.isArray(data.messages)
      || !data.messages.every((message: Message) => message && (message.role === 'user' || message.role === 'assistant')
        && typeof message.content === 'string' && (message.generationId === undefined || (typeof message.generationId === 'number' && Number.isSafeInteger(message.generationId) && message.generationId > 0))
        && (message.modelName == null || typeof message.modelName === 'string'))) return null
    return data
  } catch { return null }
}

export function saveCurrentChat(chat: CurrentChat): boolean {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(chat))
    return true
  } catch { return false }
}
