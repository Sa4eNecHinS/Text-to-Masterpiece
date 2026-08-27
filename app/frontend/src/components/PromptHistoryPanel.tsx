interface Props {
  history: string[];
}

export const PromptHistoryPanel = ({ history }: Props) => (
  <div className="prompt-history">
    <h2>Prompt history</h2>
    {history.length === 0 ? (
      <p className="empty-history">Nothing yet...</p>
    ) : (
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {history.map((h, i) => (
          <li key={i} className="prompt-item">{h}</li>
        ))}
      </ul>
    )}
  </div>
);
