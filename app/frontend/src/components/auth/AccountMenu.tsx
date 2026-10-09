import { useEffect, useId, useRef, useState } from 'react'
import { ChevronUp, CircleUserRound, LogOut, UsersRound } from 'lucide-react'
import type { User } from '@/services/requests'

type Props = {
  user: User
  disabled: boolean
  onLogout: (switchAccount: boolean) => Promise<void>
}

export function AccountMenu({ user, disabled, onLogout }: Props) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const popup = useRef<HTMLDivElement>(null)
  const id = useId()

  useEffect(() => {
    if (!open) return
    popup.current?.querySelector('button')?.focus()
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node) && !pending.current) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending.current) {
        event.preventDefault()
        setOpen(false)
        trigger.current?.focus()
      }
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  const handleLogout = async (switchAccount: boolean): Promise<void> => {
    if (pending.current || disabled) return
    pending.current = true
    setBusy(true)
    setError('')
    try {
      await onLogout(switchAccount)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Unable to log out. Please try again.')
    } finally {
      pending.current = false
      setBusy(false)
    }
  }

  return <div className="account-control" ref={root} onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget) && !pending.current) setOpen(false)
  }}>
    {open && <div ref={popup} id={id} className="account-popover" role="region" aria-label="Account options" aria-busy={busy}>
      <p className="account-popover-email" title={user.email}>{user.email}</p>
      <button type="button" disabled={busy || disabled} onClick={() => void handleLogout(true)}>
        <UsersRound size={16} /> {busy ? 'Please wait…' : 'Switch account'}
      </button>
      <button type="button" disabled={busy || disabled} onClick={() => void handleLogout(false)}>
        <LogOut size={16} /> Log out
      </button>
      {disabled && <p className="account-popover-note">Wait for the current request to finish.</p>}
      {error && <p className="auth-error" role="alert">{error}</p>}
    </div>}
    <button ref={trigger} type="button" className="sidebar-login" disabled={busy}
      aria-label={`Signed in as ${user.email}`} aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => { setError(''); setOpen(value => !value) }}>
      <CircleUserRound size={19} />
      <span className="sidebar-login-text">{user.email}</span>
      <ChevronUp size={15} className={`account-chevron ${open ? 'open' : ''}`} />
    </button>
  </div>
}
