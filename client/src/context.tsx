import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import { api } from './api';
import type {
  CustomerProfile,
  DocumentRecord,
  EligibilityResult,
  SessionState,
  ChatMessage,
} from './types';

interface AppContextValue {
  session: SessionState | null;
  loading: boolean;
  error: string | null;
  claudeConfigured: boolean;
  refresh: () => Promise<void>;
  setProfile: (p: CustomerProfile) => void;
  setDocuments: (d: DocumentRecord[]) => void;
  setEligibility: (e: EligibilityResult) => void;
  setChatHistory: (h: ChatMessage[]) => void;
  loadDemo: () => Promise<void>;
  clearError: () => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [claudeConfigured, setClaudeConfigured] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const s = await api.getSession();
      setSession(s);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [s, health] = await Promise.all([
          api.getSession(),
          api.health().catch(() => ({ ok: false, claudeConfigured: false })),
        ]);
        setSession(s);
        setClaudeConfigured(
          Boolean(health.groqConfigured ?? health.claudeConfigured)
        );
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const loadDemo = async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await api.loadDemo();
      setSession(s);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const value: AppContextValue = {
    session,
    loading,
    error,
    claudeConfigured,
    refresh,
    setProfile: (profile) =>
      setSession((s) => (s ? { ...s, profile } : s)),
    setDocuments: (documents) =>
      setSession((s) => (s ? { ...s, documents } : s)),
    setEligibility: (eligibility) =>
      setSession((s) => (s ? { ...s, eligibility } : s)),
    setChatHistory: (chatHistory) =>
      setSession((s) => (s ? { ...s, chatHistory } : s)),
    loadDemo,
    clearError: () => setError(null),
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
