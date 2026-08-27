import React from 'react';
import background from "@/assets/178b.png";

interface AppLayoutProps {
  children: React.ReactNode;
  onToggleTheme: () => void;
}

export const AppLayout = ({ children, theme, onToggleTheme }: AppLayoutProps) => {
  return (
    <>
      <div 
        className="cinematic-bg" 
        style={{ backgroundImage: `url(${background})` }} 
      />
      
      <div className="chat-shell">
        <aside className="chat-sidebar glass">
          <div className="sidebar-icon active">💬</div>
        </aside>
        
        <main className="chat-main">
          <header className="chat-header">
            <div style={{ flex: 1 }}></div>
          </header>
          
          {children}
        </main>
      </div>
    </>
  );
};
