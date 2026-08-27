export const ChatLayout = ({ children }: { children: React.ReactNode }) => (
  <div className="flex h-screen w-full bg-[var(--bg-primary)] text-[var(--text-primary)] overflow-hidden">
    {children}
  </div>
);
