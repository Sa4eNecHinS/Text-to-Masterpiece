import { useState, useEffect } from "react";
import { generateImage } from "@/services/requests";
import { AppLayout } from "@/components/layout/AppLayout";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageList } from "@/components/chat/MessageList";

export default function GeneratePage() {
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [theme, setTheme] = useState<'light' | 'dark'>('dark');

  const isChatMode = messages.length > 0;

  useEffect(() => {
    fetch("http://localhost:8000/Text-to-Masterpiece", { credentials: "include" }).catch(console.error);
  }, []);

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
      document.documentElement.classList.remove('light');
    } else {
      document.documentElement.classList.add('light');
      document.documentElement.classList.remove('dark');
    }
  }, [theme]);

  const toggleTheme = () => setTheme(prev => prev === 'dark' ? 'light' : 'dark');

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    
    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    const currentPrompt = input;
    setInput(""); 
    setLoading(true);

    try {
      const imageUrl = await generateImage(currentPrompt);
      setMessages(prev => [...prev, { role: 'assistant', content: 'Result:', image: imageUrl }]);
    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error generating image.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppLayout theme={theme} onToggleTheme={toggleTheme}>
      
      {/* КОНТЕЙНЕР ДЛЯ ЦЕНТРИРОВАНИЯ (Welcome Screen) */}
      {/* Теперь он исчезает только после отправки (когда появится сообщение) */}
      <div className="hero-center-wrapper">
        <div className={`hero-glass-window ${isChatMode ? 'hidden' : ''}`}>
          <h1 className="hero-title">Create your masterpiece</h1>
          
          {/* Инпут внутри центрального окна. 
              Мы рендерим его всегда, пока !isChatMode, чтобы не терять фокус при вводе */}
          {!isChatMode && (
            <div className="input-transition-wrapper centered">
              <ChatInput 
                value={input} 
                onChange={setInput} 
                onSend={handleSend} 
                loading={loading}
                placeholder="Describe your vision..."
                isGlass={true} 
              />
            </div>
          )}
        </div>
      </div>

      {/* СПИСОК СООБЩЕНИЙ (появляется в режиме чата) */}
      {isChatMode && (
        <div style={{ flex: 1, overflowY: 'auto', paddingBottom: '120px', paddingTop: '20px' }}>
           <MessageList messages={messages} loading={loading} />
        </div>
      )}

      {/* НИЖНИЙ ИНПУТ (появляется в режиме чата) */}
      {isChatMode && (
        <div className="input-transition-wrapper bottom">
          <ChatInput 
            value={input} 
            onChange={setInput} 
            onSend={handleSend} 
            loading={loading}
            placeholder="Continue..."
            isGlass={true}
          />
        </div>
      )}

    </AppLayout>
  );
}
