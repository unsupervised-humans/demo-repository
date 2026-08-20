import type {
  CustomerProfile,
  DocumentRecord,
  DocumentType,
  DocSuggestion,
  EligibilityResult,
  ProposedChange,
  SessionState,
  ChatMessage,
} from './types';

const BASE = '/api';

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      ...(options?.body instanceof FormData
        ? {}
        : { 'Content-Type': 'application/json' }),
      ...options?.headers,
    },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data as T;
}

export type UploadResult = {
  document: DocumentRecord;
  issues: string[];
  infoRequests: string[];
  profile: CustomerProfile | null;
  documents: DocumentRecord[];
  suggestions: DocSuggestion[];
};

export const api = {
  health: () =>
    request<{
      ok: boolean;
      groqConfigured?: boolean;
      claudeConfigured: boolean;
      llmProvider?: string;
    }>('/health'),
  getSession: () => request<SessionState>('/session'),
  resetSession: () =>
    request<SessionState>('/session/reset', { method: 'POST' }),
  loadDemo: () => request<SessionState>('/demo/load', { method: 'POST' }),
  getProfile: () =>
    request<{
      profile: CustomerProfile | null;
      requiredDocs: DocumentType[];
      optionalDocs: DocumentType[];
    }>('/profile'),
  saveProfile: (profile: Partial<CustomerProfile>) =>
    request<{ profile: CustomerProfile }>('/profile', {
      method: 'POST',
      body: JSON.stringify(profile),
    }),
  getDocuments: () =>
    request<{
      documents: DocumentRecord[];
      requiredDocs: DocumentType[];
      optionalDocs: DocumentType[];
      suggestions: DocSuggestion[];
      hints: Record<string, string>;
    }>('/documents'),
  uploadDocument: async (
    file: File,
    opts?: {
      expectedType?: DocumentType;
      replaceId?: string;
      replaceType?: boolean;
    }
  ) => {
    const form = new FormData();
    form.append('file', file);
    if (opts?.expectedType) form.append('expectedType', opts.expectedType);
    if (opts?.replaceId) form.append('replaceId', opts.replaceId);
    if (opts?.replaceType) form.append('replaceType', 'true');
    return request<UploadResult>('/documents/upload', {
      method: 'POST',
      body: form,
    });
  },
  deleteDocument: (id: string) =>
    request<{ documents: DocumentRecord[]; suggestions: DocSuggestion[] }>(
      `/documents/${id}`,
      { method: 'DELETE' }
    ),
  clearDocuments: () =>
    request<{ documents: DocumentRecord[]; suggestions: DocSuggestion[] }>(
      '/documents/clear',
      { method: 'POST' }
    ),
  evaluate: () =>
    request<{ eligibility: EligibilityResult; profile: CustomerProfile }>(
      '/eligibility/evaluate',
      { method: 'POST' }
    ),
  simulate: (change: ProposedChange) =>
    request<{
      baseline: EligibilityResult;
      simulated: EligibilityResult;
      proposedChange: ProposedChange;
    }>('/eligibility/simulate', {
      method: 'POST',
      body: JSON.stringify(change),
    }),
  chat: (message: string) =>
    request<{
      reply: ChatMessage;
      simulationResult?: EligibilityResult;
      chatHistory: ChatMessage[];
    }>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  integrationsStatus: () =>
    request<{
      groq?: {
        configured: boolean;
        model: string;
        envVar: string;
        setup: string;
        consoleUrl: string;
      };
      claude?: {
        configured: boolean;
        model: string;
        envVar: string;
        setup: string;
        consoleUrl: string;
      };
      digilocker: {
        configured: boolean;
        envVars: string[];
        setup: string;
        docsUrl: string;
      };
      panVerify: {
        configured: boolean;
        envVars: string[];
        setup: string;
      };
      honesty: string;
    }>('/integrations/status'),
  kycStatus: () =>
    request<{
      results: Array<{
        docType: string;
        level: string;
        passed: boolean;
        summary: string;
        details: string[];
        governmentApiAvailable: boolean;
        nextStep: string;
      }>;
      disclaimer: string;
    }>('/integrations/kyc'),
  kycCheck: (body: { aadhaar?: string; pan?: string }) =>
    request<{
      aadhaar: {
        docType: string;
        level: string;
        passed: boolean;
        summary: string;
        details: string[];
        governmentApiAvailable: boolean;
        nextStep: string;
      };
      pan: {
        docType: string;
        level: string;
        passed: boolean;
        summary: string;
        details: string[];
        governmentApiAvailable: boolean;
        nextStep: string;
      };
    }>('/integrations/kyc/check', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};
