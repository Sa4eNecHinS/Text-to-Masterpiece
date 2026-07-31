import { useState } from "react"

type Props = {
  mode: "signin" | "signup"
  onClose: () => void
  onSubmit: (email: string, password: string) => void
}

export default function AuthModal({ mode, onClose, onSubmit }: Props) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState("")
  const [successMessage, setSuccessMessage] = useState("")

  const isSignup = mode === "signup"

  const handleSubmit = async () => {
    if (isSignup && password !== confirmPassword) {
      setError("Пароли не совпадают")
      return
    }
    if (!email || !password) {
      setError("Заполните все поля")
      return
    }

    try {
      await onSubmit(email, password)
      setError("")
      setSuccessMessage(
        isSignup ? "Регистрация успешна, вы в системе" : "Вход выполнен успешно"
      )
    } catch {
      setError("Ошибка авторизации")
      setSuccessMessage("")
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{isSignup ? "Регистрация" : "Авторизация"}</h2>

        {successMessage && <div className="success-message">{successMessage}</div>}
        {error && <div className="error-message">{error}</div>}

        <input type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} />
        <input type="password" placeholder="Пароль" value={password} onChange={e => setPassword(e.target.value)} />
        {isSignup && (
          <input type="password" placeholder="Повторите пароль" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} />
        )}

        <button onClick={handleSubmit}>
          {isSignup ? "Зарегистрироваться" : "Войти"}
        </button>
      </div>
    </div>
  )
}
