interface Props {
  imageUrl: string | null;
  loading: boolean;
}

export const ImageViewer = ({ imageUrl, loading }: Props) => (
  <div className="image-viewer">
    {loading && (
      <div className="loader-overlay">
        <div className="spinner" />
      </div>
    )}
    
    {imageUrl ? (
      <img src={imageUrl} alt="Generated" className="generated-image" />
    ) : (
      <div className="placeholder-content">
        <span className="placeholder-icon">🎨</span>
        <p>Your masterpiece will appear here</p>
      </div>
    )}
  </div>
);
