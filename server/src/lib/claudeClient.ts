import Groq from 'groq-sdk';
import dotenv from 'dotenv';

dotenv.config();

/** Fast text model — override with GROQ_MODEL in .env */
const TEXT_MODEL =
  process.env.GROQ_MODEL || 'llama-3.3-70b-versatile';

/** Vision-capable model for scanned docs / images */
const VISION_MODEL =
  process.env.GROQ_VISION_MODEL || 'meta-llama/llama-4-scout-17b-16e-instruct';

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

  const response = await groq.chat.completions.create({
    model,
    temperature,
    max_tokens: maxTokens,
    ...(jsonMode ? { response_format: { type: 'json_object' as const } } : {}),
    messages: [
      { role: 'system', content: systemPrompt },
      ...messages.map((m) => ({
        role: m.role as 'user' | 'assistant' | 'system',
        content: m.content as string | LlmContentPart[],
      })),
    ],
  });

  const text = response.choices[0]?.message?.content;
  if (!text) {
    throw new Error('Groq returned no text content');
  }
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
