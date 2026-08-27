
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Home from '@/pages/home/home';
import Generate from '@/pages/generate/GeneratePage';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/Text-to-Masterpiece" element={<Generate />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
