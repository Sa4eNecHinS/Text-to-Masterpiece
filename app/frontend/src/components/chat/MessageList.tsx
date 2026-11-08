import { useEffect, useRef } from 'react';
import type { Message } from '@/types/message';
import { PrivateImage } from '@/components/chat/PrivateImage';

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
          {msg.content && (
            <div style={{
              backgroundColor: msg.role === 'user' ? 'var(--input-bg)' : 'transparent',
              padding: msg.role === 'user' ? '12px 16px' : '0',
              borderRadius: '18px',
              maxWidth: '85%',
              lineHeight: 1.5,
              border: msg.role === 'user' ? '1px solid var(--border)' : 'none',
              color: 'var(--text)',
              marginBottom: msg.generationId ? '12px' : '0'
            }}>
              {msg.content}
            </div>
          )}

          {msg.generationId && <small className="generation-model">{msg.modelName || 'Модель неизвестна'}</small>}
          {msg.generationId && <PrivateImage generationId={msg.generationId} />}
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
