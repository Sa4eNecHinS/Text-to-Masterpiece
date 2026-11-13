
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Home from '@/pages/home/home';
import Generate from '@/pages/generate/GeneratePage';
import { AuthProvider } from '@/components/auth/AuthProvider';
import { BackendNotice } from '@/components/BackendNotice';

function App() {
  return (
    <AuthProvider>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/Text-to-Masterpiece" element={<><BackendNotice /><Generate /></>} />
      </Routes>
    </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
