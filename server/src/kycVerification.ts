/**
 * Local KYC checks only — NOT UIDAI / Income Tax Department verification.
 *
 * Real Aadhaar e-KYC and PAN verification require licensed access
 * (DigiLocker / UIDAI / NSDL-UTIITSL) and cannot be called without
 * enterprise credentials. Configure stubs via env when you obtain them:
 *   DIGILOCKER_CLIENT_ID / DIGILOCKER_CLIENT_SECRET
 *   PAN_VERIFY_API_KEY / PAN_VERIFY_API_URL
 */

import type { CustomerProfile, DocumentRecord } from './types.js';

export type KycCheckLevel =
  | 'not_checked'
  | 'format_invalid'
  | 'format_ok'
  | 'consistency_ok'
  | 'govt_verified'; // only when a real API is plugged in

export interface KycCheckResult {
  docType: 'aadhaar' | 'pan';
  level: KycCheckLevel;
  passed: boolean;
  summary: string;
  details: string[];
  governmentApiAvailable: boolean;
  nextStep: string;
}

/** PAN format: 5 letters + 4 digits + 1 letter (e.g. ABCDE1234F) */
export function isValidPanFormat(pan: string): boolean {
  return /^[A-Z]{5}[0-9]{4}[A-Z]$/.test(pan.replace(/\s/g, '').toUpperCase());
}

/** Aadhaar: 12 digits + Verhoeff checksum */
export function isValidAadhaarFormat(aadhaar: string): boolean {
  const digits = aadhaar.replace(/\s/g, '');
  if (!/^\d{12}$/.test(digits)) return false;
  return verhoeffCheck(digits);
}

const VERHOEFF_D = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
  [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
  [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
  [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
  [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
  [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
  [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
  [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
  [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
];
const VERHOEFF_P = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
  [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
  [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
  [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
  [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
  [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
  [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
];

function verhoeffCheck(num: string): boolean {
  let c = 0;
  const reversed = num.split('').reverse().map(Number);
  for (let i = 0; i < reversed.length; i++) {
    c = VERHOEFF_D[c][VERHOEFF_P[i % 8][reversed[i]]];
  }
  return c === 0;
}

export function panApiConfigured(): boolean {
  return Boolean(
    process.env.PAN_VERIFY_API_KEY && process.env.PAN_VERIFY_API_URL
  );
}

export function digilockerConfigured(): boolean {
  return Boolean(
    process.env.DIGILOCKER_CLIENT_ID && process.env.DIGILOCKER_CLIENT_SECRET
  );
}

/**
 * Stub for future DigiLocker / UIDAI integration.
 * Returns null until credentials are set — never invents a "verified" result.
 */
export async function verifyAadhaarViaGovernment(_aadhaar: string): Promise<{
  verified: boolean;
  message: string;
} | null> {
  if (!digilockerConfigured()) return null;
  // Plug DigiLocker OAuth + e-Aadhaar fetch here when licensed.
  return {
    verified: false,
    message:
      'DigiLocker credentials present but integration not implemented yet.',
  };
}

export async function verifyPanViaGovernment(_pan: string): Promise<{
  verified: boolean;
  message: string;
} | null> {
  if (!panApiConfigured()) return null;
  // Plug NSDL / licensed PAN verify HTTP call here.
  return {
    verified: false,
    message: 'PAN API credentials present but integration not implemented yet.',
  };
}

export function checkPanLocal(
  rawPan: string | undefined,
  profile: CustomerProfile | null,
  doc?: DocumentRecord
): KycCheckResult {
  const gov = panApiConfigured();
  const details: string[] = [];
  const pan =
    rawPan ||
    (doc?.extractedFields?.pan as string) ||
    (doc?.extractedFields?.panLast4
      ? `XXXXX${doc.extractedFields.panLast4}`
      : undefined);

  if (!pan || String(pan).includes('XXXX')) {
    details.push(
      'Only a masked PAN was available — full format check needs the complete PAN (we never store full PAN in demos).'
    );
    return {
      docType: 'pan',
      level: 'not_checked',
      passed: false,
      summary: 'PAN format not fully checkable (masked)',
      details,
      governmentApiAvailable: gov,
      nextStep: gov
        ? 'Call licensed PAN verify API with user consent.'
        : 'Set PAN_VERIFY_API_KEY + PAN_VERIFY_API_URL for government verification, or upload a clearer PAN.',
    };
  }

  const normalized = String(pan).replace(/\s/g, '').toUpperCase();
  if (!isValidPanFormat(normalized)) {
    return {
      docType: 'pan',
      level: 'format_invalid',
      passed: false,
      summary: 'PAN format looks invalid',
      details: [
        'Expected pattern: 5 letters + 4 digits + 1 letter (e.g. ABCDE1234F).',
      ],
      governmentApiAvailable: gov,
      nextStep: 'Re-upload a clearer PAN card or correct the number.',
    };
  }

  details.push('PAN matches the standard format pattern.');
  let level: KycCheckLevel = 'format_ok';

  const docName = doc?.extractedFields?.name
    ? String(doc.extractedFields.name)
    : '';
  if (profile?.name && docName) {
    if (profile.name.toLowerCase() === docName.toLowerCase()) {
      details.push('Name on PAN matches your LoanReady profile.');
      level = 'consistency_ok';
    } else {
      details.push(
        `Name mismatch: profile "${profile.name}" vs PAN "${docName}".`
      );
    }
  }

  details.push(
    'This is NOT Income Tax Department verification — only local format/consistency.'
  );

  return {
    docType: 'pan',
    level,
    passed: level === 'format_ok' || level === 'consistency_ok',
    summary:
      level === 'consistency_ok'
        ? 'PAN format OK + name consistent'
        : 'PAN format OK (not govt-verified)',
    details,
    governmentApiAvailable: gov,
    nextStep: gov
      ? 'Run licensed PAN verification with consent.'
      : 'To verify with the government, obtain NSDL/UTIITSL (or DigiLocker) API access and set env vars.',
  };
}

export function checkAadhaarLocal(
  rawAadhaar: string | undefined,
  profile: CustomerProfile | null,
  doc?: DocumentRecord
): KycCheckResult {
  const gov = digilockerConfigured();
  const details: string[] = [];
  const aadhaar =
    rawAadhaar ||
    (doc?.extractedFields?.aadhaar as string) ||
    (doc?.extractedFields?.aadhaarLast4
      ? undefined
      : undefined);

  if (!aadhaar) {
    details.push(
      'Full 12-digit Aadhaar not stored (demo uses last-4 only for privacy).'
    );
    if (doc?.extractedFields?.aadhaarLast4) {
      details.push(
        `Last-4 on file: ${doc.extractedFields.aadhaarLast4}. Name/address consistency can still be checked.`
      );
    }
    const docName = doc?.extractedFields?.name
      ? String(doc.extractedFields.name)
      : '';
    if (profile?.name && docName) {
      if (profile.name.toLowerCase() === docName.toLowerCase()) {
        details.push('Name on Aadhaar matches profile.');
        return {
          docType: 'aadhaar',
          level: 'consistency_ok',
          passed: true,
          summary: 'Name consistent (Aadhaar not govt-verified)',
          details: [
            ...details,
            'UIDAI e-KYC / DigiLocker not connected — we never claim government validity.',
          ],
          governmentApiAvailable: gov,
          nextStep:
            'Connect DigiLocker (DIGILOCKER_CLIENT_ID/SECRET) for real e-Aadhaar fetch with user consent.',
        };
      }
    }
    return {
      docType: 'aadhaar',
      level: 'not_checked',
      passed: false,
      summary: 'Full Aadhaar not available for checksum',
      details,
      governmentApiAvailable: gov,
      nextStep:
        'Upload Aadhaar or connect DigiLocker. We do not call UIDAI without licensed access.',
    };
  }

  const digits = String(aadhaar).replace(/\s/g, '');
  if (!isValidAadhaarFormat(digits)) {
    return {
      docType: 'aadhaar',
      level: 'format_invalid',
      passed: false,
      summary: 'Aadhaar number failed format/checksum',
      details: [
        'Aadhaar must be 12 digits and pass the Verhoeff checksum.',
      ],
      governmentApiAvailable: gov,
      nextStep: 'Check for typos or re-upload a clearer scan.',
    };
  }

  details.push('Aadhaar passed local Verhoeff checksum (format only).');
  details.push(
    'Checksum ≠ UIDAI confirmation that the card is active/issued.'
  );

  return {
    docType: 'aadhaar',
    level: 'format_ok',
    passed: true,
    summary: 'Aadhaar format OK (not govt-verified)',
    details,
    governmentApiAvailable: gov,
    nextStep: gov
      ? 'Complete DigiLocker consent flow for e-Aadhaar.'
      : 'Set DIGILOCKER_CLIENT_ID + DIGILOCKER_CLIENT_SECRET to enable real verification.',
  };
}

export function runLocalKycBundle(
  profile: CustomerProfile | null,
  documents: DocumentRecord[]
): KycCheckResult[] {
  const aadhaarDoc = documents.find((d) => d.type === 'aadhaar');
  const panDoc = documents.find((d) => d.type === 'pan');
  return [
    checkAadhaarLocal(undefined, profile, aadhaarDoc),
    checkPanLocal(undefined, profile, panDoc),
  ];
}
