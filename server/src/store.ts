import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { v4 as uuidv4 } from 'uuid';
import type {
  ChatMessage,
  CustomerProfile,
  DocumentRecord,
  EligibilityResult,
  SessionState,
} from './types.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_STORE = path.resolve(__dirname, '../../data/store.json');

function storePath(): string {
  return process.env.STORE_PATH
    ? path.resolve(process.env.STORE_PATH)
    : DEFAULT_STORE;
}

interface StoreFile {
  sessions: Record<string, SessionState>;
  activeSessionId: string | null;
}

function emptyStore(): StoreFile {
  return { sessions: {}, activeSessionId: null };
}

function ensureDir(filePath: string): void {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function readStore(): StoreFile {
  const file = storePath();
  ensureDir(file);
  if (!fs.existsSync(file)) {
    const empty = emptyStore();
    fs.writeFileSync(file, JSON.stringify(empty, null, 2));
    return empty;
  }
  const raw = fs.readFileSync(file, 'utf-8');
  return JSON.parse(raw) as StoreFile;
}

function writeStore(store: StoreFile): void {
  const file = storePath();
  ensureDir(file);
  fs.writeFileSync(file, JSON.stringify(store, null, 2));
}

function touch(session: SessionState): SessionState {
  return { ...session, updatedAt: new Date().toISOString() };
}

export function createSession(): SessionState {
  const store = readStore();
  const now = new Date().toISOString();
  const session: SessionState = {
    sessionId: uuidv4(),
    profile: null,
    documents: [],
    eligibility: null,
    chatHistory: [],
    disclaimerShown: false,
    createdAt: now,
    updatedAt: now,
  };
  store.sessions[session.sessionId] = session;
  store.activeSessionId = session.sessionId;
  writeStore(store);
  return session;
}

export function getActiveSession(): SessionState {
  const store = readStore();
  if (store.activeSessionId && store.sessions[store.activeSessionId]) {
    return store.sessions[store.activeSessionId];
  }
  return createSession();
}

export function getSession(sessionId?: string): SessionState {
  if (!sessionId) return getActiveSession();
  const store = readStore();
  const session = store.sessions[sessionId];
  if (!session) throw new Error(`Session not found: ${sessionId}`);
  return session;
}

function saveSession(session: SessionState): SessionState {
  const store = readStore();
  const updated = touch(session);
  store.sessions[updated.sessionId] = updated;
  store.activeSessionId = updated.sessionId;
  writeStore(store);
  return updated;
}

export function updateProfile(profile: CustomerProfile): SessionState {
  const session = getActiveSession();
  return saveSession({ ...session, profile });
}

export function mergeProfile(
  partial: Partial<CustomerProfile>
): SessionState {
  const session = getActiveSession();
  const current = session.profile;
  const merged: CustomerProfile = {
    name: partial.name ?? current?.name ?? '',
    loanType: partial.loanType ?? current?.loanType ?? 'personal',
    requestedAmount:
      partial.requestedAmount ?? current?.requestedAmount ?? 0,
    monthlyIncome: partial.monthlyIncome ?? current?.monthlyIncome ?? 0,
    incomeType: partial.incomeType ?? current?.incomeType ?? 'salaried',
    existingEMIs: partial.existingEMIs ?? current?.existingEMIs ?? 0,
    creditScore: partial.creditScore ?? current?.creditScore ?? 0,
    employmentTenureMonths:
      partial.employmentTenureMonths ??
      current?.employmentTenureMonths ??
      0,
    coApplicant:
      partial.coApplicant !== undefined
        ? partial.coApplicant
        : current?.coApplicant,
    interestRateEstimate:
      partial.interestRateEstimate ??
      current?.interestRateEstimate ??
      0.12,
    loanTenureMonths:
      partial.loanTenureMonths ?? current?.loanTenureMonths ?? 36,
  };
  return saveSession({ ...session, profile: merged });
}

export function upsertDocument(
  doc: DocumentRecord,
  opts?: { replaceType?: boolean; replaceId?: string }
): SessionState {
  const session = getActiveSession();
  let documents = [...session.documents];

  if (opts?.replaceId) {
    const idx = documents.findIndex((d) => d.id === opts.replaceId);
    if (idx >= 0) documents[idx] = doc;
    else documents.push(doc);
  } else if (opts?.replaceType) {
    documents = documents.filter((d) => d.type !== doc.type);
    documents.push(doc);
  } else {
    documents.push(doc);
  }

  return saveSession({ ...session, documents });
}

export function deleteDocument(docId: string): SessionState {
  const session = getActiveSession();
  return saveSession({
    ...session,
    documents: session.documents.filter((d) => d.id !== docId),
  });
}

export function clearDocuments(): SessionState {
  const session = getActiveSession();
  return saveSession({ ...session, documents: [] });
}

export function setDocuments(documents: DocumentRecord[]): SessionState {
  const session = getActiveSession();
  return saveSession({ ...session, documents });
}

export function setEligibility(
  eligibility: EligibilityResult
): SessionState {
  const session = getActiveSession();
  return saveSession({ ...session, eligibility });
}

export function addChatMessage(message: ChatMessage): SessionState {
  const session = getActiveSession();
  return saveSession({
    ...session,
    chatHistory: [...session.chatHistory, message],
  });
}

export function markDisclaimerShown(): SessionState {
  const session = getActiveSession();
  return saveSession({ ...session, disclaimerShown: true });
}

export function replaceSession(session: SessionState): SessionState {
  return saveSession(session);
}

export function resetSession(): SessionState {
  const store = readStore();
  if (store.activeSessionId) {
    delete store.sessions[store.activeSessionId];
  }
  writeStore(store);
  return createSession();
}
