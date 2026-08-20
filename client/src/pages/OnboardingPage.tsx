import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useApp } from '../context';
import type { IncomeType, LoanType } from '../types';

export function OnboardingPage() {
  const { session, setProfile, loadDemo } = useApp();
  const navigate = useNavigate();
  const existing = session?.profile;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    name: existing?.name ?? '',
    loanType: (existing?.loanType ?? 'personal') as LoanType,
    requestedAmount: existing?.requestedAmount ?? 1000000,
    monthlyIncome: existing?.monthlyIncome ?? 60000,
    incomeType: (existing?.incomeType ?? 'salaried') as IncomeType,
    existingEMIs: existing?.existingEMIs ?? 0,
    creditScore: existing?.creditScore ?? 700,
    employmentTenureMonths: existing?.employmentTenureMonths ?? 24,
  });

  const update = (key: keyof typeof form, value: string | number) => {
    setForm((f) => ({ ...f, [key]: value }));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await api.saveProfile({
        ...form,
        requestedAmount: Number(form.requestedAmount),
        monthlyIncome: Number(form.monthlyIncome),
        existingEMIs: Number(form.existingEMIs),
        creditScore: Number(form.creditScore),
        employmentTenureMonths: Number(form.employmentTenureMonths),
      });
      setProfile(res.profile);
      navigate('/documents');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid lg:grid-cols-2 gap-10 items-start">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-forest via-leaf to-forest min-h-[320px] p-8 text-foam">
        <div
          className="absolute inset-0 opacity-30"
          style={{
            backgroundImage:
              'radial-gradient(circle at 20% 20%, #95d5b2 0%, transparent 45%), radial-gradient(circle at 80% 80%, #c45c26 0%, transparent 40%)',
          }}
        />
        <div className="relative">
          <p className="font-display text-4xl sm:text-5xl font-semibold leading-tight mb-4">
            LoanReady
          </p>
          <h1 className="text-xl sm:text-2xl font-medium text-foam/95 mb-3 max-w-md">
            Strengthen your loan application before the bank sees it.
          </h1>
          <p className="text-foam/75 max-w-sm text-sm leading-relaxed">
            Upload docs, see your DTI and approval likelihood, then fix what
            matters — with a plain-language action plan.
          </p>
          <button
            type="button"
            onClick={async () => {
              await loadDemo();
              navigate('/eligibility');
            }}
            className="mt-8 inline-flex bg-clay text-white px-4 py-2.5 rounded-lg text-sm font-semibold hover:bg-clay/90 transition-colors"
          >
            Skip — load demo profile
          </button>
        </div>
      </section>

      <section>
        <h2 className="font-display text-2xl font-semibold text-forest mb-1">
          Tell us about your loan
        </h2>
        <p className="text-ink/60 text-sm mb-6">
          A short profile is enough to start. Documents can fill in the rest.
        </p>

        <form onSubmit={submit} className="space-y-4">
          <Field label="Full name">
            <input
              required
              value={form.name}
              onChange={(e) => update('name', e.target.value)}
              className="field"
              placeholder="As on PAN / Aadhaar"
            />
          </Field>

          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Loan type">
              <select
                value={form.loanType}
                onChange={(e) => update('loanType', e.target.value)}
                className="field"
              >
                <option value="personal">Personal</option>
                <option value="home">Home</option>
                <option value="auto">Auto</option>
                <option value="business">Business</option>
                <option value="education">Education</option>
              </select>
            </Field>
            <Field label="Income type">
              <select
                value={form.incomeType}
                onChange={(e) => update('incomeType', e.target.value)}
                className="field"
              >
                <option value="salaried">Salaried</option>
                <option value="self-employed">Self-employed</option>
              </select>
            </Field>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Requested amount (₹)">
              <input
                type="number"
                required
                min={10000}
                step={10000}
                value={form.requestedAmount}
                onChange={(e) => update('requestedAmount', e.target.value)}
                className="field"
              />
            </Field>
            <Field label="Monthly income (₹)">
              <input
                type="number"
                required
                min={0}
                value={form.monthlyIncome}
                onChange={(e) => update('monthlyIncome', e.target.value)}
                className="field"
              />
            </Field>
          </div>

          <div className="grid sm:grid-cols-3 gap-4">
            <Field label="Existing EMIs (₹)">
              <input
                type="number"
                min={0}
                value={form.existingEMIs}
                onChange={(e) => update('existingEMIs', e.target.value)}
                className="field"
              />
            </Field>
            <Field label="Credit score">
              <input
                type="number"
                min={300}
                max={900}
                value={form.creditScore}
                onChange={(e) => update('creditScore', e.target.value)}
                className="field"
              />
            </Field>
            <Field label="Job tenure (months)">
              <input
                type="number"
                min={0}
                value={form.employmentTenureMonths}
                onChange={(e) =>
                  update('employmentTenureMonths', e.target.value)
                }
                className="field"
              />
            </Field>
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}

          {/* Live preview tips */}
          <div className="rounded-xl border border-forest/15 bg-foam/40 px-4 py-3 text-sm space-y-1">
            <p className="font-medium text-forest">Quick readiness check</p>
            <p className="text-ink/70">
              Rough EMI at ~13% / 36 mo:{' '}
              <strong>
                ₹
                {Math.round(
                  (Number(form.requestedAmount) *
                    (0.13 / 12) *
                    Math.pow(1 + 0.13 / 12, 36)) /
                    (Math.pow(1 + 0.13 / 12, 36) - 1)
                ).toLocaleString('en-IN')}
              </strong>
              /mo
            </p>
            <p className="text-ink/70">
              Rough DTI:{' '}
              <strong>
                {(
                  ((Number(form.existingEMIs) +
                    (Number(form.requestedAmount) *
                      (0.13 / 12) *
                      Math.pow(1 + 0.13 / 12, 36)) /
                      (Math.pow(1 + 0.13 / 12, 36) - 1)) /
                    Math.max(Number(form.monthlyIncome), 1)) *
                  100
                ).toFixed(0)}
                %
              </strong>{' '}
              (aim under 40%)
            </p>
            <p className="text-ink/55 text-xs">
              Next: upload Aadhaar, PAN, salary slips &amp; bank statement. KYC
              government verify needs Setup APIs — we only check format locally.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={saving}
              className="bg-forest text-foam px-6 py-2.5 rounded-lg font-medium hover:bg-leaf transition-colors disabled:opacity-60"
            >
              {saving ? 'Saving…' : 'Continue to documents'}
            </button>
            <button
              type="button"
              onClick={() => navigate('/setup')}
              className="border border-forest/25 text-forest px-4 py-2.5 rounded-lg text-sm"
            >
              Setup &amp; KYC
            </button>
            <button
              type="button"
              onClick={() => navigate('/chat')}
              className="border border-forest/25 text-forest px-4 py-2.5 rounded-lg text-sm"
            >
              Ask the chatbot
            </button>
          </div>
        </form>
      </section>

      <style>{`
        .field {
          width: 100%;
          border: 1px solid color-mix(in oklab, var(--color-forest) 20%, transparent);
          background: white;
          border-radius: 0.75rem;
          padding: 0.6rem 0.85rem;
          font-size: 0.95rem;
          outline: none;
        }
        .field:focus {
          border-color: var(--color-leaf);
          box-shadow: 0 0 0 3px color-mix(in oklab, var(--color-mint) 50%, transparent);
        }
      `}</style>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="text-ink/70 font-medium mb-1 block">{label}</span>
      {children}
    </label>
  );
}
