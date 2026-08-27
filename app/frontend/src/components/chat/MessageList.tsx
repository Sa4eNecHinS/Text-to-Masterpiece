import { useEffect, useRef } from 'react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  image?: string;
}

interface MessageListProps {
  messages: Message[];
  loading: boolean;
}

export const MessageList = ({ messages, loading }: MessageListProps) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  return (
    <div style={{ 
      flex: 1, 
      overflowY: 'auto', 
      padding: '20px', 
      display: 'flex', 
      flexDirection: 'column', 
      gap: '24px', 
      maxWidth: '800px', 
      margin: '0 auto', 
      width: '100%' 
    }}>
      {messages.map((msg, idx) => (
        <div 
          key={idx} 
          style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start' 
          }}
        >
          {/* Текстовый блок */}
          {msg.content && (
            <div style={{
              backgroundColor: msg.role === 'user' ? 'var(--input-bg)' : 'transparent',
              padding: msg.role === 'user' ? '12px 16px' : '0',
              borderRadius: '18px',
              maxWidth: '85%',
              lineHeight: 1.5,
              border: msg.role === 'user' ? '1px solid var(--border)' : 'none',
              color: 'var(--text)',
              marginBottom: msg.image ? '12px' : '0' // Отступ снизу, если есть картинка
            }}>
              {msg.content}
            </div>
          )}

          {/* Блок с картинкой (теперь он ОТДЕЛЬНО от текста) */}
          {msg.image && (
            <img 
              src={msg.image} 
              alt="Generated" 
              style={{ 
                borderRadius: '12px', 
                maxWidth: '100%', 
                width: '512px', // Фиксируем красивый размер для заглушки/картинки
                maxHeight: '512px',
                objectFit: 'cover',
                border: '1px solid var(--border)',
                display: 'block', // <--- ЭТА СТРОКА ЛЕЧИТ БАГ С ПОЗИЦИЕЙ
                boxShadow: '0 4px 20px rgba(0,0,0,0.5)' // Добавим тень для красоты
              }} 
            />
          )}
        </div>
      ))}
      
      {loading && (
        <div style={{ alignSelf: 'flex-start', color: 'var(--muted)', fontStyle: 'italic', padding: '12px 16px' }}>
          Generating masterpiece...
        </div>
      )}
      
      <div ref={bottomRef} />
    </div>
  );
};
