import { useState } from "react"
import ChatLayout from "@/components/ChatLayout"
import LandingPage from "@/components/LandingPage"

export default function App() {
  const [showLanding, setShowLanding] = useState(true)

  return showLanding ? (
    <LandingPage onEnter={() => setShowLanding(false)} />
  ) : (
    <ChatLayout />
  )
}
