import { useEffect, useState, type ReactNode } from 'react'
import { initializeSession, rememberSession, resetSession, logoutUser, loginUser, registerUser, type User } from '@/services/requests'
import { AuthContext, type AuthMode } from './authContext'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [sessionError, setSessionError] = useState('')

  useEffect(() => {
    let active = true
    initializeSession().then(user => {
      if (active) setUser(user)
    }).catch(error => {
      if (active) setSessionError(error instanceof Error ? error.message : 'Unable to restore your session.')
    })
    return () => { active = false }
  }, [])

  const authenticate = async (mode: AuthMode, email: string, password: string): Promise<void> => {
    await initializeSession().catch(() => {})
    const result = mode === 'signup'
      ? await registerUser({ email, password })
      : await loginUser(email, password)
    // The response reflects the cookie-backed session; no tokens in browser storage.
    setUser(result.user)
    setSessionError('')
    rememberSession(result.user)
  }

  const logout = async (): Promise<void> => {
    await logoutUser()
    resetSession()
    setUser(null)
    setSessionError('')
    // Start a fresh guest session; subsequent authentication waits for it.
    void initializeSession().catch(error => {
      setSessionError(error instanceof Error ? error.message : 'Unable to start a guest session.')
    })
  }

  return <AuthContext.Provider value={{ user, sessionError, authenticate, logout }}>{children}</AuthContext.Provider>
}
