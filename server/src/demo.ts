import { v4 as uuidv4 } from 'uuid';
import type {
  CustomerProfile,
  DocumentRecord,
  EligibilityResult,
  SessionState,
} from './types.js';
import { evaluateEligibility } from './agents/eligibilityEngine.js';
import { replaceSession, createSession, getActiveSession } from './store.js';

/** Borderline demo profile for judges — interesting action plan, not a slam dunk */
export const DEMO_PROFILE: CustomerProfile = {
  name: 'Rahul Sharma',
  loanType: 'personal',
  requestedAmount: 800000,
  monthlyIncome: 85000,
  incomeType: 'salaried',
  existingEMIs: 12000,
  creditScore: 695,
  employmentTenureMonths: 14,
  interestRateEstimate: 0.13,
  loanTenureMonths: 36,
};

export function buildDemoDocuments(): DocumentRecord[] {
  const now = new Date().toISOString();
  return [
    {
      id: uuidv4(),
      type: 'aadhaar',
      filename: 'demo_aadhaar.pdf',
      originalName: 'aadhaar_rahul.pdf',
      mimeType: 'application/pdf',
      status: 'verified',
      extractedFields: {
        name: 'Rahul Sharma',
        address: '12 MG Road, Bengaluru, KA 560001',
        aadhaarLast4: '4321',
      },
      issues: [],
      infoRequests: [
        'Demo file — replace with your own Aadhaar scan using Upload on this row.',
      ],
      isDemo: true,
      uploadedAt: now,
    },
    {
      id: uuidv4(),
      type: 'pan',
      filename: 'demo_pan.pdf',
      originalName: 'pan_rahul.pdf',
      mimeType: 'application/pdf',
      status: 'verified',
      extractedFields: { name: 'Rahul Sharma', panLast4: 'K5L2' },
      issues: [],
      infoRequests: [
        'Demo file — replace with your own PAN card photo/PDF.',
      ],
      isDemo: true,
      uploadedAt: now,
    },
    {
      id: uuidv4(),
      type: 'salary_slip',
      filename: 'demo_salary.pdf',
      originalName: 'salary_jan2026.pdf',
      mimeType: 'application/pdf',
      status: 'needs_attention',
      extractedFields: {
        name: 'Rahul Sharma',
        employer: 'TechVista Solutions Pvt Ltd',
        netSalary: 72000,
        month: '2026-01',
      },
      issues: [
        'Only 1 month salary slip found — lenders usually want last 3 months',
      ],
      infoRequests: [
        'Upload Aug–Jan salary slips from sample-docs or your own payslips.',
      ],
      isDemo: true,
      uploadedAt: now,
    },
    {
      id: uuidv4(),
      type: 'bank_statement',
      filename: 'demo_bank.pdf',
      originalName: 'hdfc_statement.pdf',
      mimeType: 'application/pdf',
      status: 'verified',
      extractedFields: {
        name: 'Rahul Sharma',
        averageBalance: 145000,
        salaryCredits: 72000,
        period: '2025-08 to 2026-01',
      },
      issues: [],
      infoRequests: [
        'Demo statement — replace with bank_statement_6months.pdf or your real PDF.',
      ],
      isDemo: true,
      uploadedAt: now,
    },
  ];
}

export function loadDemoProfile(): SessionState {
  createSession();
  const session = getActiveSession();
  const eligibility: EligibilityResult = evaluateEligibility(DEMO_PROFILE);
  const demo: SessionState = {
    ...session,
    profile: DEMO_PROFILE,
    documents: buildDemoDocuments(),
    eligibility,
    chatHistory: [
      {
        id: uuidv4(),
        role: 'assistant',
        content:
          "Hi Rahul — demo profile loaded. Documents are placeholders: use each row's Upload button to add your own Aadhaar, PAN, salary slips, and bank statement. Reminder: this is a preparation estimate only, not a lender decision.",
        timestamp: new Date().toISOString(),
      },
    ],
    disclaimerShown: true,
  };
  return replaceSession(demo);
}
