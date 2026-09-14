interface ChatHistoryProps {
  isOpen: boolean;
}

export const ChatHistory = ({ isOpen }: ChatHistoryProps) => {
  const chats = [
    { id: 1, title: "Cyberpunk city" },
    { id: 2, title: "Mountain landscape" },
    { id: 3, title: "Portrait experiment" },
  ];

  return (
    <div
      className={`chat-history ${
        isOpen ? "visible" : "hidden"
      }`}
    >
      <div className="chat-history-title">
        History
      </div>

      <div className="chat-history-list">
        {chats.map((chat) => (
          <button
            key={chat.id}
            className="chat-history-item"
          >
            {chat.title}
          </button>
        ))}
      </div>
    </div>
  );
};
