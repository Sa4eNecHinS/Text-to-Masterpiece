import React from 'react';

interface ChatInputProps {
  value: string;
  onChange: (val: string) => void;
  onSend: () => void;
  loading?: boolean;
  placeholder?: string;
  isGlass?: boolean; 
}

export const ChatInput = ({ 
  value, onChange, onSend, loading, placeholder = "Describe your thoughts...", isGlass = false 
}: ChatInputProps) => {
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className={`input-pill ${isGlass ? 'glass' : ''}`}>
      <button className="action-btn" style={{ marginRight: 8, background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: '20px' }}>
        +
      </button>
      
      <textarea
        className="prompt-input"
        rows={1}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={loading}
      />
      
      <button 
        className="send-btn" 
        onClick={onSend} 
        disabled={!value.trim() || loading}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 19V5M5 12L12 5L19 12" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
    </div>
  );
};
