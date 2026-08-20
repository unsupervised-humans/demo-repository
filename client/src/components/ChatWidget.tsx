import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { useApp } from '../context';
import { LikelihoodBadge, pct } from './LikelihoodBadge';

export function ChatWidget() {
  const { session, setChatHistory } = useApp();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const history = session?.chatHistory ?? [];

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history, open]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
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

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-5 right-5 z-50 w-14 h-14 rounded-full bg-forest text-foam shadow-lg hover:scale-105 transition-transform flex items-center justify-center font-display text-lg"
        aria-label="Open chat"
      >
        {open ? '×' : 'Chat'}
      </button>

      {open && (
        <div className="fixed bottom-24 right-5 z-50 w-[min(100vw-2rem,380px)] h-[480px] bg-sand border border-forest/15 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
          <div className="bg-forest text-foam px-4 py-3 flex items-center justify-between">
            <div>
              <p className="font-display font-semibold">LoanReady Assistant</p>
              <p className="text-xs text-foam/70">Ask about DTI, flags, or what-ifs</p>
            </div>
            <Link
              to="/chat"
              className="text-xs underline text-mint"
              onClick={() => setOpen(false)}
            >
              Full page
            </Link>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {history.length === 0 && (
              <p className="text-sm text-ink/60 p-2">
                Hi — I can explain your eligibility result, document issues, or
                run a quick what-if. Try: &quot;what if I reduce my loan to 9
                lakh&quot;
              </p>
            )}
            {history.map((m) => (
              <div
                key={m.id}
                className={`text-sm leading-relaxed max-w-[90%] ${
                  m.role === 'user'
                    ? 'ml-auto bg-forest text-foam rounded-2xl rounded-br-md px-3 py-2'
                    : 'bg-white/80 border border-forest/10 rounded-2xl rounded-bl-md px-3 py-2'
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
                    <p className="text-xs mt-1 text-ink/60">
                      DTI {pct(m.simulationResult.dtiRatio)}
                    </p>
                  </div>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          {error && (
            <p className="px-3 text-xs text-danger">{error}</p>
          )}

          <form
            className="p-3 border-t border-forest/10 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask anything…"
              className="flex-1 rounded-xl border border-forest/20 bg-white px-3 py-2 text-sm outline-none focus:border-leaf"
              disabled={sending}
            />
            <button
              type="submit"
              disabled={sending || !input.trim()}
              className="bg-leaf text-white px-3 py-2 rounded-xl text-sm font-medium disabled:opacity-50"
            >
              {sending ? '…' : 'Send'}
            </button>
          </form>
        </div>
      )}
    </>
  );
}
