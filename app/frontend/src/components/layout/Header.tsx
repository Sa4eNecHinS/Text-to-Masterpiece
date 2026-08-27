import { useTheme } from '@/hooks/useTheme'; 

export const Header = ({ title }: { title: string }) => {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="chat-header">
      <div className="model-selector">
        {title} <span className="chevron">⌄</span>
      </div>
      <button className="theme-toggle" onClick={toggleTheme}>
        {theme === 'dark' ? '☀️' : '🌙'}
      </button>
    </header>
  );
};
