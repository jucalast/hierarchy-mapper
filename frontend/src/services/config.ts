/**
 * Configuração centralizada de URLs e requisições AJAX
 * Suporta reconexão automática e timeout
 */

// URL base do backend - configurável via variável de ambiente
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
export const API_V1_URL = `${API_BASE_URL}/api/v1`;

/**
 * Constrói URL do proxy de imagens do backend (evita CORS/hotlink).
 * Retorna a URL intacta se já for local ou não for http.
 */
export function buildProxyImageUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  if (typeof url !== 'string') return undefined;
  if (!url.startsWith('http')) return url;
  // Já está proxificada ou já aponta para o próprio backend
  if (url.includes('/proxy/image') || url.includes(API_BASE_URL)) return url;
  return `${API_V1_URL}/proxy/image?url=${encodeURIComponent(url)}`;
}

// Configurações de retry
export const RETRY_CONFIG = {
  maxRetries: 3,
  initialDelayMs: 500,
  maxDelayMs: 5000,
  backoffMultiplier: 2,
} as const;

// Timeouts
export const TIMEOUTS = {
  short: 5000,    // Requisições rápidas
  medium: 15000,  // Requisições normais
  long: 60000,    // Uploads, operações pesadas
} as const;

/**
 * Aguarda o backend estar pronto (health check)
 */
export async function waitForBackend(timeoutMs = 10000): Promise<boolean> {
  const startTime = Date.now();
  
  while (Date.now() - startTime < timeoutMs) {
    try {
      const response = await fetch(`${API_BASE_URL}/docs`, {
        method: 'HEAD',
        mode: 'no-cors', // Para evitar CORS em health check simples
      });
      if (response.ok || response.status === 0) {
        console.log('✅ Backend está pronto');
        return true;
      }
    } catch (error) {
      // Backend não respondeu, aguarda e tenta novamente
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
  
  console.warn('⚠️ Backend não respondeu no timeout');
  return false;
}

/**
 * Fetch com retry automático e timeout
 */
export async function fetchWithRetry(
  url: string,
  options: RequestInit & { timeout?: number } = {},
  retries: number = RETRY_CONFIG.maxRetries,
  delayMs: number = RETRY_CONFIG.initialDelayMs
): Promise<Response> {
  const timeout = options.timeout || TIMEOUTS.medium;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    // Se sucesso, retorna
    if (response.ok) {
      return response;
    }

    // Se erro 5xx ou timeout, tenta novamente
    if ((response.status >= 500 || response.status === 0) && retries > 0) {
      console.warn(`❌ Erro ${response.status} em ${url}, tentando novamente em ${delayMs}ms...`);
      await new Promise(resolve => setTimeout(resolve, delayMs));
      
      const nextDelay = Math.min(
        delayMs * RETRY_CONFIG.backoffMultiplier,
        RETRY_CONFIG.maxDelayMs
      );
      
      return fetchWithRetry(url, options, retries - 1, nextDelay);
    }

    return response;
  } catch (error: any) {
    clearTimeout(timeoutId);

    // Se foi AbortError (timeout), tenta novamente
    if (error.name === 'AbortError' && retries > 0) {
      console.warn(`⏱️ Timeout em ${url}, tentando novamente em ${delayMs}ms...`);
      await new Promise(resolve => setTimeout(resolve, delayMs));
      
      const nextDelay = Math.min(
        delayMs * RETRY_CONFIG.backoffMultiplier,
        RETRY_CONFIG.maxDelayMs
      );
      
      return fetchWithRetry(url, options, retries - 1, nextDelay);
    }

    throw error;
  }
}

/**
 * Helper para requisições GET com retry
 */
export async function apiGet<T = any>(
  endpoint: string,
  options: RequestInit & { timeout?: number } = {}
): Promise<T> {
  const url = endpoint.startsWith('http') 
    ? endpoint 
    : `${API_V1_URL}${endpoint}`;
  
  const response = await fetchWithRetry(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Helper para requisições POST com retry
 */
export async function apiPost<T = any>(
  endpoint: string,
  body?: any,
  options: RequestInit & { timeout?: number } = {}
): Promise<T> {
  const url = endpoint.startsWith('http') 
    ? endpoint 
    : `${API_V1_URL}${endpoint}`;
  
  const response = await fetchWithRetry(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    body: body ? JSON.stringify(body) : undefined,
    ...options,
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

export default {
  API_BASE_URL,
  API_V1_URL,
  RETRY_CONFIG,
  TIMEOUTS,
  waitForBackend,
  fetchWithRetry,
  apiGet,
  apiPost,
};
