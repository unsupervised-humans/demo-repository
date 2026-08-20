import fs from 'fs';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import pdfParse from 'pdf-parse';
import { z } from 'zod';
import {
  callClaude,
  callClaudeWithImage,
  parseClaudeJson,
  isClaudeConfigured,
} from '../lib/claudeClient.js';
import { mergeProfile, upsertDocument } from '../store.js';
import type {
  CustomerProfile,
  DocumentRecord,
  DocumentType,
} from '../types.js';

const DOC_TYPES: DocumentType[] = [
  'aadhaar',
  'pan',
  'salary_slip',
  'bank_statement',
  'itr',
  'form_16',
  'employment_letter',
  'address_proof',
  'cancelled_cheque',
  'utility_bill',
  'other',
];

const ClassifySchema = z.object({
  type: z.enum([
    'aadhaar',
    'pan',
    'salary_slip',
    'bank_statement',
    'itr',
    'form_16',
    'employment_letter',
    'address_proof',
    'cancelled_cheque',
    'utility_bill',
    'other',
  ]),
  confidence: z.number().optional(),
});

const ExtractSchema = z.object({
  fields: z.record(z.unknown()),
  summary: z.string().optional(),
});

const ValidateSchema = z.object({
  status: z.enum(['verified', 'needs_attention']),
  issues: z.array(z.string()),
  profileUpdates: z
    .object({
      name: z.string().optional(),
      monthlyIncome: z.number().optional(),
      existingEMIs: z.number().optional(),
      employmentTenureMonths: z.number().optional(),
      creditScore: z.number().optional(),
    })
    .optional(),
});

const AGENT1_SYSTEM = `You are the Document & Profile Agent for LoanReady, a loan pre-approval assistant.
You extract structured data from KYC and income documents for Indian loan applicants.
Always return strict JSON only. Never invent PAN/Aadhaar numbers — if unclear, omit or mark null.
Use INR amounts as numbers without currency symbols.
Be conservative: flag issues rather than guessing.

IMPORTANT DEMO & TESTING RULES:
- This is a testing/demo sandbox. Some documents are generated synthetically.
- Do NOT flag "synthetic", "demo", "sample", "hackathon", or "not real" labels or notices in the document text as validation issues or security failures.
- Do NOT flag masked numbers (like Aadhaar "XXXX XXXX 4321" or PAN "XXXXXK5L2") as missing or invalid. Masked identifiers are correct security practices and should be considered verified.
- Do NOT flag missing father_name or date_of_birth in the profile as an issue, because the system profile schema does not track these fields. As long as the applicant's name matches, consider it verified.
- Gross salary being higher than the profile monthly income is normal and expected (as people enter net/take-home income in onboarding). Do NOT flag this as a mismatch. Only flag if the net salary on the slip is significantly lower than the profile monthly income.
- Treat salary slips and bank statements as recent/valid if they cover the period up to the current date or match the dynamically generated sample dates.
- For Employment Letter: Do NOT flag it as "older than 3 months" or out of date. Permanent employment letters/joining letters are expected to be dated in the past when the employee joined. Furthermore, if the employment tenure shown in the letter (time since joining date) is higher than or equal to the profile tenure, do NOT flag it as a mismatch (longer tenure is positive).
- For Form 16: Accept the Form 16 if it covers the latest completed Indian financial year (April to March) or the previous year. Do not flag it as outdated unless it is more than 2 years old.`;

export async function classifyDocument(
  textOrHint: string,
  filename: string
): Promise<DocumentType> {
  if (!isClaudeConfigured()) {
    return heuristicClassify(filename, textOrHint);
  }

  const raw = await callClaude({
    system: AGENT1_SYSTEM,
    messages: [
      {
        role: 'user',
        content: `Classify this document. Filename: ${filename}\nContent/hint:\n${textOrHint.slice(0, 4000)}\n\nReturn JSON: {"type":"<one of ${DOC_TYPES.join('|')}>","confidence":0-1}`,
      },
    ],
    jsonMode: true,
  });

  const parsed = ClassifySchema.parse(parseClaudeJson(raw));
  return parsed.type;
}

function heuristicClassify(filename: string, text: string): DocumentType {
  const f = `${filename} ${text}`.toLowerCase();
  if (f.includes('aadhaar') || f.includes('aadhar')) return 'aadhaar';
  if (f.includes('pan')) return 'pan';
  if (f.includes('salary') || f.includes('payslip') || f.includes('pay slip'))
    return 'salary_slip';
  if (f.includes('bank') || f.includes('statement')) return 'bank_statement';
  if (f.includes('itr') || f.includes('income tax')) return 'itr';
  if (f.includes('form') && f.includes('16')) return 'form_16';
  if (f.includes('employment') || f.includes('offer')) return 'employment_letter';
  if (f.includes('cheque') || f.includes('check')) return 'cancelled_cheque';
  if (f.includes('utility') || f.includes('electric') || f.includes('gas bill'))
    return 'utility_bill';
  if (f.includes('address') || f.includes('utility')) return 'address_proof';
  return 'other';
}

export async function extractFields(
  filePath: string,
  docType: DocumentType,
  mimeType: string
): Promise<Record<string, unknown>> {
  const isImage = mimeType.startsWith('image/');
  const isPdf = mimeType === 'application/pdf' || filePath.endsWith('.pdf');

  if (!isClaudeConfigured()) {
    return mockExtract(docType);
  }

  if (isImage) {
    const buffer = fs.readFileSync(filePath);
    const base64 = buffer.toString('base64');
    const mediaType = (mimeType as 'image/jpeg' | 'image/png' | 'image/gif' | 'image/webp');
    const raw = await callClaudeWithImage({
      system: AGENT1_SYSTEM,
      prompt: `This is a ${docType} document image. Extract all relevant fields as JSON:
{"fields":{...},"summary":"one sentence"}
Include name, amounts, dates, account numbers (masked), employer, address as applicable.`,
      imageBase64: base64,
      mediaType: ['image/jpeg', 'image/png', 'image/gif', 'image/webp'].includes(mediaType)
        ? mediaType
        : 'image/jpeg',
      jsonMode: true,
    });
    return ExtractSchema.parse(parseClaudeJson(raw)).fields;
  }

  let text = '';
  if (isPdf) {
    const data = await pdfParse(fs.readFileSync(filePath));
    text = data.text || '';
  } else {
    text = fs.readFileSync(filePath, 'utf-8');
  }

  if (!text.trim()) {
    return mockExtract(docType);
  }

  const raw = await callClaude({
    system: AGENT1_SYSTEM,
    messages: [
      {
        role: 'user',
        content: `Document type: ${docType}\nExtract structured fields from this text. Return JSON {"fields":{...},"summary":"..."}\n\n${text.slice(0, 12000)}`,
      },
    ],
    jsonMode: true,
  });

  return ExtractSchema.parse(parseClaudeJson(raw)).fields;
}

function mockExtract(docType: DocumentType): Record<string, unknown> {
  const mocks: Record<DocumentType, Record<string, unknown>> = {
    aadhaar: {
      name: 'Rahul Sharma',
      address: '12 MG Road, Bengaluru, KA 560001',
      aadhaarLast4: '4321',
    },
    pan: { name: 'Rahul Sharma', panLast4: 'K5L2' },
    salary_slip: {
      name: 'Rahul Sharma',
      employer: 'TechVista Solutions Pvt Ltd',
      netSalary: 72000,
      month: '2026-01',
      grossSalary: 85000,
    },
    bank_statement: {
      name: 'Rahul Sharma',
      averageBalance: 145000,
      salaryCredits: 72000,
      period: '2025-08 to 2026-01',
    },
    itr: { name: 'Rahul Sharma', assessedIncome: 900000, ay: '2025-26' },
    form_16: { name: 'Rahul Sharma', taxableIncome: 860000 },
    employment_letter: {
      name: 'Rahul Sharma',
      employer: 'TechVista Solutions Pvt Ltd',
      designation: 'Senior Analyst',
      joiningDate: '2023-06-15',
    },
    address_proof: {
      name: 'Rahul Sharma',
      address: '12 MG Road, Bengaluru, KA 560001',
    },
    cancelled_cheque: {
      name: 'Rahul Sharma',
      bank: 'HDFC Bank',
      accountMasked: 'XXXX4821',
      ifsc: 'HDFC0001234',
    },
    utility_bill: {
      name: 'Rahul Sharma',
      address: '12 MG Road, Bengaluru, KA 560001',
      billMonth: '2026-01',
    },
    other: { note: 'Unrecognized document — manual review suggested' },
  };
  return mocks[docType];
}

export async function validateDocument(
  extractedFields: Record<string, unknown>,
  docType: DocumentType,
  profile: CustomerProfile | null
): Promise<{
  status: 'verified' | 'needs_attention';
  issues: string[];
  profileUpdates?: Partial<CustomerProfile>;
}> {
  if (!isClaudeConfigured()) {
    return heuristicValidate(extractedFields, docType, profile);
  }

  let checkInstructions = '';
  if (docType === 'salary_slip') {
    checkInstructions = 'Check: recency (salary slip pay period must be within the last 3 months), completeness, name consistency with profile.';
  } else if (docType === 'bank_statement') {
    checkInstructions = 'Check: recency (statement period must cover recent months ending close to today), completeness, name consistency with profile.';
  } else if (docType === 'utility_bill') {
    checkInstructions = 'Check: recency (bill date must be within the last 3 months), name consistency, address consistency with profile.';
  } else if (docType === 'aadhaar' || docType === 'pan') {
    checkInstructions = 'Check: name consistency with profile, completeness. Do NOT perform any recency checks on KYC documents (Aadhaar/PAN).';
  } else {
    checkInstructions = 'Check: name consistency with profile, completeness.';
  }

  const raw = await callClaude({
    system: AGENT1_SYSTEM,
    messages: [
      {
        role: 'user',
        content: `Validate this ${docType} extraction against the customer profile.
Extracted: ${JSON.stringify(extractedFields)}
Profile: ${JSON.stringify(profile)}
Instructions: ${checkInstructions}
Return JSON:
{"status":"verified"|"needs_attention","issues":["plain language"],"profileUpdates":{optional fields to merge}}`,
      },
    ],
    jsonMode: true,
  });

  return ValidateSchema.parse(parseClaudeJson(raw));
}

function heuristicValidate(
  fields: Record<string, unknown>,
  docType: DocumentType,
  profile: CustomerProfile | null
): {
  status: 'verified' | 'needs_attention';
  issues: string[];
  infoRequests: string[];
  profileUpdates?: Partial<CustomerProfile>;
} {
  const issues: string[] = [];
  const infoRequests: string[] = [];
  const updates: Partial<CustomerProfile> = {};

  if (
    fields.name &&
    profile?.name &&
    String(fields.name).toLowerCase() !== profile.name.toLowerCase()
  ) {
    issues.push(
      `Name on document ("${fields.name}") does not match profile ("${profile.name}")`
    );
    infoRequests.push(
      'Confirm the name on your KYC matches the name you entered in onboarding.'
    );
  }

  if (docType === 'salary_slip' && typeof fields.netSalary === 'number') {
    updates.monthlyIncome = fields.netSalary as number;
    if (fields.name && !profile?.name) updates.name = String(fields.name);
    if (!fields.month) {
      infoRequests.push(
        'Which month is this salary slip for? Upload slips labelled with the month.'
      );
    }
  }

  if (docType === 'salary_slip' && !fields.employer) {
    infoRequests.push('Employer name was not clear — upload a sharper scan.');
  }

  if (docType === 'bank_statement') {
    if (!fields.period) {
      infoRequests.push(
        'Please confirm the statement covers the last 6 months of your salary account.'
      );
    }
    if (!fields.salaryCredits && !fields.averageBalance) {
      infoRequests.push(
        'We could not see salary credits clearly — upload the PDF exported from net banking.'
      );
    }
  }

  if (docType === 'aadhaar' && !fields.address) {
    infoRequests.push(
      'Address was not readable on Aadhaar — upload a clearer image or add address proof.'
    );
  }

  if (docType === 'pan' && !fields.panLast4 && !fields.name) {
    issues.push('PAN details could not be read clearly');
    infoRequests.push('Re-upload PAN with better lighting / higher resolution.');
  }

  if (docType === 'employment_letter' && fields.joiningDate) {
    const joined = new Date(String(fields.joiningDate));
    if (!Number.isNaN(joined.getTime())) {
      const months =
        (Date.now() - joined.getTime()) / (1000 * 60 * 60 * 24 * 30.44);
      updates.employmentTenureMonths = Math.floor(months);
    }
  }

  if (Object.keys(fields).length < 2) {
    issues.push('Document appears incomplete — few fields could be extracted');
    infoRequests.push(
      'Try a PDF export instead of a phone photo, or retake with more light.'
    );
  }

  return {
    status: issues.length ? 'needs_attention' : 'verified',
    issues,
    infoRequests,
    profileUpdates: Object.keys(updates).length ? updates : undefined,
  };
}

function buildInfoRequests(
  docType: DocumentType,
  fields: Record<string, unknown>,
  issues: string[],
  extra: string[] = []
): string[] {
  const asks = [...extra];
  if (docType === 'salary_slip') {
    asks.push(
      'If you have more months, upload them too — lenders prefer 3–6 months.'
    );
  }
  if (issues.length) {
    asks.push('Resolve the flagged issues or replace this file before applying.');
  }
  if (!Object.keys(fields).length) {
    asks.push('No fields extracted — confirm the file is not password-protected.');
  }
  return [...new Set(asks)];
}

export function updateProfileFromFields(
  extractedFields: Record<string, unknown>,
  profileUpdates?: Partial<CustomerProfile>
): void {
  const partial: Partial<CustomerProfile> = { ...(profileUpdates || {}) };
  if (typeof extractedFields.name === 'string' && !partial.name) {
    partial.name = extractedFields.name;
  }
  if (typeof extractedFields.netSalary === 'number') {
    partial.monthlyIncome = extractedFields.netSalary;
  }
  if (
    typeof extractedFields.salaryCredits === 'number' &&
    !partial.monthlyIncome
  ) {
    partial.monthlyIncome = extractedFields.salaryCredits as number;
  }
  if (Object.keys(partial).length) {
    mergeProfile(partial);
  }
}

export interface ProcessDocumentResult {
  document: DocumentRecord;
  issues: string[];
  infoRequests: string[];
  profile: CustomerProfile | null;
}

export async function processUploadedDocument(opts: {
  filePath: string;
  originalName: string;
  mimeType: string;
  profile: CustomerProfile | null;
  expectedType?: DocumentType;
  replaceId?: string;
  replaceType?: boolean;
}): Promise<ProcessDocumentResult> {
  let textHint = opts.originalName;
  try {
    if (opts.mimeType === 'application/pdf' || opts.filePath.endsWith('.pdf')) {
      const data = await pdfParse(fs.readFileSync(opts.filePath));
      textHint = data.text?.slice(0, 2000) || opts.originalName;
    } else if (opts.mimeType === 'text/plain') {
      textHint = fs.readFileSync(opts.filePath, 'utf-8').slice(0, 2000);
    }
  } catch {
    // ignore parse errors for classification hint
  }

  const classified = await classifyDocument(textHint, opts.originalName);
  const docType = opts.expectedType || classified;

  const extractedFields = await extractFields(
    opts.filePath,
    docType,
    opts.mimeType
  );

  let validation: {
    status: 'verified' | 'needs_attention';
    issues: string[];
    infoRequests?: string[];
    profileUpdates?: Partial<CustomerProfile>;
  };

  if (!isClaudeConfigured()) {
    validation = heuristicValidate(extractedFields, docType, opts.profile);
  } else {
    const base = await validateDocument(
      extractedFields,
      docType,
      opts.profile
    );
    validation = { ...base, infoRequests: [] };
  }

  if (
    opts.expectedType &&
    classified !== opts.expectedType &&
    classified !== 'other'
  ) {
    validation.issues = [
      ...validation.issues,
      `File looks more like ${classified.replace(/_/g, ' ')} than ${opts.expectedType.replace(/_/g, ' ')}. You can still keep it if this is intentional.`,
    ];
    validation.infoRequests = [
      ...(validation.infoRequests || []),
      `Double-check you uploaded the correct file for ${opts.expectedType.replace(/_/g, ' ')}.`,
    ];
    if (validation.status === 'verified') {
      validation.status = 'needs_attention';
    }
  }

  const infoRequests = buildInfoRequests(
    docType,
    extractedFields,
    validation.issues,
    validation.infoRequests || []
  );

  updateProfileFromFields(extractedFields, validation.profileUpdates);

  const document: DocumentRecord = {
    id: uuidv4(),
    type: docType,
    filename: path.basename(opts.filePath),
    originalName: opts.originalName,
    mimeType: opts.mimeType,
    status: validation.status,
    extractedFields,
    issues: validation.issues,
    infoRequests,
    isDemo: false,
    uploadedAt: new Date().toISOString(),
  };

  const multi = ['salary_slip', 'bank_statement'].includes(docType);
  const session = upsertDocument(document, {
    replaceId: opts.replaceId,
    replaceType: opts.replaceType ?? (!multi && !opts.replaceId),
  });

  return {
    document,
    issues: validation.issues,
    infoRequests,
    profile: session.profile,
  };
}
