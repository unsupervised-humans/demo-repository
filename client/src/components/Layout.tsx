import { Link, NavLink, useNavigate } from 'react-router-dom';
import { useApp } from '../context';

const links = [
  { to: '/', label: 'Onboarding', end: true },
  { to: '/documents', label: 'Documents' },
  { to: '/eligibility', label: 'Eligibility' },
  { to: '/simulator', label: 'What-If' },
  { to: '/chat', label: 'Chat' },
  { to: '/setup', label: 'Setup & KYC' },
];

export function Layout({ children }: { children: React.ReactNode }) {
  const { loadDemo, session, claudeConfigured } = useApp();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex flex-col">
      <div className="bg-forest text-foam text-center text-sm px-4 py-2.5 leading-snug">
        This tool provides an estimate to help you prepare your application. It
        does not guarantee loan approval and is not affiliated with any lender.
      </div>

      <header className="border-b border-forest/10 bg-sand/80 backdrop-blur sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-4 py-3 flex flex-wrap items-center gap-3 justify-between">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="font-display text-2xl font-semibold text-forest tracking-tight"
          >
            LoanReady
          </button>

          <nav className="flex flex-wrap gap-1">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  `px-3 py-1.5 text-sm rounded-md transition-colors ${
                    isActive
                      ? 'bg-forest text-foam'
                      : 'text-ink/70 hover:bg-foam hover:text-forest'
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            {!claudeConfigured ? (
              <Link
                to="/setup"
                className="text-xs text-amber bg-amber/15 px-2 py-1 rounded hover:bg-amber/25"
              >
                Offline — connect Groq
              </Link>
            ) : (
              <span className="text-xs text-ok bg-ok/15 px-2 py-1 rounded">
                Groq connected
              </span>
            )}
            <button
              type="button"
              onClick={async () => {
                await loadDemo();
                navigate('/eligibility');
              }}
              className="text-sm font-medium bg-clay text-white px-3 py-1.5 rounded-md hover:bg-clay/90 transition-colors"
            >
              Load demo profile
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-8">
        {children}
      </main>

      {session?.profile && (
        <div className="fixed bottom-0 left-0 right-0 pointer-events-none h-0" />
      )}
    </div>
  );
}
