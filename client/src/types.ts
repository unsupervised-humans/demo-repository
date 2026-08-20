export type IncomeType = 'salaried' | 'self-employed';
export type LoanType = 'personal' | 'home' | 'auto' | 'business' | 'education';
export type DocumentType =
  | 'aadhaar'
  | 'pan'
  | 'salary_slip'
  | 'bank_statement'
  | 'itr'
  | 'form_16'
  | 'employment_letter'
  | 'address_proof'
  | 'cancelled_cheque'
  | 'utility_bill'
  | 'other';
export type DocumentStatus =
  | 'missing'
  | 'uploaded'
  | 'verified'
  | 'needs_attention';
export type ApprovalLikelihood =
  | 'rejected'
  | 'borderline'
  | 'likely_approved';

export interface CoApplicant {
  name: string;
  monthlyIncome: number;
  creditScore: number;
  existingEMIs: number;
}

export interface CustomerProfile {
  name: string;
  loanType: LoanType;
  requestedAmount: number;
  monthlyIncome: number;
  incomeType: IncomeType;
  existingEMIs: number;
  creditScore: number;
  employmentTenureMonths: number;
  coApplicant?: CoApplicant;
  interestRateEstimate?: number;
  loanTenureMonths?: number;
}

export interface DocumentRecord {
  id: string;
  type: DocumentType;
  filename: string;
  originalName: string;
  mimeType: string;
  status: DocumentStatus;
  extractedFields: Record<string, unknown>;
  issues: string[];
  infoRequests: string[];
  isDemo?: boolean;
  uploadedAt: string;
}

export interface DocSuggestion {
  id: string;
  severity: 'required' | 'recommended' | 'optional';
  title: string;
  detail: string;
  relatedDocType?: DocumentType;
  action: 'upload' | 'replace' | 'add_more' | 'update_profile' | 'review';
}

export interface ActionItem {
  rank: number;
  title: string;
  description: string;
  estimatedImpact: string;
  category: string;
  proposedChange?: ProposedChange;
}

export interface EligibilityResult {
  dtiRatio: number;
  foirRatio: number;
  approvalLikelihood: ApprovalLikelihood;
  score: number;
  creditBand: string;
  estimatedEMI: number;
  riskFactors: string[];
  actionPlan: ActionItem[];
  evaluatedAt: string;
}

export interface ProposedChange {
  requestedAmount?: number;
  existingEMIs?: number;
  monthlyIncome?: number;
  creditScore?: number;
  addCoApplicant?: CoApplicant;
  removeCoApplicant?: boolean;
  loanTenureMonths?: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  simulationResult?: EligibilityResult;
}

export interface SessionState {
  sessionId: string;
  profile: CustomerProfile | null;
  documents: DocumentRecord[];
  eligibility: EligibilityResult | null;
  chatHistory: ChatMessage[];
  disclaimerShown: boolean;
  createdAt: string;
  updatedAt: string;
}

export const DOC_LABELS: Record<DocumentType, string> = {
  aadhaar: 'Aadhaar Card',
  pan: 'PAN Card',
  salary_slip: 'Salary Slip',
  bank_statement: 'Bank Statement',
  itr: 'ITR',
  form_16: 'Form 16',
  employment_letter: 'Employment Letter',
  address_proof: 'Address Proof',
  cancelled_cheque: 'Cancelled Cheque',
  utility_bill: 'Utility Bill',
  other: 'Other',
};

export const DOC_HINTS: Record<DocumentType, string> = {
  aadhaar: 'Clear front (and back if available). Masked number is fine.',
  pan: 'Clear PAN scan or photo. Name must match Aadhaar.',
  salary_slip: 'Last 3–6 months. Upload one file per month.',
  bank_statement: 'Salary account, last 6 months (net-banking PDF preferred).',
  itr: 'Latest ITR-V / acknowledgement.',
  form_16: 'From employer for the latest FY.',
  employment_letter: 'Letterhead with joining date & designation.',
  address_proof: 'Aadhaar, passport, or voter ID with current address.',
  cancelled_cheque: 'Signed cancelled cheque of salary account.',
  utility_bill: 'Electricity / water / gas bill within last 3 months.',
  other: 'Any other supporting document.',
};

export const MULTI_DOC_TYPES: DocumentType[] = [
  'salary_slip',
  'bank_statement',
];
