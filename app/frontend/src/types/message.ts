export type Message = {
  role: 'user' | 'assistant'
  content: string
  image?: string
  modelName?: string | null
}
