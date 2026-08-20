import { z } from 'zod';
import {
  callClaude,
  parseClaudeJson,
  isClaudeConfigured,
} from '../lib/claudeClient.js';
import {
  evaluateEligibility,
  simulateChange,
  generateActionPlan,
  applyProposedChange,
} from './eligibilityEngine.js';
import type {
  CustomerProfile,
  EligibilityResult,
  ProposedChange,
} from '../types.js';

const AGENT2_SYSTEM = `You are the Eligibility & Advisory Agent for LoanReady.
You think like a prudent Indian retail lender for personal/home/auto loans.
You NEVER guarantee approval. Frame everything as an estimate to help the customer prepare.
Return strict JSON only when asked. Be specific with INR amounts and percentage impacts.`;

const ActionPlanEnrichSchema = z.object({
  actionPlan: z.array(
    z.object({
      rank: z.number(),
      title: z.string(),
      description: z.string(),
      estimatedImpact: z.string(),
      category: z.enum([
        'amount',
        'debt',
        'credit',
        'income',
        'documents',
        'co_applicant',
      ]),
    })
  ),
});

/**
 * Full evaluation — deterministic engine first, optional Claude enrichment for plain-language plan.
 */
export async function runEligibilityEvaluation(
  profile: CustomerProfile
): Promise<EligibilityResult> {
  const base = evaluateEligibility(profile);

  if (!isClaudeConfigured()) {
    return base;
  }

  try {
    const raw = await callClaude({
      system: AGENT2_SYSTEM,
      messages: [
        {
          role: 'user',
          content: `Enrich this eligibility action plan in plain language for a stressed loan applicant.
Keep ranks, categories, and numeric impacts accurate — do not invent new metrics.
Profile: ${JSON.stringify(profile)}
Evaluation: ${JSON.stringify(base)}
Return JSON: {"actionPlan":[...same shape, improved wording...]}`,
        },
      ],
      jsonMode: true,
      temperature: 0.3,
    });

    const enriched = ActionPlanEnrichSchema.parse(parseClaudeJson(raw));
    return {
      ...base,
      actionPlan: enriched.actionPlan.map((a, i) => ({
        ...a,
        rank: a.rank || i + 1,
        proposedChange: base.actionPlan[i]?.proposedChange,
      })),
    };
  } catch {
    return base;
  }
}

export async function runSimulation(
  profile: CustomerProfile,
  proposedChange: ProposedChange
): Promise<EligibilityResult> {
  const next = applyProposedChange(profile, proposedChange);
  return evaluateEligibility(next);
}

export { evaluateEligibility, simulateChange, generateActionPlan };
