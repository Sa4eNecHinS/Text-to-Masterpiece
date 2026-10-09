import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { Eye, EyeOff, LoaderCircle, X } from 'lucide-react'
import { AuthError, type AuthField } from '@/services/requests'
import type { AuthMode } from './auth/authContext'

type Props = {
  onClose: () => void
  onSubmit: (mode: AuthMode, email: string, password: string) => Promise<void>
}

export default function AuthModal({ onClose, onSubmit }: Props) {
  const [mode, setMode] = useState<AuthMode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [visible, setVisible] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<AuthField, string>>>({})
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const pending = useRef(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const emailInput = useRef<HTMLInputElement>(null)
  const mounted = useRef(false)
  const id = useId()
  const signup = mode === 'signup'

  useEffect(() => {
    mounted.current = true
    const opener = document.activeElement as HTMLElement | null
    const element = dialog.current!
    const overflow = document.body.style.overflow
    element.showModal() // Native modal makes the background inert and traps focus.
    emailInput.current?.focus()
    document.body.style.overflow = 'hidden'
    return () => {
      mounted.current = false
      element.close()
      document.body.style.overflow = overflow
      opener?.focus()
    }
  }, [])

  const switchMode = () => {
    setMode(signup ? 'signin' : 'signup')
    setErrors({})
    setError('')
    setConfirmPassword('')
    setPassword('')
    setVisible(false)
    emailInput.current?.focus()
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (pending.current) return
    const fields: Partial<Record<AuthField, string>> = {}
    if (!email.trim()) fields.email = 'Enter your email.'
    else if (!emailInput.current?.validity.valid) fields.email = 'Enter a valid email.'
    if (!password) fields.password = 'Enter your password.'
    if (signup && !confirmPassword) fields.confirmPassword = 'Confirm your password.'
    else if (signup && password !== confirmPassword) fields.confirmPassword = 'Passwords do not match.'
    setErrors(fields)
    setError('')
    const first = Object.keys(fields)[0]
    if (first) {
      document.getElementById(`${id}-${first}`)?.focus()
      return
    }
    pending.current = true
    setLoading(true)
    try {
      await onSubmit(mode, email.trim(), password)
      if (mounted.current) onClose()
    } catch (err) {
      if (mounted.current) {
        setError(err instanceof Error ? err.message : 'Unable to authenticate. Please try again.')
        if (err instanceof AuthError) setErrors(err.fields)
      }
    } finally {
      pending.current = false
      if (mounted.current) setLoading(false)
    }
  }

  return (
    <dialog ref={dialog} className="auth-dialog" aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`}
      onCancel={event => { event.preventDefault(); onClose() }}
      onKeyDown={event => {
        if (event.key === 'Escape') {
          event.preventDefault()
          onClose()
          return
        }
        if (event.key !== 'Tab') return
        const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled)'))
        const first = controls[0]
        const last = controls.at(-1)
        if (event.shiftKey && (document.activeElement === first || document.activeElement === event.currentTarget)) {
          event.preventDefault()
          last?.focus()
        } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === event.currentTarget)) {
          event.preventDefault()
          first?.focus()
        }
      }}
      onClick={event => { if (event.target === event.currentTarget) onClose() }}>
      <div className="auth-panel">
        <button type="button" className="auth-close" aria-label="Close authentication dialog" onClick={onClose}><X size={20} /></button>
        <h2 id={`${id}-title`}>{signup ? 'Create an account' : 'Welcome back'}</h2>
        <p id={`${id}-description`} className="auth-description">{signup ? 'Save your ideas and masterpieces.' : 'Log in to continue creating.'}</p>
        <form className="auth-form" noValidate onSubmit={handleSubmit} aria-busy={loading}>
          <div className="auth-field">
            <label htmlFor={`${id}-email`}>Email</label>
            <input ref={emailInput} id={`${id}-email`} type="email" autoComplete="email" required value={email} disabled={loading}
              onChange={event => setEmail(event.target.value)} aria-invalid={!!errors.email} aria-describedby={errors.email ? `${id}-email-error` : undefined} />
            {errors.email && <span id={`${id}-email-error`} className="auth-error">{errors.email}</span>}
          </div>
          <div className="auth-field">
            <label htmlFor={`${id}-password`}>Password</label>
            <div className="auth-password">
              <input id={`${id}-password`} type={visible ? 'text' : 'password'} autoComplete={signup ? 'new-password' : 'current-password'} required
                value={password} disabled={loading} onChange={event => setPassword(event.target.value)}
                aria-invalid={!!errors.password} aria-describedby={errors.password ? `${id}-password-error` : undefined} />
              <button type="button" className="auth-visibility" aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible} onClick={() => setVisible(!visible)}>
                {visible ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {errors.password && <span id={`${id}-password-error`} className="auth-error">{errors.password}</span>}
          </div>
          {signup && <div className="auth-field">
            <label htmlFor={`${id}-confirmPassword`}>Confirm password</label>
            <input id={`${id}-confirmPassword`} type={visible ? 'text' : 'password'} autoComplete="new-password" required value={confirmPassword} disabled={loading}
              onChange={event => setConfirmPassword(event.target.value)} aria-invalid={!!errors.confirmPassword}
              aria-describedby={errors.confirmPassword ? `${id}-confirm-error` : undefined} />
            {errors.confirmPassword && <span id={`${id}-confirm-error`} className="auth-error">{errors.confirmPassword}</span>}
          </div>}
          {error && <p className="auth-error auth-form-error" role="alert">{error}</p>}
          <button className="auth-submit" type="submit" disabled={loading}>
            {loading && <LoaderCircle size={17} className="auth-spinner" />}
            {loading ? 'Please wait…' : signup ? 'Create account' : 'Log In'}
          </button>
          <button type="button" className="auth-switch" disabled={loading} onClick={switchMode}>
            {signup ? 'Already have an account? Log in' : 'Create an account'}
          </button>
        </form>
      </div>
    </dialog>
  )
}
