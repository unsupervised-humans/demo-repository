import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';

type ProviderStatus = {
  configured: boolean;
  model: string;
  envVar: string;
  setup: string;
  consoleUrl: string;
};

type IntegrationStatus = {
  groq?: ProviderStatus;
  claude?: ProviderStatus;
  digilocker: {
    configured: boolean;
    envVars: string[];
    setup: string;
    docsUrl: string;
  };
  panVerify: {
    configured: boolean;
    envVars: string[];
    setup: string;
  };
  honesty: string;
};

type KycResult = {
  docType: string;
  level: string;
  passed: boolean;
  summary: string;
  details: string[];
  governmentApiAvailable: boolean;
  nextStep: string;
};

export function SetupPage() {
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [kyc, setKyc] = useState<KycResult[]>([]);
  const [aadhaarInput, setAadhaarInput] = useState('');
  const [panInput, setPanInput] = useState('');
  const [checkMsg, setCheckMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const llm = status?.groq || status?.claude;

  const load = async () => {
    setLoading(true);
    try {
      const [s, k] = await Promise.all([
        api.integrationsStatus(),
        api.kycStatus(),
      ]);
      setStatus(s);
      setKyc(k.results);
    } catch (e) {
      setCheckMsg((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const runCheck = async () => {
    setCheckMsg(null);
    try {
      const res = await api.kycCheck({
        aadhaar: aadhaarInput || undefined,
        pan: panInput || undefined,
      });
      setKyc([res.aadhaar, res.pan]);
      setCheckMsg(
        'Local checks updated. Government APIs stay disconnected unless env credentials are set.'
      );
    } catch (e) {
      setCheckMsg((e as Error).message);
    }
  };

  if (loading) {
    return <p className="text-ink/50 animate-pulse">Loading integration status…</p>;
  }

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h1 className="font-display text-3xl font-semibold text-forest">
          Connections &amp; KYC
        </h1>
        <p className="text-ink/60 mt-1 text-sm">{status?.honesty}</p>
      </div>

      <section
        className={`rounded-2xl border p-5 ${
          llm?.configured
            ? 'border-ok/30 bg-ok/5'
            : 'border-amber/40 bg-amber/10'
        }`}
      >
        <div className="flex flex-wrap justify-between gap-2 items-start">
          <div>
            <h2 className="font-display text-xl font-semibold text-forest">
              Groq API (chatbot + agents)
            </h2>
            <p className="text-sm text-ink/65 mt-1">
              Status:{' '}
              <strong>
                {llm?.configured ? 'Connected' : 'Not connected — Offline mode'}
              </strong>
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            className="text-xs border border-forest/25 px-3 py-1.5 rounded-lg"
          >
            Refresh
          </button>
        </div>
        {!llm?.configured && (
          <ol className="mt-4 text-sm space-y-2 list-decimal pl-5 text-ink/80">
            <li>
              Create a <strong>free</strong> key at{' '}
              <a
                className="text-leaf underline"
                href="https://console.groq.com/keys"
                target="_blank"
                rel="noreferrer"
              >
                console.groq.com/keys
              </a>
            </li>
            <li>
              Open <code className="bg-white/80 px-1 rounded">server/.env</code>
            </li>
            <li>
              Set{' '}
              <code className="bg-white/80 px-1 rounded">
                GROQ_API_KEY=gsk_your_key
              </code>
            </li>
            <li>
              Restart the server (
              <code className="bg-white/80 px-1 rounded">npm run dev</code>)
            </li>
            <li>
              Refresh this page, then open{' '}
              <Link to="/chat" className="text-leaf underline">
                Chat
              </Link>
            </li>
          </ol>
        )}
        {llm?.configured && (
          <p className="text-sm mt-3 text-ok">
            Model {llm.model} is ready for Document, Eligibility, and Chat
            agents.
          </p>
        )}
      </section>

      <section className="rounded-2xl border border-forest/10 bg-white/70 p-5 space-y-4">
        <h2 className="font-display text-xl font-semibold text-forest">
          Government KYC APIs
        </h2>
        <div className="text-sm space-y-3">
          <div>
            <p className="font-medium">DigiLocker / e-Aadhaar</p>
            <p className="text-ink/60">
              {status?.digilocker.configured ? 'Credentials set' : 'Not configured'}{' '}
              — {status?.digilocker.setup}
            </p>
          </div>
          <div>
            <p className="font-medium">PAN verification</p>
            <p className="text-ink/60">
              {status?.panVerify.configured ? 'Credentials set' : 'Not configured'}{' '}
              — {status?.panVerify.setup}
            </p>
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-forest/10 bg-white/70 p-5 space-y-4">
        <h2 className="font-display text-xl font-semibold text-forest">
          Local KYC checks (what we do today)
        </h2>
        <p className="text-sm text-ink/60">
          Format (PAN pattern, Aadhaar Verhoeff checksum) + name consistency.
          Not a bank or UIDAI decision.
        </p>

        <div className="grid sm:grid-cols-2 gap-3">
          <label className="text-sm">
            <span className="text-ink/60 block mb-1">Full Aadhaar (optional test)</span>
            <input
              value={aadhaarInput}
              onChange={(e) => setAadhaarInput(e.target.value)}
              placeholder="12 digits — not stored permanently"
              className="w-full border border-forest/20 rounded-lg px-3 py-2"
            />
          </label>
          <label className="text-sm">
            <span className="text-ink/60 block mb-1">Full PAN (optional test)</span>
            <input
              value={panInput}
              onChange={(e) => setPanInput(e.target.value.toUpperCase())}
              placeholder="ABCDE1234F"
              className="w-full border border-forest/20 rounded-lg px-3 py-2"
            />
          </label>
        </div>
        <button
          type="button"
          onClick={() => void runCheck()}
          className="bg-forest text-foam px-4 py-2 rounded-lg text-sm font-medium"
        >
          Run local KYC check
        </button>
        {checkMsg && <p className="text-sm text-ink/70">{checkMsg}</p>}

        <ul className="space-y-3 mt-2">
          {kyc.map((r) => (
            <li
              key={r.docType}
              className={`rounded-xl border px-4 py-3 ${
                r.passed ? 'border-ok/30 bg-ok/5' : 'border-amber/30 bg-amber/10'
              }`}
            >
              <p className="font-medium capitalize">
                {r.docType} — {r.summary}
              </p>
              <p className="text-xs uppercase tracking-wide text-ink/45 mt-0.5">
                Level: {r.level.replace(/_/g, ' ')}
              </p>
              <ul className="text-sm text-ink/70 mt-2 list-disc pl-4">
                {r.details.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
              <p className="text-sm text-leaf mt-2">{r.nextStep}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
