import { z } from 'zod';
import { v4 as uuidv4 } from 'uuid';
import {
  callClaude,
  parseClaudeJson,
  isClaudeConfigured,
} from '../lib/claudeClient.js';
import { simulateChange } from './eligibilityEngine.js';
import {
  addChatMessage,
  getActiveSession,
  markDisclaimerShown,
} from '../store.js';
import type {
  ChatMessage,
  CustomerProfile,
  EligibilityResult,
  ProposedChange,
  SessionState,
} from '../types.js';

const ChatResponseSchema = z.object({
  reply: z.string(),
  intent: z.enum([
    'general',
    'explain_term',
    'why_flagged',
    'what_if',
    'encouragement',
  ]),
  proposedChange: z
    .object({
      requestedAmount: z.number().optional(),
      existingEMIs: z.number().optional(),
      monthlyIncome: z.number().optional(),
      creditScore: z.number().optional(),
      loanTenureMonths: z.number().optional(),
      removeCoApplicant: z.boolean().optional(),
      addCoApplicant: z
        .object({
          name: z.string(),
          monthlyIncome: z.number(),
          creditScore: z.number(),
          existingEMIs: z.number(),
        })
        .optional(),
    })
    .nullable()
    .optional(),
});

function buildSystemPrompt(session: SessionState): string {
  const disclaimerNote = session.disclaimerShown
    ? 'Disclaimer already shown this session — do not repeat it.'
    : 'Include a brief one-line disclaimer that this is an estimate, not a guarantee, ONCE in your reply.';

  return `You are LoanReady's Customer Support Chatbot — warm, short, and specific.
The customer is stressed about getting a loan. Avoid jargon unless explaining it.
Never fabricate loan approval. Frame likelihood as an estimate only.
${disclaimerNote}

CURRENT CustomerProfile (JSON):
${JSON.stringify(session.profile, null, 2)}

CURRENT EligibilityResult (JSON):
${JSON.stringify(session.eligibility, null, 2)}

Document issues summary:
${JSON.stringify(
  session.documents.map((d) => ({
    type: d.type,
    status: d.status,
    issues: d.issues,
  })),
  null,
  2
)}

When the user asks a what-if (e.g. reduce loan to 9 lakh, pay down EMI, add co-applicant),
set intent to "what_if" and fill proposedChange with numeric fields in INR (9 lakh = 900000).
Otherwise proposedChange should be null.

Respond with JSON only:
{
  "reply": "short warm answer",
  "intent": "general|explain_term|why_flagged|what_if|encouragement",
  "proposedChange": null | { ... }
}`;
}

function offlineReply(
  message: string,
  session: SessionState
): z.infer<typeof ChatResponseSchema> {
  const lower = message.toLowerCase();

  // What-if: reduce loan
  const lakhMatch = lower.match(
    /(?:reduce|lower|what if|loan.*?to)\s*(?:.*?)\s*(\d+(?:\.\d+)?)\s*(?:lakh|lac|l)/i
  );
  const amountMatch = lower.match(
    /(?:₹|rs\.?|inr)?\s*(\d[\d,]*)\s*(?:rupees)?/i
  );

  if (
    (lower.includes('what if') || lower.includes('reduce') || lower.includes('lower')) &&
    (lakhMatch || (lower.includes('loan') && amountMatch))
  ) {
    let amount = session.profile?.requestedAmount ?? 1000000;
    if (lakhMatch) {
      amount = Math.round(parseFloat(lakhMatch[1]) * 100000);
    } else if (amountMatch) {
      amount = parseInt(amountMatch[1].replace(/,/g, ''), 10);
    }
    return {
      reply: `Let's check what happens if you request ₹${amount.toLocaleString('en-IN')} instead.`,
      intent: 'what_if',
      proposedChange: { requestedAmount: amount },
    };
  }

  if (lower.includes('dti') || lower.includes('debt-to-income')) {
    const dti = session.eligibility
      ? `${(session.eligibility.dtiRatio * 100).toFixed(1)}%`
      : 'not calculated yet';
    return {
      reply: `DTI (debt-to-income) is your total EMIs — including the new loan — divided by monthly income. Yours is currently ${dti}. Lenders prefer under 40%.`,
      intent: 'explain_term',
      proposedChange: null,
    };
  }

  if (lower.includes('foir')) {
    return {
      reply: `FOIR is fixed obligations to income — similar to DTI, measuring how much of your income is already committed. Keeping it under ~50% helps approval odds.`,
      intent: 'explain_term',
      proposedChange: null,
    };
  }

  if (lower.includes('why') || lower.includes('flag')) {
    const factors = session.eligibility?.riskFactors ?? [];
    if (factors.length) {
      return {
        reply: `Here's what stood out: ${factors.slice(0, 2).join(' ')} I can walk you through fixing any of these.`,
        intent: 'why_flagged',
        proposedChange: null,
      };
    }
    return {
      reply: `No major risk flags yet — run an eligibility check from the dashboard if you haven't.`,
      intent: 'why_flagged',
      proposedChange: null,
    };
  }

  const likelihood = session.eligibility?.approvalLikelihood ?? 'unknown';
  return {
    reply: `I'm here to help you strengthen your application before you approach a bank. Your current estimate is "${likelihood.replace('_', ' ')}". Ask me about DTI, your action plan, or try a what-if like "what if I reduce my loan to 9 lakh".`,
    intent: 'general',
    proposedChange: null,
  };
}

export interface ChatResult {
  message: ChatMessage;
  simulationResult?: EligibilityResult;
  disclaimerShown: boolean;
}

export async function handleChat(
  userText: string
): Promise<ChatResult> {
  let session = getActiveSession();

  const userMsg: ChatMessage = {
    id: uuidv4(),
    role: 'user',
    content: userText,
    timestamp: new Date().toISOString(),
  };
  session = addChatMessage(userMsg);

  let parsed: z.infer<typeof ChatResponseSchema>;

  if (isClaudeConfigured()) {
    try {
      const history = session.chatHistory.slice(-8).map((m) => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }));

      const raw = await callClaude({
        system: buildSystemPrompt(session),
        messages: [
          ...history.filter((m) => m.role === 'user' || m.role === 'assistant'),
          { role: 'user', content: userText },
        ],
        jsonMode: true,
        temperature: 0.4,
        maxTokens: 1024,
      });
      parsed = ChatResponseSchema.parse(parseClaudeJson(raw));
    } catch {
      parsed = offlineReply(userText, session);
    }
  } else {
    parsed = offlineReply(userText, session);
  }

  let simulationResult: EligibilityResult | undefined;
  if (
    parsed.intent === 'what_if' &&
    parsed.proposedChange &&
    session.profile
  ) {
    simulationResult = simulateChange(
      session.profile,
      parsed.proposedChange as ProposedChange
    );
    parsed.reply += ` Simulated result: likelihood ${simulationResult.approvalLikelihood.replace(/_/g, ' ')}, DTI ${(simulationResult.dtiRatio * 100).toFixed(1)}%, score ${simulationResult.score}/100. This is an estimate only — not a lender decision.`;
  }

  if (!session.disclaimerShown) {
    if (!parsed.reply.toLowerCase().includes('estimate')) {
      parsed.reply +=
        ' (Reminder: LoanReady gives preparation estimates only — not a guarantee of approval.)';
    }
    session = markDisclaimerShown();
  }

  const assistantMsg: ChatMessage = {
    id: uuidv4(),
    role: 'assistant',
    content: parsed.reply,
    timestamp: new Date().toISOString(),
    simulationResult,
  };
  addChatMessage(assistantMsg);

  return {
    message: assistantMsg,
    simulationResult,
    disclaimerShown: true,
  };
}
