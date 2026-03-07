import { useState, useEffect } from 'react'
import ImageViewer from './ImageViewer'
import InputBar from './InputBar'

export default function ChatLayout() {
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [dark, setDark] = useState(false)

  // Загрузка темы
  useEffect(() => {
    const saved = localStorage.getItem('dark') === '1'
    setDark(saved)
    document.documentElement.classList.toggle('dark', saved)
  }, [])

  // Создание куки
   useEffect(() => {
    fetch('http://localhost:8000/Text-to-Masterpiece', {
      method: 'GET',
      credentials: 'include',
    }).catch(() => {
      // намеренно игнорируем — cookie важнее ответа
    })
  }, [])

  const toggleTheme = () => {
    const next = !dark
    setDark(next)
    document.documentElement.classList.toggle('dark', next)
    localStorage.setItem('dark', next ? '1' : '0')
  }

  return (
    <div className="app-root">
      <header className="topbar">
        <button
          className="menu-btn"
          onClick={() => setDrawerOpen(prev => !prev)}
        >
          ☰
        </button>

        <div className="title">Text → Image</div>

        <button
          className={`theme-toggle ${dark ? 'dark' : ''}`}
          onClick={toggleTheme}
        >
          <span className="icon">{dark ? '☾' : '☀'}</span>
        </button>
      </header>

      {drawerOpen && (
        <>
          <div
            className="drawer-backdrop"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="drawer">
            <h2>History coming soon</h2>
          </aside>
        </>
      )}

      <main className="chat-area">
        <ImageViewer imageUrl={imageUrl} />
      </main>

      <InputBar onGenerated={(url) => setImageUrl(url)} />
    </div>
  )
}
