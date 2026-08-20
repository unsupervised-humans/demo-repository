import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';
import { apiRouter } from './routes.js';
import { integrationsRouter } from './routes/integrations.js';

dotenv.config();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = Number(process.env.PORT) || 3001;

app.use(cors());
app.use(express.json({ limit: '2mb' }));
app.use('/uploads', express.static(path.resolve(__dirname, '../uploads')));
app.use('/api', apiRouter);
app.use('/api/integrations', integrationsRouter);

app.use(
  (
    err: Error,
    _req: express.Request,
    res: express.Response,
    _next: express.NextFunction
  ) => {
    console.error(err);
    res.status(500).json({ error: err.message || 'Internal server error' });
  }
);

app.listen(PORT, () => {
  console.log(`LoanReady API running on http://localhost:${PORT}`);
  console.log(
    `Groq API: ${process.env.GROQ_API_KEY && process.env.GROQ_API_KEY !== 'your_api_key_here' ? 'configured' : 'NOT configured (offline/mock mode)'}`
  );
});
