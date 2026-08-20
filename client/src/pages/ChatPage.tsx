import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { useApp } from '../context';
import { LikelihoodBadge, pct } from '../components/LikelihoodBadge';

export function ChatPage() {
  const { session, setChatHistory, claudeConfigured } = useApp();
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const history = session?.chatHistory ?? [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history]);

  const send = async (override?: string) => {
    const text = (override ?? input).trim();
    if (!text || sending) return;
    if (!override) setInput('');
    setSending(true);
    setError(null);
    try {
      const res = await api.chat(text);
      setChatHistory(res.chatHistory);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  const suggestions = useMemo(() => {
    const base = [
      'What is DTI?',
      'Why was I flagged?',
      'What if I reduce my loan to 5 lakh?',
      'How can I improve my score?',
      'Is my Aadhaar verified with the government?',
    ];
    if (session?.eligibility?.riskFactors?.[0]) {
      base.unshift('Explain my top risk factor in simple words');
    }
    return base;
  }, [session?.eligibility?.riskFactors]);

  return (
    <div className="max-w-2xl mx-auto flex flex-col h-[calc(100vh-12rem)]">
      <div className="mb-4">
        <h1 className="font-display text-3xl font-semibold text-forest">
          Chat with LoanReady
        </h1>
        <p className="text-sm text-ink/60 mt-1">
          Context-aware of your profile, documents, and eligibility result.
        </p>
      </div>

      {!claudeConfigured && (
        <div className="mb-3 rounded-xl border border-amber/40 bg-amber/10 px-4 py-3 text-sm">
          <p className="font-medium text-ink">
            Chatbot is in offline mode (Groq API not connected)
          </p>
          <p className="text-ink/70 mt-1">
            Basic answers and what-ifs still work. For smarter replies, add a
            free Groq key.
          </p>
          <Link
            to="/setup"
            className="inline-block mt-2 text-leaf font-medium underline"
          >
            Open Setup &amp; KYC → connect Groq
          </Link>
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-3">
        {suggestions.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => void send(s)}
            className="text-xs bg-foam text-forest px-3 py-1.5 rounded-full hover:bg-mint/40"
          >
            {s}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 bg-white/50 border border-forest/10 rounded-2xl p-4">
        {history.length === 0 && (
          <p className="text-sm text-ink/60">
            Ask about terms, risk flags, documents, or try a natural-language
            what-if. Tip: we do <strong>not</strong> government-verify
            Aadhaar/PAN unless DigiLocker/PAN APIs are connected on Setup.
          </p>
        )}
        {history.map((m) => (
          <div
            key={m.id}
            className={`text-sm leading-relaxed max-w-[85%] ${
              m.role === 'user'
                ? 'ml-auto bg-forest text-foam rounded-2xl rounded-br-md px-4 py-2.5'
                : 'bg-sand border border-forest/10 rounded-2xl rounded-bl-md px-4 py-2.5'
            }`}
          >
            {m.content}
            {m.simulationResult && (
              <div className="mt-2 pt-2 border-t border-forest/10">
                <LikelihoodBadge
                  likelihood={m.simulationResult.approvalLikelihood}
                  score={m.simulationResult.score}
                  size="sm"
                />
                <p className="text-xs mt-1 opacity-70">
                  Simulated DTI {pct(m.simulationResult.dtiRatio)}
                </p>
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {error && <p className="text-danger text-sm mt-2">{error}</p>}

      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message…"
          className="flex-1 rounded-xl border border-forest/20 bg-white px-4 py-3 text-sm outline-none focus:border-leaf"
          disabled={sending}
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="bg-forest text-foam px-5 py-3 rounded-xl text-sm font-medium disabled:opacity-50"
        >
          {sending ? '…' : 'Send'}
        </button>
      </form>
    </div>
  );
}
