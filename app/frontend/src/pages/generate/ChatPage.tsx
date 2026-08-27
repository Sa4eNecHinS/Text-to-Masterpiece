import { useState, useEffect, useRef } from "react";
import { generateImage } from "@/services/requests";
import { AppLayout } from "@/components/layout/AppLayout";
import { MessageList } from "@/components/chat/MessageList";
import { ChatInput } from "@/components/chat/ChatInput";
import { Header } from "@/components/layout/Header";

export default function ChatPage() {
  const [messages, setMessages] = useState<{role: string, content: string, image?: string}[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Инициализация куки (оставляем вашу логику)
  useEffect(() => {
    fetch("http://localhost:8000/Text-to-Masterpiece", { credentials: "include" })
      .catch(console.error);
  }, []);

  // Авто-скролл вниз
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      // Здесь вызов вашего API
      const imageUrl = await generateImage(input); 
      
      const aiMsg = { role: 'assistant', content: 'Generated image:', image: imageUrl };
      setMessages(prev => [...prev, aiMsg]);
    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error generating image.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppLayout>
      <Header title="Qwen3.8-Max" />
      
      {/* Область сообщений или Welcome экран */}
      <div className="chat-scroll-area" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="welcome-screen">
            <h1 className="welcome-title">How can I help you ?</h1>
            {/* Инпут дублируется в центре для красоты, как у Qwen */}
            <div className="centered-input-wrapper">
               <ChatInput 
                  value={input} 
                  onChange={setInput} 
                  onSend={handleSend} 
                  loading={loading}
                  centered={true} 
                />
            </div>
          </div>
        ) : (
          <MessageList messages={messages} />
        )}
      </div>

      {/* Нижний инпут (появляется только когда есть сообщения) */}
      {messages.length > 0 && (
        <div className="bottom-input-wrapper">
          <ChatInput 
            value={input} 
            onChange={setInput} 
            onSend={handleSend} 
            loading={loading}
            centered={false}
          />
        </div>
      )}
    </AppLayout>
  );
}
