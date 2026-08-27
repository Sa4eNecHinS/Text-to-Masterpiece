interface Props {
  prompt: string;
  setPrompt: (v: string) => void;
  onGenerate: () => void;
  loading: boolean;
}

export const InputBar = ({ prompt, setPrompt, onGenerate, loading }: Props) => (
  <div className="input-area">
    <div className="input-wrapper">
      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            onGenerate();
          }
        }}
        placeholder="Describe your thoughts..."
        rows={1}
        className="prompt-input"
      />
      <button
        onClick={onGenerate}
        disabled={loading || !prompt.trim()}
        className="generate-btn"
      >
        {loading ? "Generating..." : "Create"}
      </button>
    </div>
  </div>
);
