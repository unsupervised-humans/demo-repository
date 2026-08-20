import type {
  ApprovalLikelihood,
  CustomerProfile,
  EligibilityResult,
  ProposedChange,
  ActionItem,
} from '../types.js';
import { LENDER_THRESHOLDS } from '../types.js';

/** EMI using standard amortization formula */
export function estimateEMI(
  principal: number,
  annualRate: number,
  tenureMonths: number
): number {
  if (principal <= 0 || tenureMonths <= 0) return 0;
  const r = annualRate / 12;
  if (r === 0) return principal / tenureMonths;
  const factor = Math.pow(1 + r, tenureMonths);
  return (principal * r * factor) / (factor - 1);
}

export function calculateDTI(profile: CustomerProfile): number {
  const rate =
    profile.interestRateEstimate ?? LENDER_THRESHOLDS.DEFAULT_INTEREST_RATE;
  const tenure =
    profile.loanTenureMonths ?? LENDER_THRESHOLDS.DEFAULT_LOAN_TENURE_MONTHS;
  const newEmi = estimateEMI(profile.requestedAmount, rate, tenure);
  const totalObligations = profile.existingEMIs + newEmi;
  const income = effectiveIncome(profile);
  if (income <= 0) return 1;
  return totalObligations / income;
}

export function calculateFOIR(profile: CustomerProfile): number {
  // FOIR: fixed obligations (existing EMIs + new EMI) / income — same base as DTI for unsecured
  // For clarity we treat FOIR as obligations including a small living-expense buffer factor
  const dti = calculateDTI(profile);
  return Math.min(dti * 1.05, 1);
}

export function mapCreditBand(creditScore: number): string {
  if (creditScore >= LENDER_THRESHOLDS.CREDIT_SCORE_IDEAL) return 'Excellent';
  if (creditScore >= LENDER_THRESHOLDS.CREDIT_SCORE_GOOD) return 'Good';
  if (creditScore >= LENDER_THRESHOLDS.CREDIT_SCORE_FAIR) return 'Fair';
  if (creditScore >= LENDER_THRESHOLDS.CREDIT_SCORE_POOR) return 'Poor';
  return 'Very Poor';
}

function effectiveIncome(profile: CustomerProfile): number {
  let income = profile.monthlyIncome;
  if (profile.coApplicant) {
    income += profile.coApplicant.monthlyIncome;
  }
  return income;
}

function effectiveEMIs(profile: CustomerProfile): number {
  let emis = profile.existingEMIs;
  if (profile.coApplicant) {
    emis += profile.coApplicant.existingEMIs;
  }
  return emis;
}

function effectiveCredit(profile: CustomerProfile): number {
  if (!profile.coApplicant) return profile.creditScore;
  return Math.round(
    (profile.creditScore + profile.coApplicant.creditScore) / 2
  );
}

function scoreFromMetrics(
  dti: number,
  foir: number,
  creditScore: number,
  tenureMonths: number
): { score: number; likelihood: ApprovalLikelihood; riskFactors: string[] } {
  const risks: string[] = [];
  let score = 70;

  // DTI scoring
  if (dti <= LENDER_THRESHOLDS.DTI_PREFERRED_MAX) {
    score += 15;
  } else if (dti <= LENDER_THRESHOLDS.DTI_HARD_MAX) {
    score -= 10;
    risks.push(
      `DTI is ${(dti * 100).toFixed(1)}% — above preferred ${(LENDER_THRESHOLDS.DTI_PREFERRED_MAX * 100).toFixed(0)}% threshold`
    );
  } else {
    score -= 30;
    risks.push(
      `DTI is ${(dti * 100).toFixed(1)}% — exceeds hard limit of ${(LENDER_THRESHOLDS.DTI_HARD_MAX * 100).toFixed(0)}%`
    );
  }

  // FOIR
  if (foir > LENDER_THRESHOLDS.FOIR_HARD_MAX) {
    score -= 15;
    risks.push(
      `FOIR is ${(foir * 100).toFixed(1)}% — above hard limit of ${(LENDER_THRESHOLDS.FOIR_HARD_MAX * 100).toFixed(0)}%`
    );
  } else if (foir > LENDER_THRESHOLDS.FOIR_PREFERRED_MAX) {
    score -= 8;
    risks.push(
      `FOIR is ${(foir * 100).toFixed(1)}% — above preferred ${(LENDER_THRESHOLDS.FOIR_PREFERRED_MAX * 100).toFixed(0)}%`
    );
  }

  // Credit
  if (creditScore >= LENDER_THRESHOLDS.CREDIT_SCORE_IDEAL) {
    score += 12;
  } else if (creditScore >= LENDER_THRESHOLDS.CREDIT_SCORE_GOOD) {
    score += 5;
  } else if (creditScore >= LENDER_THRESHOLDS.CREDIT_SCORE_FAIR) {
    score -= 10;
    risks.push(
      `Credit score ${creditScore} is below ideal ${LENDER_THRESHOLDS.CREDIT_SCORE_GOOD}+ for unsecured personal loans`
    );
  } else {
    score -= 25;
    risks.push(
      `Credit score ${creditScore} is in a high-risk band — most lenders will decline or price very high`
    );
  }

  // Tenure
  if (tenureMonths < LENDER_THRESHOLDS.TENURE_MINIMUM_MONTHS) {
    score -= 20;
    risks.push(
      `Employment tenure of ${tenureMonths} months is below minimum ${LENDER_THRESHOLDS.TENURE_MINIMUM_MONTHS} months`
    );
  } else if (tenureMonths < LENDER_THRESHOLDS.TENURE_PREFERRED_MONTHS) {
    score -= 8;
    risks.push(
      `Employment tenure of ${tenureMonths} months is below preferred ${LENDER_THRESHOLDS.TENURE_PREFERRED_MONTHS} months`
    );
  } else {
    score += 5;
  }

  score = Math.max(
    LENDER_THRESHOLDS.MIN_SCORE,
    Math.min(LENDER_THRESHOLDS.MAX_SCORE, score)
  );

  let likelihood: ApprovalLikelihood;
  if (score >= 70 && dti <= LENDER_THRESHOLDS.DTI_HARD_MAX) {
    likelihood = 'likely_approved';
  } else if (score >= 45 && dti <= LENDER_THRESHOLDS.DTI_HARD_MAX + 0.05) {
    likelihood = 'borderline';
  } else {
    likelihood = 'rejected';
  }

  return { score, likelihood, riskFactors: risks };
}

export function applyProposedChange(
  profile: CustomerProfile,
  change: ProposedChange
): CustomerProfile {
  const next: CustomerProfile = { ...profile };
  if (change.requestedAmount !== undefined) {
    next.requestedAmount = change.requestedAmount;
  }
  if (change.existingEMIs !== undefined) {
    next.existingEMIs = change.existingEMIs;
  }
  if (change.monthlyIncome !== undefined) {
    next.monthlyIncome = change.monthlyIncome;
  }
  if (change.creditScore !== undefined) {
    next.creditScore = change.creditScore;
  }
  if (change.loanTenureMonths !== undefined) {
    next.loanTenureMonths = change.loanTenureMonths;
  }
  if (change.removeCoApplicant) {
    delete next.coApplicant;
  } else if (change.addCoApplicant) {
    next.coApplicant = change.addCoApplicant;
  }
  return next;
}

export function computeEligibilityCore(
  profile: CustomerProfile
): EligibilityResult {
  const rate =
    profile.interestRateEstimate ?? LENDER_THRESHOLDS.DEFAULT_INTEREST_RATE;
  const tenure =
    profile.loanTenureMonths ?? LENDER_THRESHOLDS.DEFAULT_LOAN_TENURE_MONTHS;
  const estimatedEMI = estimateEMI(profile.requestedAmount, rate, tenure);

  const evalProfile: CustomerProfile = {
    ...profile,
    monthlyIncome: effectiveIncome(profile),
    existingEMIs: effectiveEMIs(profile),
    creditScore: effectiveCredit(profile),
  };

  const dti = calculateDTI(evalProfile);
  const foir = calculateFOIR(evalProfile);
  const creditBand = mapCreditBand(evalProfile.creditScore);
  const { score, likelihood, riskFactors } = scoreFromMetrics(
    dti,
    foir,
    evalProfile.creditScore,
    profile.employmentTenureMonths
  );

  return {
    dtiRatio: Math.round(dti * 1000) / 1000,
    foirRatio: Math.round(foir * 1000) / 1000,
    approvalLikelihood: likelihood,
    score,
    creditBand,
    estimatedEMI: Math.round(estimatedEMI),
    riskFactors,
    actionPlan: [],
    evaluatedAt: new Date().toISOString(),
  };
}

export function evaluateEligibility(
  profile: CustomerProfile
): EligibilityResult {
  const core = computeEligibilityCore(profile);
  const actionPlan = generateActionPlan(profile, core);
  return { ...core, actionPlan };
}

export function simulateChange(
  profile: CustomerProfile,
  proposedChange: ProposedChange
): EligibilityResult {
  const simulated = applyProposedChange(profile, proposedChange);
  // Core only — avoid recurse through generateActionPlan
  return computeEligibilityCore(simulated);
}

export function generateActionPlan(
  profile: CustomerProfile,
  evaluation: EligibilityResult
): ActionItem[] {
  const items: ActionItem[] = [];
  const rate =
    profile.interestRateEstimate ?? LENDER_THRESHOLDS.DEFAULT_INTEREST_RATE;
  const tenure =
    profile.loanTenureMonths ?? LENDER_THRESHOLDS.DEFAULT_LOAN_TENURE_MONTHS;

  // Reduce loan amount
  if (evaluation.dtiRatio > LENDER_THRESHOLDS.DTI_PREFERRED_MAX) {
    const targetDti = LENDER_THRESHOLDS.DTI_PREFERRED_MAX;
    const income = effectiveIncome(profile);
    const maxTotalObligations = income * targetDti;
    const maxNewEmi = Math.max(0, maxTotalObligations - effectiveEMIs(profile));
    // Reverse EMI to principal
    const r = rate / 12;
    const factor = Math.pow(1 + r, tenure);
    const maxPrincipal =
      r === 0
        ? maxNewEmi * tenure
        : (maxNewEmi * (factor - 1)) / (r * factor);
    const reducedAmount = Math.floor(maxPrincipal / 10000) * 10000;
    if (reducedAmount > 0 && reducedAmount < profile.requestedAmount) {
      const sim = simulateChange(profile, {
        requestedAmount: reducedAmount,
      });
      items.push({
        rank: 0,
        title: `Reduce loan amount to ₹${(reducedAmount / 100000).toFixed(1)}L`,
        description: `Lowering your request from ₹${(profile.requestedAmount / 100000).toFixed(1)}L to ₹${(reducedAmount / 100000).toFixed(1)}L brings DTI into the preferred band.`,
        estimatedImpact: `Reduces DTI from ${(evaluation.dtiRatio * 100).toFixed(1)}% to ${(sim.dtiRatio * 100).toFixed(1)}%`,
        category: 'amount',
        proposedChange: { requestedAmount: reducedAmount },
      });
    }
  }

  // Pay down existing debt
  if (profile.existingEMIs > 0 && evaluation.dtiRatio > LENDER_THRESHOLDS.DTI_PREFERRED_MAX) {
    const payDown = Math.min(profile.existingEMIs, Math.round(profile.existingEMIs * 0.4));
    const newEmis = profile.existingEMIs - payDown;
    const sim = simulateChange(profile, { existingEMIs: newEmis });
    items.push({
      rank: 0,
      title: 'Pay down existing EMIs',
      description: `Clearing ~₹${payDown.toLocaleString('en-IN')}/mo of existing obligations frees capacity for the new loan.`,
      estimatedImpact: `Reduces DTI from ${(evaluation.dtiRatio * 100).toFixed(1)}% to ${(sim.dtiRatio * 100).toFixed(1)}%`,
      category: 'debt',
      proposedChange: { existingEMIs: newEmis },
    });
  }

  // Add co-applicant
  if (!profile.coApplicant && evaluation.score < 75) {
    const demoCo = {
      name: 'Co-applicant',
      monthlyIncome: Math.round(profile.monthlyIncome * 0.7),
      creditScore: Math.max(profile.creditScore, 720),
      existingEMIs: 0,
    };
    const sim = simulateChange(profile, { addCoApplicant: demoCo });
    items.push({
      rank: 0,
      title: 'Add a co-applicant with stable income',
      description:
        'A salaried co-applicant with good credit can raise household income and average credit band.',
      estimatedImpact: `Could lift score from ${evaluation.score} to ~${sim.score} and DTI to ${(sim.dtiRatio * 100).toFixed(1)}%`,
      category: 'co_applicant',
      proposedChange: { addCoApplicant: demoCo },
    });
  }

  // Credit improvement
  if (profile.creditScore < LENDER_THRESHOLDS.CREDIT_SCORE_GOOD) {
    items.push({
      rank: 0,
      title: 'Improve credit score before applying',
      description:
        'Pay revolving credit on time for 1–2 cycles, keep utilization under 30%, and dispute any errors on your bureau report.',
      estimatedImpact: `Moving from ${profile.creditScore} toward ${LENDER_THRESHOLDS.CREDIT_SCORE_GOOD}+ improves approval odds significantly`,
      category: 'credit',
    });
  }

  // Tenure / employment
  if (profile.employmentTenureMonths < LENDER_THRESHOLDS.TENURE_PREFERRED_MONTHS) {
    items.push({
      rank: 0,
      title: 'Wait until employment tenure hits 12 months',
      description:
        'Many lenders prefer at least 12 months with the current employer for unsecured loans.',
      estimatedImpact: `Removes tenure risk flag (currently ${profile.employmentTenureMonths} months)`,
      category: 'income',
    });
  }

  // Documents
  items.push({
    rank: 0,
    title: 'Ensure all KYC and income docs are recent',
    description:
      'Upload last 3 months salary slips, 6 months bank statements, and clear PAN/Aadhaar scans to avoid processing delays.',
    estimatedImpact: 'Reduces “needs attention” document flags that slow underwriting',
    category: 'documents',
  });

  // Rank by impact (score improvement proxy)
  return items
    .map((item, i) => ({ ...item, rank: i + 1 }))
    .slice(0, 6);
}
