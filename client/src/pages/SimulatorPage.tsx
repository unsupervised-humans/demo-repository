import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { useApp } from '../context';
import type { EligibilityResult, CoApplicant } from '../types';
import {
  LikelihoodBadge,
  formatINR,
  pct,
} from '../components/LikelihoodBadge';

export function SimulatorPage() {
  const { session, setEligibility } = useApp();
  const profile = session?.profile;
  const baseline = session?.eligibility;

  const [amount, setAmount] = useState(profile?.requestedAmount ?? 1000000);
  const [debtPaydown, setDebtPaydown] = useState(0);
  const [addCo, setAddCo] = useState(false);
  const [coIncome, setCoIncome] = useState(50000);
  const [coCredit, setCoCredit] = useState(740);
  const [simulated, setSimulated] = useState<EligibilityResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (profile) setAmount(profile.requestedAmount);
  }, [profile]);

  useEffect(() => {
    if (!profile) return;
    const timer = setTimeout(() => {
      void runSim();
    }, 350);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [amount, debtPaydown, addCo, coIncome, coCredit, profile]);

  const runSim = async () => {
    if (!profile) return;
    setLoading(true);
    setError(null);
    try {
      if (!baseline) {
        const ev = await api.evaluate();
        setEligibility(ev.eligibility);
      }
      const newEmis = Math.max(
        0,
        (profile.existingEMIs || 0) - debtPaydown
      );
      const change: {
        requestedAmount: number;
        existingEMIs: number;
        addCoApplicant?: CoApplicant;
        removeCoApplicant?: boolean;
      } = {
        requestedAmount: amount,
        existingEMIs: newEmis,
      };
      if (addCo) {
        change.addCoApplicant = {
          name: 'Co-applicant',
          monthlyIncome: coIncome,
          creditScore: coCredit,
          existingEMIs: 0,
        };
      } else if (profile.coApplicant) {
        change.removeCoApplicant = false;
      }
      const res = await api.simulate(change);
      setSimulated(res.simulated);
      if (!baseline) setEligibility(res.baseline);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  if (!profile) {
    return (
      <div className="text-center py-20">
        <h1 className="font-display text-2xl text-forest">No profile yet</h1>
        <Link to="/" className="text-leaf underline mt-4 inline-block">
          Complete onboarding
        </Link>
      </div>
    );
  }

  const before = baseline;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-3xl font-semibold text-forest">
          What-If simulator
        </h1>
        <p className="text-ink/60 mt-1 text-sm max-w-xl">
          Adjust loan amount, pay down debt, or add a co-applicant. Compare
          live estimates side-by-side — your real profile stays unchanged.
        </p>
        <div className="flex flex-wrap gap-2 mt-3">
          {[
            {
              label: '−20% loan',
              apply: () =>
                setAmount(Math.round((profile.requestedAmount || amount) * 0.8)),
            },
            {
              label: 'Aim DTI ~40%',
              apply: () => {
                setDebtPaydown(0);
                setAmount(
                  Math.min(
                    profile.requestedAmount,
                    Math.round(profile.monthlyIncome * 0.4 * 28)
                  )
                );
              },
            },
            {
              label: 'Pay 40% EMIs',
              apply: () =>
                setDebtPaydown(Math.round((profile.existingEMIs || 0) * 0.4)),
            },
            {
              label: 'Add co-applicant',
              apply: () => setAddCo(true),
            },
          ].map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={p.apply}
              className="text-xs bg-foam text-forest px-3 py-1.5 rounded-full hover:bg-mint/40"
            >
              {p.label}
            </button>
          ))}
          <Link
            to="/chat"
            className="text-xs border border-forest/20 text-forest px-3 py-1.5 rounded-full hover:bg-foam"
          >
            Ask chatbot about this scenario
          </Link>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-8">
        <div className="space-y-6 bg-white/70 border border-forest/10 rounded-2xl p-6">
          <label className="block">
            <div className="flex justify-between text-sm mb-2">
              <span className="font-medium">Loan amount</span>
              <span className="text-forest font-semibold">
                {formatINR(amount)}
              </span>
            </div>
            <input
              type="range"
              min={100000}
              max={5000000}
              step={50000}
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
              className="w-full accent-leaf"
            />
          </label>

          <label className="block">
            <div className="flex justify-between text-sm mb-2">
              <span className="font-medium">Pay down existing EMIs</span>
              <span className="text-forest font-semibold">
                −{formatINR(debtPaydown)}/mo
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={profile.existingEMIs || 50000}
              step={500}
              value={debtPaydown}
              onChange={(e) => setDebtPaydown(Number(e.target.value))}
              className="w-full accent-leaf"
            />
          </label>

          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={addCo}
              onChange={(e) => setAddCo(e.target.checked)}
              className="accent-leaf w-4 h-4"
            />
            <span className="text-sm font-medium">Add co-applicant</span>
          </label>

          {addCo && (
            <div className="grid grid-cols-2 gap-3 pl-7">
              <label className="text-sm">
                <span className="text-ink/60 block mb-1">Their income</span>
                <input
                  type="number"
                  value={coIncome}
                  onChange={(e) => setCoIncome(Number(e.target.value))}
                  className="w-full border border-forest/20 rounded-lg px-3 py-2"
                />
              </label>
              <label className="text-sm">
                <span className="text-ink/60 block mb-1">Their credit</span>
                <input
                  type="number"
                  value={coCredit}
                  onChange={(e) => setCoCredit(Number(e.target.value))}
                  className="w-full border border-forest/20 rounded-lg px-3 py-2"
                />
              </label>
            </div>
          )}

          {loading && (
            <p className="text-xs text-ink/50">Recalculating…</p>
          )}
          {error && <p className="text-sm text-danger">{error}</p>}
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <CompareCard title="Before" result={before} muted />
          <CompareCard title="After" result={simulated} highlight />
        </div>
      </div>
    </div>
  );
}

function CompareCard({
  title,
  result,
  muted,
  highlight,
}: {
  title: string;
  result: EligibilityResult | null | undefined;
  muted?: boolean;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-2xl border p-5 ${
        highlight
          ? 'border-leaf bg-foam/40'
          : muted
            ? 'border-forest/10 bg-white/50'
            : 'border-forest/10 bg-white/80'
      }`}
    >
      <p className="text-xs uppercase tracking-wider text-ink/45 mb-3">
        {title}
      </p>
      {!result ? (
        <p className="text-sm text-ink/50">Run evaluation to see baseline</p>
      ) : (
        <>
          <LikelihoodBadge
            likelihood={result.approvalLikelihood}
            score={result.score}
            size="md"
          />
          <dl className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-ink/55">DTI</dt>
              <dd className="font-medium">{pct(result.dtiRatio)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ink/55">FOIR</dt>
              <dd className="font-medium">{pct(result.foirRatio)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-ink/55">Est. EMI</dt>
              <dd className="font-medium">
                {formatINR(result.estimatedEMI)}
              </dd>
            </div>
          </dl>
        </>
      )}
    </div>
  );
}
