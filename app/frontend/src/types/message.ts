export type Message = {
  role: 'user' | 'assistant'
  content: string
  generationId?: number
  modelName?: string | null
}
