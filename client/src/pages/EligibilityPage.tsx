import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { useApp } from '../context';
import {
  LikelihoodBadge,
  formatINR,
  pct,
} from '../components/LikelihoodBadge';

export function EligibilityPage() {
  const { session, setEligibility } = useApp();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const profile = session?.profile;
  const eligibility = session?.eligibility;

  const run = async () => {
    if (!profile) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.evaluate();
      setEligibility(res.eligibility);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  if (!profile) {
    return (
      <Empty
        title="No profile yet"
        body="Complete onboarding or load the demo profile first."
        to="/"
        cta="Go to onboarding"
      />
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold text-forest">
            Eligibility dashboard
          </h1>
          <p className="text-ink/60 mt-1 text-sm">
            {profile.name} · {profile.loanType} loan ·{' '}
            {formatINR(profile.requestedAmount)}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void run()}
            disabled={loading}
            className="bg-forest text-foam px-4 py-2 rounded-lg text-sm font-medium hover:bg-leaf disabled:opacity-60"
          >
            {loading
              ? 'Evaluating…'
              : eligibility
                ? 'Re-evaluate'
                : 'Run evaluation'}
          </button>
          <Link
            to="/simulator"
            className="border border-forest/30 text-forest px-4 py-2 rounded-lg text-sm font-medium hover:bg-foam"
          >
            What-If simulator
          </Link>
        </div>
      </div>

      {error && <p className="text-danger text-sm">{error}</p>}

      {!eligibility ? (
        <div className="rounded-2xl border border-dashed border-forest/25 p-12 text-center bg-white/40">
          <p className="text-ink/70 mb-4">
            Run Agent 2 to calculate DTI, FOIR, and your action plan.
          </p>
          <button
            type="button"
            onClick={() => void run()}
            disabled={loading}
            className="bg-clay text-white px-5 py-2.5 rounded-lg font-medium"
          >
            {loading ? 'Working…' : 'Evaluate my application'}
          </button>
        </div>
      ) : (
        <>
          <div className="grid md:grid-cols-3 gap-4">
            <div className="md:col-span-1 bg-white/80 border border-forest/10 rounded-2xl p-6">
              <p className="text-xs uppercase tracking-wider text-ink/45 mb-4">
                Approval likelihood
              </p>
              <LikelihoodBadge
                likelihood={eligibility.approvalLikelihood}
                score={eligibility.score}
                size="lg"
              />
              <p className="text-xs text-ink/50 mt-4">
                Credit band: {eligibility.creditBand} · Est. EMI{' '}
                {formatINR(eligibility.estimatedEMI)}/mo
              </p>
            </div>

            <Metric
              label="DTI ratio"
              value={pct(eligibility.dtiRatio)}
              hint="Preferred under 40%"
              warn={eligibility.dtiRatio > 0.4}
            />
            <Metric
              label="FOIR ratio"
              value={pct(eligibility.foirRatio)}
              hint="Preferred under 50%"
              warn={eligibility.foirRatio > 0.5}
            />
          </div>

          {eligibility.riskFactors.length > 0 && (
            <section>
              <h2 className="font-display text-xl font-semibold text-forest mb-3">
                Risk factors
              </h2>
              <ul className="space-y-2">
                {eligibility.riskFactors.map((r) => (
                  <li
                    key={r}
                    className="bg-amber/10 border border-amber/30 rounded-xl px-4 py-3 text-sm"
                  >
                    {r}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h2 className="font-display text-xl font-semibold text-forest mb-3">
              Ranked action plan
            </h2>
            <ol className="space-y-3">
              {eligibility.actionPlan.map((item) => (
                <li
                  key={`${item.rank}-${item.title}`}
                  className="bg-white/80 border border-forest/10 rounded-xl p-4 flex gap-4"
                >
                  <span className="font-display text-2xl text-mint font-semibold w-8 shrink-0">
                    {item.rank}
                  </span>
                  <div className="flex-1">
                    <p className="font-medium">{item.title}</p>
                    <p className="text-sm text-ink/65 mt-1">
                      {item.description}
                    </p>
                    <p className="text-sm text-leaf font-medium mt-2">
                      {item.estimatedImpact}
                    </p>
                    {item.category === 'documents' && (
                      <Link
                        to="/documents"
                        className="text-xs text-forest underline mt-2 inline-block"
                      >
                        Fix documents →
                      </Link>
                    )}
                    {(item.category === 'amount' ||
                      item.category === 'debt' ||
                      item.category === 'co_applicant') && (
                      <Link
                        to="/simulator"
                        className="text-xs text-forest underline mt-2 inline-block"
                      >
                        Try in What-If simulator →
                      </Link>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <section className="grid sm:grid-cols-3 gap-3">
            <Link
              to="/documents"
              className="rounded-xl border border-forest/15 bg-white/70 px-4 py-3 text-sm hover:bg-foam"
            >
              <p className="font-medium text-forest">Document readiness</p>
              <p className="text-ink/55 text-xs mt-1">
                {session?.documents?.length || 0} file(s) on file — upload or
                replace
              </p>
            </Link>
            <Link
              to="/setup"
              className="rounded-xl border border-forest/15 bg-white/70 px-4 py-3 text-sm hover:bg-foam"
            >
              <p className="font-medium text-forest">KYC status</p>
              <p className="text-ink/55 text-xs mt-1">
                Local format checks only — not UIDAI verified
              </p>
            </Link>
            <button
              type="button"
              className="rounded-xl border border-forest/15 bg-white/70 px-4 py-3 text-sm text-left hover:bg-foam"
              onClick={() => {
                const text = [
                  `LoanReady estimate for ${profile.name}`,
                  `Likelihood: ${eligibility.approvalLikelihood}`,
                  `Score: ${eligibility.score}`,
                  `DTI: ${(eligibility.dtiRatio * 100).toFixed(1)}%`,
                  `FOIR: ${(eligibility.foirRatio * 100).toFixed(1)}%`,
                  `EMI: ₹${eligibility.estimatedEMI}`,
                  'Not a lender decision.',
                ].join('\n');
                void navigator.clipboard?.writeText(text).then(() => {
                  setCopied(true);
                  setTimeout(() => setCopied(false), 2000);
                });
              }}
            >
              <p className="font-medium text-forest">
                {copied ? 'Copied!' : 'Copy summary'}
              </p>
              <p className="text-ink/55 text-xs mt-1">
                Paste into notes or share with an advisor
              </p>
            </button>
          </section>
        </>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  hint,
  warn,
}: {
  label: string;
  value: string;
  hint: string;
  warn?: boolean;
}) {
  return (
    <div className="bg-white/80 border border-forest/10 rounded-2xl p-6 flex flex-col justify-center">
      <p className="text-xs uppercase tracking-wider text-ink/45">{label}</p>
      <p
        className={`font-display text-4xl font-semibold mt-2 ${warn ? 'text-clay' : 'text-forest'}`}
      >
        {value}
      </p>
      <p className="text-xs text-ink/50 mt-2">{hint}</p>
    </div>
  );
}

function Empty({
  title,
  body,
  to,
  cta,
}: {
  title: string;
  body: string;
  to: string;
  cta: string;
}) {
  return (
    <div className="text-center py-20">
      <h1 className="font-display text-2xl text-forest">{title}</h1>
      <p className="text-ink/60 mt-2 mb-6">{body}</p>
      <Link to={to} className="bg-forest text-foam px-4 py-2 rounded-lg text-sm">
        {cta}
      </Link>
    </div>
  );
}
