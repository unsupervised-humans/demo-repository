import type {
  CustomerProfile,
  DocumentRecord,
  DocumentType,
  DocSuggestion,
  LoanType,
} from './types.js';
import {
  DOC_UPLOAD_HINTS,
  MULTI_UPLOAD_TYPES,
  OPTIONAL_DOCS_BY_LOAN,
  REQUIRED_DOCS_BY_LOAN,
} from './types.js';

const SALARY_TARGET = 3;
const BANK_TARGET_MONTHS = 6;

export function requiredDocs(loanType?: LoanType | null): DocumentType[] {
  return REQUIRED_DOCS_BY_LOAN[loanType || 'personal'];
}

export function optionalDocs(loanType?: LoanType | null): DocumentType[] {
  return OPTIONAL_DOCS_BY_LOAN[loanType || 'personal'];
}

export function docsOfType(
  documents: DocumentRecord[],
  type: DocumentType
): DocumentRecord[] {
  return documents.filter((d) => d.type === type);
}

export function buildDocSuggestions(
  profile: CustomerProfile | null,
  documents: DocumentRecord[]
): DocSuggestion[] {
  const suggestions: DocSuggestion[] = [];
  const loan = profile?.loanType || 'personal';
  const required = requiredDocs(loan);
  const optional = optionalDocs(loan);

  for (const type of required) {
    const list = docsOfType(documents, type);
    if (list.length === 0) {
      suggestions.push({
        id: `missing-${type}`,
        severity: 'required',
        title: `Upload your ${label(type)}`,
        detail: DOC_UPLOAD_HINTS[type],
        relatedDocType: type,
        action: 'upload',
      });
      continue;
    }

    if (type === 'salary_slip' && list.length < SALARY_TARGET) {
      suggestions.push({
        id: 'salary-more',
        severity: 'recommended',
        title: `Add more salary slips (${list.length}/${SALARY_TARGET}+ months)`,
        detail:
          'Most lenders want at least the last 3 months. You can upload more files below.',
        relatedDocType: 'salary_slip',
        action: 'add_more',
      });
    }

    if (type === 'bank_statement' && list.length === 1) {
      const period = String(list[0].extractedFields?.period || '');
      if (!period.toLowerCase().includes('6') && !period.includes('Aug')) {
        suggestions.push({
          id: 'bank-period',
          severity: 'recommended',
          title: 'Confirm bank statement covers 6 months',
          detail: `Upload a full ${BANK_TARGET_MONTHS}-month statement from your salary account if this one is shorter.`,
          relatedDocType: 'bank_statement',
          action: 'replace',
        });
      }
    }

    for (const doc of list) {
      if (doc.status === 'needs_attention' || doc.issues.length) {
        suggestions.push({
          id: `issue-${doc.id}`,
          severity: 'required',
          title: `Fix issues on ${label(doc.type)}`,
          detail: doc.issues[0] || 'Document needs attention before you apply.',
          relatedDocType: doc.type,
          action: 'replace',
        });
      }
      for (const ask of doc.infoRequests || []) {
        suggestions.push({
          id: `info-${doc.id}-${ask.slice(0, 24)}`,
          severity: 'recommended',
          title: 'More information needed',
          detail: ask,
          relatedDocType: doc.type,
          action: 'review',
        });
      }
      if (doc.isDemo) {
        suggestions.push({
          id: `demo-${doc.type}`,
          severity: 'optional',
          title: `Replace demo ${label(doc.type)} with your own file`,
          detail:
            'Demo files are synthetic. Upload your real PDF/image using the Upload button on that row.',
          relatedDocType: doc.type,
          action: 'replace',
        });
      }
    }
  }

  // Profile gaps
  if (profile) {
    if (!profile.creditScore || profile.creditScore < 300) {
      suggestions.push({
        id: 'profile-credit',
        severity: 'required',
        title: 'Add your credit score',
        detail:
          'Update it on Onboarding, or tell the chat your approximate CIBIL/Experian score.',
        action: 'update_profile',
      });
    }
    if (!profile.monthlyIncome) {
      suggestions.push({
        id: 'profile-income',
        severity: 'required',
        title: 'Confirm monthly income',
        detail:
          'Upload a salary slip so we can extract net pay, or enter income on Onboarding.',
        relatedDocType: 'salary_slip',
        action: 'upload',
      });
    }
    if (profile.incomeType === 'self-employed') {
      const hasItr = docsOfType(documents, 'itr').length > 0;
      if (!hasItr) {
        suggestions.push({
          id: 'se-itr',
          severity: 'required',
          title: 'Self-employed? Upload ITR',
          detail: 'Lenders usually need ITR for at least the last 2 years.',
          relatedDocType: 'itr',
          action: 'upload',
        });
      }
    }
  } else {
    suggestions.push({
      id: 'no-profile',
      severity: 'required',
      title: 'Complete onboarding first',
      detail: 'Tell us loan type and amount so we know which documents apply.',
      action: 'update_profile',
    });
  }

  // Optional boosters not yet uploaded
  for (const type of optional) {
    if (docsOfType(documents, type).length === 0) {
      suggestions.push({
        id: `opt-${type}`,
        severity: 'optional',
        title: `Optional: ${label(type)}`,
        detail: DOC_UPLOAD_HINTS[type],
        relatedDocType: type,
        action: 'upload',
      });
    }
  }

  // Dedupe by id
  const seen = new Set<string>();
  return suggestions.filter((s) => {
    if (seen.has(s.id)) return false;
    seen.add(s.id);
    return true;
  });
}

function label(type: DocumentType): string {
  const map: Record<DocumentType, string> = {
    aadhaar: 'Aadhaar',
    pan: 'PAN',
    salary_slip: 'salary slip',
    bank_statement: 'bank statement',
    itr: 'ITR',
    form_16: 'Form 16',
    employment_letter: 'employment letter',
    address_proof: 'address proof',
    cancelled_cheque: 'cancelled cheque',
    utility_bill: 'utility bill',
    other: 'document',
  };
  return map[type];
}

export function allowsMultiple(type: DocumentType): boolean {
  return MULTI_UPLOAD_TYPES.includes(type);
}
