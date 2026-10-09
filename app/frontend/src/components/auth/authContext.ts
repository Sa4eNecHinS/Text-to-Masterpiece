import { createContext, useContext } from 'react'
import type { User } from '@/services/requests'

export type AuthMode = 'signin' | 'signup'
export const AuthContext = createContext<{
  user: User | null
  sessionError: string
  logout: () => Promise<void>
  authenticate: (mode: AuthMode, email: string, password: string) => Promise<void>
} | null>(null)

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('AuthProvider is missing')
  return context
}
