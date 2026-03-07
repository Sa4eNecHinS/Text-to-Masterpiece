export default function ImageViewer({ imageUrl }: { imageUrl: string | null }) {
  return (
    <div className="image-wrapper">
      {imageUrl ? (
        <img src={imageUrl} alt="generated" className="generated-img" />
      ) : (
        <div className="placeholder">Your generated image will appear here</div>
      )}
    </div>
  )
}
