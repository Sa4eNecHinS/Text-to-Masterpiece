import type { Message } from '@/types/message'
import type { ChatHistoryEntry } from '@/services/requests'

export function generationMessages(entries: ChatHistoryEntry[]): Message[] {
  return entries.flatMap(entry => [
    { role: 'user' as const, content: entry.prompt },
    { role: 'assistant' as const, content: 'Result:', image: entry.image_url, modelName: entry.model_name },
  ])
}

// v1 selected a generation's numeric ID, not a chat UUID. Do not restore it.
const KEY = 'ttm.current-chat.v2'
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
        && typeof message.content === 'string' && (message.image === undefined || typeof message.image === 'string')
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
