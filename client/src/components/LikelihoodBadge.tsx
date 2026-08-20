import type { ApprovalLikelihood } from '../types';

const config: Record<
  ApprovalLikelihood,
  { label: string; className: string; ring: string }
> = {
  likely_approved: {
    label: 'Likely approved',
    className: 'bg-ok/15 text-ok border-ok/30',
    ring: 'stroke-ok',
  },
  borderline: {
    label: 'Borderline',
    className: 'bg-amber/20 text-ink border-amber/40',
    ring: 'stroke-amber',
  },
  rejected: {
    label: 'Likely declined',
    className: 'bg-danger/10 text-danger border-danger/30',
    ring: 'stroke-danger',
  },
};

export function LikelihoodBadge({
  likelihood,
  score,
  size = 'md',
}: {
  likelihood: ApprovalLikelihood;
  score?: number;
  size?: 'sm' | 'md' | 'lg';
}) {
  const c = config[likelihood];
  const pct = score ?? (likelihood === 'likely_approved' ? 80 : likelihood === 'borderline' ? 55 : 30);
  const r = size === 'lg' ? 54 : size === 'sm' ? 28 : 40;
  const stroke = size === 'lg' ? 8 : 6;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;

  return (
    <div className="flex items-center gap-4">
      <div className="relative" style={{ width: r * 2 + 16, height: r * 2 + 16 }}>
        <svg width={r * 2 + 16} height={r * 2 + 16} className="-rotate-90">
          <circle
            cx={r + 8}
            cy={r + 8}
            r={r}
            fill="none"
            stroke="currentColor"
            strokeWidth={stroke}
            className="text-forest/10"
          />
          <circle
            cx={r + 8}
            cy={r + 8}
            r={r}
            fill="none"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circ}
            strokeDashoffset={offset}
            className={c.ring}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`font-display font-semibold ${size === 'lg' ? 'text-2xl' : 'text-lg'}`}>
            {score ?? '—'}
          </span>
          {size !== 'sm' && (
            <span className="text-[10px] uppercase tracking-wide text-ink/50">score</span>
          )}
        </div>
      </div>
      <span
        className={`inline-flex border px-3 py-1 rounded-full text-sm font-medium ${c.className}`}
      >
        {c.label}
      </span>
    </div>
  );
}

export function formatINR(n: number): string {
  if (n >= 100000) {
    return `₹${(n / 100000).toFixed(n % 100000 === 0 ? 0 : 1)}L`;
  }
  return `₹${n.toLocaleString('en-IN')}`;
}

export function pct(ratio: number): string {
  return `${(ratio * 100).toFixed(1)}%`;
}
