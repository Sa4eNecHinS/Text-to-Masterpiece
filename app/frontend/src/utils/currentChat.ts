import type { Message } from '@/types/message'

const KEY = 'ttm.current-chat.v1'
export type CurrentChat = {
  owner: number | null
  messages: Message[]
  input: string
  selectedId: number | null
}

// Tab-scoped: persists across reloads without mixing independent browser tabs.
export function readCurrentChat(owner: number | null): CurrentChat | null {
  try {
    const data = JSON.parse(sessionStorage.getItem(KEY) || 'null')
    if (!data || data.owner !== owner || typeof data.input !== 'string'
      || !(data.selectedId === null || typeof data.selectedId === 'number') || !Array.isArray(data.messages)
      || !data.messages.every((message: Message) => message && (message.role === 'user' || message.role === 'assistant')
        && typeof message.content === 'string' && (message.image === undefined || typeof message.image === 'string'))) return null
    return data
  } catch { return null }
}

export function saveCurrentChat(chat: CurrentChat): boolean {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(chat))
    return true
  } catch { return false }
}
