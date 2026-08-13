import { useState, useEffect } from "react";
import { generateImage } from "@/services/requests";

export default function Generate() {
  const [prompt, setPrompt] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [imageUrl, setImageUrl] = useState<string | null>(null);


  // как только страница загружается,
  // сразу принимаем куки 
  useEffect(() => {
    fetch("http://localhost:8000/Text-to-Masterpiece", {
      credentials: "include", // параметр который приказывает браузеру 
                              // принять куки даже если домены разные 
    }).catch((err) => {
      console.error("Session init failed", err);
    });
  }, []);  // [] - массив зависимостей
           // т.к пустой то будет запускаться только раз 
           // при отображении веб интерфейса


  const handleGenerate = () => {
    if (!prompt.trim() || loading) return;
    handleGenerateAsync();
  };

  const handleGenerateAsync = async () => {
    try {
      setLoading(true);

      // сохраняем локально (UI отзывчивый)
      setHistory((prev) => [...prev, prompt]);

      // отправляем на backend
      const ImageUrl = await generateImage(prompt);

      // backend пока возвращает заглушку
      setImageUrl(
        ImageUrl
      );

      setPrompt("");
    } catch (err) {
      console.error("Generation failed", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ height: "100vh", display: "flex" }}>
      {/* Левая колонка */}
      <div
        style={{
          width: "50%",
          display: "flex",
          objectFit: "cover",
          flexDirection: "column",
          borderRight: "1px solid #ccc",
        }}
      >
        {/* История промптов */}
        <div style={{ flex: 2, padding: 16, overflowY: "auto" }}>
          <h2>Prompt history</h2>
          <ul>
            {history.map((h, i) => (
              <li key={i}>{h}</li>
            ))}
          </ul>
        </div>

        {/* Ввод */}
        <div
          style={{
            flex: 1,
            padding: 16,
            borderTop: "1px solid #ccc",
            display: "flex",
            gap: 8,
          }}
        >
          <textarea
            style={{ flex: 1 }}
            placeholder="Введите промпт..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <button onClick={handleGenerate} disabled={loading}>
            {loading ? "Генерация..." : "Сгенерировать"}
          </button>
        </div>
      </div>

      {/* Правая колонка */}
      <div
        style={{
          width: "50%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#f5f5f5",
        }}
      >
        {imageUrl ? (
          <img
            src={imageUrl}
            alt="Generated"
            style={{ 
              width: "100%", 
              height: "100%", 
              objectFit: "cover" 
            }}
          />
        ) : (
          <span style={{ color: "#888" }}>Здесь появится изображение</span>
        )}
      </div>
    </div>
  );
}
