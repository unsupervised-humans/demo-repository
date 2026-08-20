# LoanReady

AI-powered loan pre-approval assistant that helps customers improve their loan application **before** submitting to a bank.

## Quick start

```bash
npm run install:all
cp server/.env.example server/.env
# Set GROQ_API_KEY=gsk_... from https://console.groq.com/keys
npm run dev
```

- Frontend: http://localhost:5173
- Backend: http://localhost:3001

## LLM

Uses **Groq** (free tier). Shared wrapper: `server/src/lib/claudeClient.ts`  
Default: `llama-3.3-70b-versatile` + vision model for scanned docs.

## Disclaimer

Estimate only — not a loan approval guarantee; not affiliated with any lender.
