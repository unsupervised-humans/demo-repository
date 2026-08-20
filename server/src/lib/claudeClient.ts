import Groq from 'groq-sdk';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

dotenv.config();

const CACHE_FILE = path.resolve(process.cwd(), 'data/llm_cache.json');

function ensureCacheDir(): void {
  const dir = path.dirname(CACHE_FILE);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function readCache(): Record<string, string> {
  try {
    ensureCacheDir();
    if (fs.existsSync(CACHE_FILE)) {
      return JSON.parse(fs.readFileSync(CACHE_FILE, 'utf-8'));
    }
  } catch {
    // ignore read errors
  }
  return {};
}

function writeCache(cache: Record<string, string>): void {
  try {
    ensureCacheDir();
    fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2), 'utf-8');
  } catch {
    // ignore write errors
  }
}

function getCacheKey(options: LlmCallOptions): string {
  const hash = crypto.createHash('sha256');
  const content = JSON.stringify({
    model: options.model || 'openai/gpt-oss-20b',
    system: options.system,
    jsonMode: options.jsonMode ?? false,
    messages: options.messages.map((m) => ({
      role: m.role,
      content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
    })),
  });
  hash.update(content);
  return hash.digest('hex');
}

/** Fast text model — override with GROQ_MODEL in .env */
const TEXT_MODEL =
  process.env.GROQ_MODEL || 'openai/gpt-oss-20b';

/** Vision-capable model for scanned docs / images */
const VISION_MODEL =
  process.env.GROQ_VISION_MODEL || 'qwen/qwen3.6-27b';

let client: Groq | null = null;

function getClient(): Groq {
  if (!client) {
    const apiKey = process.env.GROQ_API_KEY;
    if (!apiKey || apiKey === 'your_api_key_here') {
      throw new Error(
        'GROQ_API_KEY is not set. Get a free key at https://console.groq.com/keys and put it in server/.env'
      );
    }
    client = new Groq({ apiKey });
  }
  return client;
}

export type LlmContentPart =
  | { type: 'text'; text: string }
  | {
      type: 'image_url';
      image_url: { url: string };
    };

export interface LlmMessage {
  role: 'user' | 'assistant' | 'system';
  content: string | LlmContentPart[];
}

export interface LlmCallOptions {
  system: string;
  messages: LlmMessage[];
  maxTokens?: number;
  temperature?: number;
  /** When true, ask the model to return strict JSON only */
  jsonMode?: boolean;
  model?: string;
}

/**
 * Single shared Groq API wrapper used by all three agents.
 * Agents differ only by system prompt — never duplicate API call logic.
 */
export async function callLlm(options: LlmCallOptions): Promise<string> {
  const cacheKey = getCacheKey(options);
  const cache = readCache();
  if (cache[cacheKey]) {
    console.log(`[LLM Cache Hit] Using cached response for model ${options.model || TEXT_MODEL}`);
    return cache[cacheKey];
  }

  const groq = getClient();
  const {
    system,
    messages,
    maxTokens = 4096,
    temperature = 0.2,
    jsonMode = false,
    model = TEXT_MODEL,
  } = options;

  const systemPrompt = jsonMode
    ? `${system}\n\nIMPORTANT: Respond with ONLY valid JSON. No markdown fences, no commentary, no preamble.`
    : system;

  let retries = 5;
  let delay = 2000;
  let response;

  while (retries >= 0) {
    try {
      response = await groq.chat.completions.create({
        model,
        temperature,
        max_tokens: maxTokens,
        ...(jsonMode ? { response_format: { type: 'json_object' as const } } : {}),
        messages: [
          { role: 'system', content: systemPrompt },
          ...messages.map((m) => ({
            role: m.role as any,
            content: m.content as any,
          })),
        ],
      });
      break; // Success
    } catch (err: any) {
      const isRateLimit = err.status === 429 || err.statusCode === 429 || String(err).includes('429') || String(err.message).includes('rate limit');
      if (isRateLimit && retries > 0) {
        console.warn(`[Groq Rate Limit] Received 429. Retrying in ${delay}ms... (Retries left: ${retries})`);
        await new Promise((resolve) => setTimeout(resolve, delay));
        retries--;
        delay *= 2;
      } else {
        throw err;
      }
    }
  }

  if (!response) {
    throw new Error('Groq call failed after all retries');
  }

  const text = response.choices[0]?.message?.content;
  if (!text) {
    throw new Error('Groq returned no text content');
  }

  // Update and save cache
  cache[cacheKey] = text;
  writeCache(cache);

  return text;
}

/** @deprecated use callLlm — kept so older agent imports keep working */
export const callClaude = callLlm;

/**
 * Call Groq vision model with an image (scanned docs / photos).
 */
export async function callLlmWithImage(options: {
  system: string;
  prompt: string;
  imageBase64: string;
  mediaType: 'image/jpeg' | 'image/png' | 'image/gif' | 'image/webp';
  jsonMode?: boolean;
}): Promise<string> {
  const dataUrl = `data:${options.mediaType};base64,${options.imageBase64}`;
  return callLlm({
    system: options.system,
    model: VISION_MODEL,
    jsonMode: options.jsonMode ?? true,
    messages: [
      {
        role: 'user',
        content: [
          { type: 'text', text: options.prompt },
          { type: 'image_url', image_url: { url: dataUrl } },
        ],
      },
    ],
  });
}

export const callClaudeWithImage = callLlmWithImage;

/**
 * Parse JSON from LLM response, stripping optional markdown fences.
 */
export function parseLlmJson<T>(raw: string): T {
  let cleaned = raw.trim();
  const fenceMatch = cleaned.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fenceMatch) {
    cleaned = fenceMatch[1].trim();
  }
  try {
    return JSON.parse(cleaned) as T;
  } catch (err) {
    throw new Error(
      `Failed to parse LLM JSON response: ${(err as Error).message}\nRaw: ${raw.slice(0, 500)}`
    );
  }
}

export const parseClaudeJson = parseLlmJson;

export function isLlmConfigured(): boolean {
  const key = process.env.GROQ_API_KEY;
  return Boolean(key && key !== 'your_api_key_here' && key.trim().length > 0);
}

export const isClaudeConfigured = isLlmConfigured;

export { TEXT_MODEL as MODEL, VISION_MODEL };
