import { useState, useEffect } from 'react'
import ImageViewer from '@/components/ImageViewer'
import InputBar from '@/components/InputBar'
import AuthModal from '@/components/AuthModal'
import { loginUser, registerUser, getCurrentUser } from '@/services/requests'
import user_profile_rick from "@/assets/user_profile_rick.png"

export default function ChatLayout() {
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [dark, setDark] = useState(false)
  const [authMode, setAuthMode] = useState<"signin" | "signup" | null>(null)
  const [currentUser, setCurrentUser] = useState<{ email: string } | null>(null)

  useEffect(() => {
    const saved = localStorage.getItem('dark') === '1'
    setDark(saved)
    document.documentElement.classList.toggle('dark', saved)
  }, [])

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const user = await getCurrentUser()
        setCurrentUser(user)
      } catch {
        setCurrentUser(null)
      }
    }
    fetchUser()
  }, [])

  const toggleTheme = () => {
    const next = !dark
    setDark(next)
    document.documentElement.classList.toggle('dark', next)
    localStorage.setItem('dark', next ? '1' : '0')
  }

  const handleAuthSubmit = async (email: string, password: string) => {
    try {
      if (authMode === "signup") {
        await registerUser({ email, password })
      } else {
        await loginUser(email, password)
      }

      const user = await getCurrentUser()
      setCurrentUser(user)
      setAuthMode(null)
    } catch {
      throw new Error("Ошибка авторизации")
    }
  }

  return (
    <div className="app-root">
      <header className="topbar">
        <button className="menu-btn" onClick={() => setDrawerOpen(prev => !prev)}>☰</button>
        <div className="title">Text → Image</div>
        <div className="topbar-right">
          {currentUser ? (
            <div className="user-icon">
              <img src={user_profile_rick} alt="User Avatar" />
            </div>
          ) : (
            <div className="auth-buttons">
              <button className="signin-btn" onClick={() => setAuthMode("signin")}>Sign In</button>
              <button className="signup-btn" onClick={() => setAuthMode("signup")}>Sign Up</button>
            </div>
          )}

          <button className={`theme-toggle ${dark ? "dark" : ""}`} onClick={toggleTheme}>
            <span className="icon">{dark ? "☾" : "☀"}</span>
          </button>
        </div>
      </header>

      {drawerOpen && (
        <>
          <div className="drawer-backdrop" onClick={() => setDrawerOpen(false)} />
          <aside className="drawer">
            <h2>History coming soon</h2>
          </aside>
        </>
      )}

      <main className="chat-area">
        <ImageViewer imageUrl={imageUrl} />
      </main>

      <InputBar onGenerated={(url) => setImageUrl(url)} />

      {authMode && (
        <AuthModal
          mode={authMode}
          onClose={() => setAuthMode(null)}
          onSubmit={handleAuthSubmit}
        />
      )}
    </div>
  )
}
