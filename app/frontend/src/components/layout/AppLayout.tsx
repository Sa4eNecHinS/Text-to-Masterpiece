import React, { useRef, useState } from "react";
import {
  PanelLeftOpen,
  PanelLeftClose,
  CircleUserRound,
  Plus,
} from "lucide-react";

import background from "@/assets/178b.png";
import { ChatHistory, type ChatHistoryProps } from "@/components/chat/ChatHistory";
import AuthModal from "@/components/AuthModal";
import { AccountMenu } from "@/components/auth/AccountMenu";
import { useAuth } from "@/components/auth/authContext";

interface AppLayoutProps {
  children: React.ReactNode;
  history: ChatHistoryProps;
  onNewChat: () => void;
  onSignedOut: () => void;
}

export const AppLayout = ({ children, history, onNewChat, onSignedOut }: AppLayoutProps) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const { user, sessionError, authenticate, logout } = useAuth();
  const accountFooter = useRef<HTMLDivElement>(null);
  const focusAccountButton = () => requestAnimationFrame(() => {
    accountFooter.current?.querySelector<HTMLButtonElement>('.sidebar-login')?.focus();
  });

  const handleLogout = async (switchAccount: boolean): Promise<void> => {
    await logout();
    onSignedOut();
    if (switchAccount) setAuthOpen(true);
    else focusAccountButton();
  };

  return (
    <>
      <div
        className="cinematic-bg"
        style={{ backgroundImage: `url(${background})` }}
      />

      <div className="chat-shell">
        <aside
          className={`chat-sidebar ${
            sidebarOpen ? "expanded glass" : "collapsed"
          }`}
        >
          {sidebarOpen && (
            <>
              <div className="sidebar-header">
                <button
                  className="sidebar-icon"
                  onClick={() => setSidebarOpen(false)}
                  aria-label="Close sidebar"
                >
                  <PanelLeftClose size={18}/>
                </button>
              </div>

              <button className="sidebar-new-chat" onClick={onNewChat} disabled={history.disabled}>
                <Plus size={18} /> New chat
              </button>
              <ChatHistory {...history} />

              <div className="sidebar-footer" ref={accountFooter}>
                {sessionError && <p className="sidebar-session-error" role="status">{sessionError}</p>}
                {user ? <AccountMenu user={user} disabled={history.disabled} onLogout={handleLogout} /> : (
                  <button className="sidebar-login" onClick={() => setAuthOpen(true)}
                    aria-haspopup="dialog" aria-label="Log In">
                    <CircleUserRound size={19} />
                    <span className="sidebar-login-text">Log In</span>
                  </button>
                )}
              </div>
            </>
          )}
        </aside>

        <main className="chat-main">
          {!sidebarOpen && (
            <button
              className="sidebar-open-button"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open sidebar"
            >
              <PanelLeftOpen size={19} strokeWidth={1.8}/>
            </button>
          )}

          {children}
        </main>
      </div>
      {authOpen && <AuthModal onClose={() => {
        setAuthOpen(false);
        focusAccountButton();
      }} onSubmit={authenticate} />}
    </>
  );
};
