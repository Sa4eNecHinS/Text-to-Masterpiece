import { useLayoutEffect, useState, type ReactNode } from 'react'
import { initializeSession, rememberSession, resetSession, logoutUser, loginUser, registerUser, startBackendReadiness, retainBackendWakeFrame, type User } from '@/services/requests'
import { AuthContext, type AuthMode } from './authContext'
import { useBackendReadiness } from '@/components/useBackendReadiness'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [sessionError, setSessionError] = useState('')

  const backend = useBackendReadiness()
  // Enable the shared readiness gate before child pages start passive effects.
  // StrictMode replays join the same promise rather than starting another loop.
  useLayoutEffect(() => {
    let active = true
    const releaseWakeFrame = retainBackendWakeFrame()
    void startBackendReadiness().catch(() => {})
    initializeSession().then(user => {
      if (active) { setUser(user); setSessionError('') }
    }).catch(error => {
      if (active) setSessionError(error instanceof Error ? error.message : 'Unable to restore your session.')
    })
    return () => { active = false; releaseWakeFrame() }
  }, [backend.retryVersion])

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

  const visibleSessionError = ['checking', 'starting', 'unavailable'].includes(backend.status) ? '' : sessionError
  return <AuthContext.Provider value={{ user, sessionError: visibleSessionError, authenticate, logout }}>{children}</AuthContext.Provider>
}
