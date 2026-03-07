// ================= src/components/Toast.tsx =================
import { useEffect } from 'react'

export default function Toast({
  message,
  onClose
}: {
  message: string | null
  onClose: () => void
}) {
  useEffect(() => {
    if (!message) return
    const t = setTimeout(onClose, 3000)
    return () => clearTimeout(t)
  }, [message, onClose])

  if (!message) return null
  return <div className="toast">{message}</div>
}
