import React, { useState } from "react";
import {
  PanelLeftOpen,
  PanelLeftClose,
  CircleUserRound,
} from "lucide-react";

import background from "@/assets/178b.png";
import { ChatHistory } from "@/components/chat/ChatHistory";

interface AppLayoutProps {
  children: React.ReactNode;
}

export const AppLayout = ({ children }: AppLayoutProps) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);

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

              <ChatHistory isOpen={true} />

              <div className="sidebar-footer">
                <button className="sidebar-login">
                  <CircleUserRound size={19} />

                  <span className="sidebar-login-text">
                    Log In
                  </span>
                </button>
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
    </>
  );
};
