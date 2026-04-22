/**
 * Cliente HTTP com retry, timeout, parsing de erro padronizado.
 * Centraliza headers, base URL e correlation_id (X-Request-ID).
 */
import { API_V1_URL, RETRY_CONFIG, TIMEOUTS, fetchWithRetry } from '../config';
import type { ApiErrorBody } from '@/types';

export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string | null;
  details?: unknown;
  constructor(
    status: number,
    code: string,
    message: string,
    requestId?: string | null,
    details?: unknown,
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

function genRequestId(): string {
  // Não exigimos UUID v4 cripto — só correlação client→server
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `cli-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`;
}

function resolveUrl(endpoint: string): string {
  if (endpoint.startsWith('http://') || endpoint.startsWith('https://')) return endpoint;
  if (endpoint.startsWith('/api/')) {
    // Já é caminho absoluto — concatena com origin do API_V1_URL
    const origin = API_V1_URL.replace(/\/api\/v1$/, '');
    return `${origin}${endpoint}`;
  }
  return `${API_V1_URL}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | { detail?: string } | null = null;
  try {
    body = await response.json();
  } catch {
    /* ignore */
  }
  const reqId = response.headers.get('X-Request-ID');

  if (body && (body as ApiErrorBody).error) {
    const err = (body as ApiErrorBody).error;
    return new ApiError(
      response.status,
      err.code || `http_${response.status}`,
      err.message || response.statusText,
      err.request_id ?? reqId,
      err.details,
    );
  }
  const detail = (body as { detail?: string } | null)?.detail;
  return new ApiError(
    response.status,
    `http_${response.status}`,
    detail || response.statusText || 'Request failed',
    reqId,
  );
}

export interface RequestOptions {
  timeout?: number;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  retry?: boolean | number;
}

async function request<T>(
  method: string,
  endpoint: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const url = resolveUrl(endpoint);
  const requestId = genRequestId();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Request-ID': requestId,
    ...(options.headers || {}),
  };

  const init: RequestInit & { timeout?: number } = {
    method,
    headers,
    body: body !== undefined && body !== null ? JSON.stringify(body) : undefined,
    signal: options.signal,
    timeout: options.timeout || TIMEOUTS.medium,
  };

  const retries =
    options.retry === false ? 0 :
    typeof options.retry === 'number' ? options.retry :
    RETRY_CONFIG.maxRetries;

  const response = await fetchWithRetry(url, init, retries);

  if (!response.ok) {
    throw await parseError(response);
  }

  // 204 → null
  if (response.status === 204) return null as T;
  // body vazio
  const text = await response.text();
  if (!text) return null as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return text as unknown as T;
  }
}

export const api = {
  get: <T = unknown>(endpoint: string, options?: RequestOptions) =>
    request<T>('GET', endpoint, undefined, options),
  post: <T = unknown>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    request<T>('POST', endpoint, body, options),
  put: <T = unknown>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    request<T>('PUT', endpoint, body, options),
  patch: <T = unknown>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    request<T>('PATCH', endpoint, body, options),
  delete: <T = unknown>(endpoint: string, options?: RequestOptions) =>
    request<T>('DELETE', endpoint, undefined, options),
};
