export type IncomeType = 'salaried' | 'self-employed';
export type LoanType =
  | 'personal'
  | 'home'
  | 'auto'
  | 'business'
  | 'education';

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
  /** Plain-language asks for the customer when something is incomplete */
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
  category: 'amount' | 'debt' | 'credit' | 'income' | 'documents' | 'co_applicant';
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

/** Configurable lender thresholds — not magic numbers */
export const LENDER_THRESHOLDS = {
  DTI_PREFERRED_MAX: 0.4,
  DTI_HARD_MAX: 0.55,
  FOIR_PREFERRED_MAX: 0.5,
  FOIR_HARD_MAX: 0.65,
  CREDIT_SCORE_IDEAL: 750,
  CREDIT_SCORE_GOOD: 700,
  CREDIT_SCORE_FAIR: 650,
  CREDIT_SCORE_POOR: 600,
  TENURE_PREFERRED_MONTHS: 12,
  TENURE_MINIMUM_MONTHS: 6,
  DEFAULT_INTEREST_RATE: 0.12,
  DEFAULT_LOAN_TENURE_MONTHS: 36,
  MIN_SCORE: 0,
  MAX_SCORE: 100,
} as const;

export const REQUIRED_DOCS_BY_LOAN: Record<LoanType, DocumentType[]> = {
  personal: ['aadhaar', 'pan', 'salary_slip', 'bank_statement'],
  home: ['aadhaar', 'pan', 'salary_slip', 'bank_statement', 'itr', 'address_proof'],
  auto: ['aadhaar', 'pan', 'salary_slip', 'bank_statement'],
  business: ['aadhaar', 'pan', 'bank_statement', 'itr', 'form_16'],
  education: ['aadhaar', 'pan', 'bank_statement', 'salary_slip'],
};

/** Strongly recommended extras (not always mandatory) */
export const OPTIONAL_DOCS_BY_LOAN: Record<LoanType, DocumentType[]> = {
  personal: [
    'employment_letter',
    'form_16',
    'cancelled_cheque',
    'address_proof',
    'utility_bill',
  ],
  home: ['employment_letter', 'form_16', 'cancelled_cheque', 'utility_bill'],
  auto: [
    'employment_letter',
    'cancelled_cheque',
    'address_proof',
    'utility_bill',
  ],
  business: [
    'employment_letter',
    'cancelled_cheque',
    'address_proof',
    'utility_bill',
  ],
  education: [
    'employment_letter',
    'form_16',
    'cancelled_cheque',
    'address_proof',
  ],
};

/** Types that allow multiple file uploads (e.g. 6 months of slips) */
export const MULTI_UPLOAD_TYPES: DocumentType[] = [
  'salary_slip',
  'bank_statement',
];

export const DOC_UPLOAD_HINTS: Record<DocumentType, string> = {
  aadhaar: 'Clear front (and back if available). Masked number is fine.',
  pan: 'Clear PAN card scan or photo. Name must match Aadhaar.',
  salary_slip: 'Upload last 3–6 months. One PDF per month is ideal.',
  bank_statement: 'Salary account, last 6 months. PDF from net banking preferred.',
  itr: 'Latest ITR-V / acknowledgement for the previous assessment year.',
  form_16: 'From your employer for the latest financial year.',
  employment_letter: 'On company letterhead with joining date & designation.',
  address_proof: 'Aadhaar, passport, or voter ID with current address.',
  cancelled_cheque: 'Signed cancelled cheque of your salary account.',
  utility_bill: 'Electricity / water / gas bill dated within last 3 months.',
  other: 'Any supporting document the lender may ask for.',
};

