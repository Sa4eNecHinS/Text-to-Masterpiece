import { useState, useEffect } from "react";
import { generateImage, startGuestSession } from "@/services/requests";
import type { Message } from "@/types/message";
import { AppLayout } from "@/components/layout/AppLayout";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageList } from "@/components/chat/MessageList";

export default function GeneratePage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const isChatMode = messages.length > 0;

  useEffect(() => {
    startGuestSession().catch(console.error);
  }, []);


  const handleSend = async () => {
    if (!input.trim() || loading) return;
    
    const userMsg: Message = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    const currentPrompt = input;
    setInput(""); 
    setLoading(true);

    try {
      const imageUrl = await generateImage(currentPrompt);
      setMessages(prev => [...prev, { role: 'assistant', content: 'Result:', image: imageUrl }]);
    } catch (err) {
      console.error(err);
      const message = err instanceof Error ? err.message : 'Error generating image.';
      setMessages(prev => [...prev, { role: 'assistant', content: message }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppLayout>
      
      <div className="hero-center-wrapper">
        <div className={`hero-glass-window ${isChatMode ? 'hidden' : ''}`}>
          <h1 className="hero-title">Create your masterpiece</h1>
          
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

      {/* messages list */}
      {isChatMode && (
        <div style={{ flex: 1, overflowY: 'auto', paddingBottom: '120px', paddingTop: '20px' }}>
           <MessageList messages={messages} loading={loading} />
        </div>
      )}

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
