import { Router } from 'express';
import { getActiveSession } from '../store.js';
import { isLlmConfigured, MODEL } from '../lib/claudeClient.js';
import {
  digilockerConfigured,
  panApiConfigured,
  runLocalKycBundle,
  checkAadhaarLocal,
  checkPanLocal,
  verifyAadhaarViaGovernment,
  verifyPanViaGovernment,
} from '../kycVerification.js';

export const integrationsRouter = Router();

/** Where to plug API keys + current connection status */
integrationsRouter.get('/status', (_req, res) => {
  res.json({
    groq: {
      configured: isLlmConfigured(),
      model: MODEL,
      envVar: 'GROQ_API_KEY',
      setup:
        'Put your free key in server/.env as GROQ_API_KEY=gsk_... then restart the server. Get one at https://console.groq.com/keys',
      consoleUrl: 'https://console.groq.com/keys',
    },
    // backward-compatible alias for older UI
    claude: {
      configured: isLlmConfigured(),
      model: MODEL,
      envVar: 'GROQ_API_KEY',
      setup:
        'Anthropic was replaced with Groq. Set GROQ_API_KEY in server/.env (https://console.groq.com/keys).',
      consoleUrl: 'https://console.groq.com/keys',
    },
    digilocker: {
      configured: digilockerConfigured(),
      envVars: ['DIGILOCKER_CLIENT_ID', 'DIGILOCKER_CLIENT_SECRET'],
      setup:
        'Requires DigiLocker API partnership. Used for consent-based e-Aadhaar — not available on free/hackathon keys.',
      docsUrl: 'https://www.digitallocker.gov.in/',
    },
    panVerify: {
      configured: panApiConfigured(),
      envVars: ['PAN_VERIFY_API_KEY', 'PAN_VERIFY_API_URL'],
      setup:
        'Requires licensed NSDL/UTIITSL (or similar) PAN verification. LoanReady only does local format checks until this is set.',
    },
    honesty:
      'LoanReady does NOT verify Aadhaar/PAN with the government unless you connect licensed APIs. Local checks are format + name consistency only. LLM features use Groq (free tier).',
  });
});

integrationsRouter.get('/kyc', (_req, res) => {
  const session = getActiveSession();
  const results = runLocalKycBundle(session.profile, session.documents);
  res.json({
    results,
    disclaimer:
      'Local format/consistency only — not UIDAI or Income Tax Department verification.',
  });
});

integrationsRouter.post('/kyc/check', async (req, res) => {
  const session = getActiveSession();
  const { aadhaar, pan } = req.body || {};
  const aadhaarDoc = session.documents.find((d) => d.type === 'aadhaar');
  const panDoc = session.documents.find((d) => d.type === 'pan');

  const aadhaarLocal = checkAadhaarLocal(
    aadhaar,
    session.profile,
    aadhaarDoc
  );
  const panLocal = checkPanLocal(pan, session.profile, panDoc);

  const govAadhaar = aadhaar
    ? await verifyAadhaarViaGovernment(String(aadhaar))
    : null;
  const govPan = pan ? await verifyPanViaGovernment(String(pan)) : null;

  res.json({
    aadhaar: aadhaarLocal,
    pan: panLocal,
    governmentAttempts: {
      aadhaar: govAadhaar,
      pan: govPan,
    },
    disclaimer:
      'Government results are null unless DigiLocker/PAN API env vars are configured.',
  });
});
