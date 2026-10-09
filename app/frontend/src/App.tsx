
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Home from '@/pages/home/home';
import Generate from '@/pages/generate/GeneratePage';
import { AuthProvider } from '@/components/auth/AuthProvider';

function App() {
  return (
    <AuthProvider>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/Text-to-Masterpiece" element={<Generate />} />
      </Routes>
    </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
