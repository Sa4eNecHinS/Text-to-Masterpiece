import { ChatInput } from '@/components/chat/ChatInput';

interface WelcomeScreenProps {
  inputValue: string;
  onInputChange: (val: string) => void;
  onSend: () => void;
  loading: boolean;
}

export const WelcomeScreen = ({ inputValue, onInputChange, onSend, loading }: WelcomeScreenProps) => {
  return (
    <div className="welcome-container">
      <h1 className="welcome-title">Create a masterpiece.</h1>
      
      <div style={{ width: '100%', maxWidth: '600px', padding: '0 20px' }}>
        <ChatInput 
          value={inputValue}
          onChange={onInputChange}
          onSend={onSend}
          loading={loading}
          placeholder="Describe your thoughts..."
        />
      </div>
    </div>
  );
};
