import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppProvider, useApp } from './context';
import { Layout } from './components/Layout';
import { ChatWidget } from './components/ChatWidget';
import { OnboardingPage } from './pages/OnboardingPage';
import { DocumentsPage } from './pages/DocumentsPage';
import { EligibilityPage } from './pages/EligibilityPage';
import { SimulatorPage } from './pages/SimulatorPage';
import { ChatPage } from './pages/ChatPage';
import { SetupPage } from './pages/SetupPage';

function Shell() {
  const { loading, error, clearError } = useApp();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-sand">
        <p className="font-display text-2xl text-forest animate-pulse">
          LoanReady
        </p>
      </div>
    );
  }

  return (
    <Layout>
      {error && (
        <div className="mb-4 bg-danger/10 border border-danger/30 text-danger text-sm px-4 py-2 rounded-lg flex justify-between gap-4">
          <span>{error}</span>
          <button type="button" onClick={clearError} className="underline">
            Dismiss
          </button>
        </div>
      )}
      <Routes>
        <Route path="/" element={<OnboardingPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/eligibility" element={<EligibilityPage />} />
        <Route path="/simulator" element={<SimulatorPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/setup" element={<SetupPage />} />
      </Routes>
      <ChatWidget />
    </Layout>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppProvider>
        <Shell />
      </AppProvider>
    </BrowserRouter>
  );
}
