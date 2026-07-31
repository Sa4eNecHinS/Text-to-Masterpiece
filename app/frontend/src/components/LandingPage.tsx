import "@/landing.css"
import hand from "@/assets/hand_1.png"
import { useEffect, useState } from "react"

type Props = { onEnter: () => void }

export default function LandingPage({ onEnter }: Props) {
  const [handsScale, setHandsScale] = useState(1)

  useEffect(() => {
    const updateScale = () => {
      const baseWidth = 1920
      const currentWidth = window.innerWidth
      const scale = Math.max(0.5, Math.min(1, currentWidth / baseWidth))
      setHandsScale(scale)
    }

    updateScale()
    window.addEventListener('resize', updateScale)
    return () => window.removeEventListener('resize', updateScale)
  }, [])

  return (
    <div className="landing-root">
      {/* Анимированный фон с точками */}
      <div className="landing-bg">
        <div className="stars-container">
          {[...Array(50)].map((_, i) => (
            <div 
              key={i} 
              className="star" 
              style={{
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                animationDelay: `${Math.random() * 20}s`,
                animationDuration: `${15 + Math.random() * 10}s`
              }}
            />
          ))}
        </div>
      </div>

      {/* Текстовый блок */}
      <div className="landing-text">
        <div className="text-block">
          <h1>
            Create Your <br />
            <span className="masterpiece">Masterpiece</span>
          </h1>
          <hr className="divider" />
        </div>
        <div className="button-area">
          <button className="create-btn" onClick={onEnter}>
            CREATE →
          </button>
        </div>
      </div>

      {/* РУКА - масштабируется
      <div 
        className="hands-wrapper"
        style={{ transform: `scale(${handsScale})` }}
      >
        <img src={hand} alt="Hand" className="landing-hands" />
      </div>
      */}
    </div>
  )
}
