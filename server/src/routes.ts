import { Router } from 'express';
import multer from 'multer';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';
import {
  getActiveSession,
  updateProfile,
  mergeProfile,
  resetSession,
  setEligibility,
  deleteDocument,
  clearDocuments,
} from './store.js';
import { processUploadedDocument } from './agents/documentAgent.js';
import {
  runEligibilityEvaluation,
  runSimulation,
} from './agents/eligibilityAgent.js';
import { handleChat } from './agents/chatAgent.js';
import { loadDemoProfile } from './demo.js';
import type { CustomerProfile, DocumentType, ProposedChange } from './types.js';
import { DOC_UPLOAD_HINTS } from './types.js';
import { isLlmConfigured } from './lib/claudeClient.js';
import {
  buildDocSuggestions,
  optionalDocs,
  requiredDocs,
} from './documentGuidance.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const uploadRoot =
  process.env.UPLOAD_DIR || path.resolve(__dirname, '../uploads');

if (!fs.existsSync(uploadRoot)) {
  fs.mkdirSync(uploadRoot, { recursive: true });
}

const storage = multer.diskStorage({
  destination: (_req, _file, cb) => cb(null, uploadRoot),
  filename: (_req, file, cb) => {
    const safe = file.originalname.replace(/[^a-zA-Z0-9._-]/g, '_');
    cb(null, `${Date.now()}_${safe}`);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: 10 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    const ok =
      file.mimetype.startsWith('image/') ||
      file.mimetype === 'application/pdf' ||
      file.mimetype === 'text/plain';
    cb(ok ? null : new Error('Only PDF, images, and text files are allowed'), ok);
  },
});

export const apiRouter = Router();

apiRouter.get('/health', (_req, res) => {
  res.json({
    ok: true,
    groqConfigured: isLlmConfigured(),
    claudeConfigured: isLlmConfigured(), // alias — Anthropic replaced by Groq
    llmProvider: 'groq',
    app: 'LoanReady',
  });
});

apiRouter.get('/session', (_req, res) => {
  const session = getActiveSession();
  res.json(session);
});

apiRouter.post('/session/reset', (_req, res) => {
  const session = resetSession();
  res.json(session);
});

apiRouter.post('/demo/load', (_req, res) => {
  const session = loadDemoProfile();
  res.json(session);
});

apiRouter.get('/profile', (_req, res) => {
  const session = getActiveSession();
  res.json({
    profile: session.profile,
    requiredDocs: requiredDocs(session.profile?.loanType),
    optionalDocs: optionalDocs(session.profile?.loanType),
  });
});

apiRouter.post('/profile', (req, res) => {
  const body = req.body as Partial<CustomerProfile>;
  if (!body.loanType && !getActiveSession().profile) {
    res.status(400).json({ error: 'loanType is required for onboarding' });
    return;
  }
  const session = getActiveSession().profile
    ? mergeProfile(body)
    : updateProfile({
        name: body.name || '',
        loanType: body.loanType || 'personal',
        requestedAmount: Number(body.requestedAmount) || 0,
        monthlyIncome: Number(body.monthlyIncome) || 0,
        incomeType: body.incomeType || 'salaried',
        existingEMIs: Number(body.existingEMIs) || 0,
        creditScore: Number(body.creditScore) || 0,
        employmentTenureMonths: Number(body.employmentTenureMonths) || 0,
        coApplicant: body.coApplicant,
        interestRateEstimate: body.interestRateEstimate ?? 0.12,
        loanTenureMonths: body.loanTenureMonths ?? 36,
      });
  res.json({ profile: session.profile });
});

apiRouter.post('/documents/upload', upload.single('file'), async (req, res) => {
  try {
    if (!req.file) {
      res.status(400).json({ error: 'No file uploaded' });
      return;
    }
    const session = getActiveSession();
    const expectedType = req.body?.expectedType as DocumentType | undefined;
    const replaceId = req.body?.replaceId as string | undefined;
    const replaceType =
      req.body?.replaceType === 'true' || req.body?.replaceType === true;

    const result = await processUploadedDocument({
      filePath: req.file.path,
      originalName: req.file.originalname,
      mimeType: req.file.mimetype,
      profile: session.profile,
      expectedType: expectedType || undefined,
      replaceId: replaceId || undefined,
      replaceType: Boolean(replaceType),
    });
    const updated = getActiveSession();
    const suggestions = buildDocSuggestions(
      updated.profile,
      updated.documents
    );
    res.json({
      document: result.document,
      issues: result.issues,
      infoRequests: result.infoRequests,
      profile: updated.profile,
      documents: updated.documents,
      suggestions,
    });
  } catch (err) {
    console.error('Upload error:', err);
    res.status(500).json({
      error: (err as Error).message || 'Document processing failed',
    });
  }
});

apiRouter.get('/documents', (_req, res) => {
  const session = getActiveSession();
  const loan = session.profile?.loanType;
  res.json({
    documents: session.documents,
    requiredDocs: requiredDocs(loan),
    optionalDocs: optionalDocs(loan),
    suggestions: buildDocSuggestions(session.profile, session.documents),
    hints: DOC_UPLOAD_HINTS,
  });
});

apiRouter.delete('/documents/:id', (req, res) => {
  const session = deleteDocument(req.params.id);
  res.json({
    documents: session.documents,
    suggestions: buildDocSuggestions(session.profile, session.documents),
  });
});

apiRouter.post('/documents/clear', (_req, res) => {
  const session = clearDocuments();
  res.json({
    documents: session.documents,
    suggestions: buildDocSuggestions(session.profile, session.documents),
  });
});

apiRouter.get('/documents/suggestions', (_req, res) => {
  const session = getActiveSession();
  res.json({
    suggestions: buildDocSuggestions(session.profile, session.documents),
  });
});

apiRouter.post('/eligibility/evaluate', async (_req, res) => {
  try {
    const session = getActiveSession();
    if (!session.profile) {
      res.status(400).json({ error: 'No profile — complete onboarding first' });
      return;
    }
    const eligibility = await runEligibilityEvaluation(session.profile);
    setEligibility(eligibility);
    res.json({ eligibility, profile: session.profile });
  } catch (err) {
    console.error('Evaluate error:', err);
    res.status(500).json({ error: (err as Error).message });
  }
});

apiRouter.post('/eligibility/simulate', async (req, res) => {
  try {
    const session = getActiveSession();
    if (!session.profile) {
      res.status(400).json({ error: 'No profile — complete onboarding first' });
      return;
    }
    const change = req.body as ProposedChange;
    const simulated = await runSimulation(session.profile, change);
    const baseline =
      session.eligibility ||
      (await runEligibilityEvaluation(session.profile));
    res.json({
      baseline,
      simulated,
      proposedChange: change,
    });
  } catch (err) {
    console.error('Simulate error:', err);
    res.status(500).json({ error: (err as Error).message });
  }
});

apiRouter.post('/chat', async (req, res) => {
  try {
    const message = String(req.body?.message || '').trim();
    if (!message) {
      res.status(400).json({ error: 'message is required' });
      return;
    }
    const result = await handleChat(message);
    const session = getActiveSession();
    res.json({
      reply: result.message,
      simulationResult: result.simulationResult,
      chatHistory: session.chatHistory,
    });
  } catch (err) {
    console.error('Chat error:', err);
    res.status(500).json({ error: (err as Error).message });
  }
});

apiRouter.get('/chat/history', (_req, res) => {
  const session = getActiveSession();
  res.json({ chatHistory: session.chatHistory });
});
