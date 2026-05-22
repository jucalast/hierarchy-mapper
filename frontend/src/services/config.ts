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
// maxRetries=2: apenas 2 tentativas extras (total 3 requests) — evita 60s+ de espera
// antes de exibir erro ao usuário. Retries cobrem falhas transitórias de rede.
export const RETRY_CONFIG = {
  maxRetries: 2,
  initialDelayMs: 500,
  maxDelayMs: 2000,
  backoffMultiplier: 2,
} as const;

// Timeouts
export const TIMEOUTS = {
  short: 8000,
  medium: 20000,
  long: 60000,
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

  // Se o sinal externo já estiver abortado, lança o erro imediatamente
  if (options.signal?.aborted) {
    throw options.signal.reason || new DOMException('The user aborted a request.', 'AbortError');
  }

  const controller = new AbortController();

  // Vincula o sinal externo ao controller interno para abortar imediatamente se o chamador cancelar
  let externalAbortListener: (() => void) | null = null;
  if (options.signal) {
    externalAbortListener = () => {
      controller.abort(options.signal?.reason || new DOMException('The user aborted a request.', 'AbortError'));
    };
    options.signal.addEventListener('abort', externalAbortListener);
  }

  // Controle de timeout interno
  let isTimeout = false;
  const timeoutId = setTimeout(() => {
    isTimeout = true;
    controller.abort(new DOMException('Request timeout', 'AbortError'));
  }, timeout);

  // Tenta recuperar o token JWT do localStorage se no ambiente do browser
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const authHeaders: Record<string, string> = {};
  if (token) {
    authHeaders['Authorization'] = `Bearer ${token}`;
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        ...authHeaders,
        ...options.headers,
      },
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    if (externalAbortListener && options.signal) {
      options.signal.removeEventListener('abort', externalAbortListener);
    }

    // Se sucesso, retorna
    if (response.ok) {
      return response;
    }

    // Se erro 5xx ou status 0 (rede/cors) e temos retries, tenta novamente
    if ((response.status >= 500 || response.status === 0) && retries > 0) {
      if (options.signal?.aborted) {
        throw options.signal.reason || new DOMException('The user aborted a request.', 'AbortError');
      }

      console.warn(`❌ Erro ${response.status} em ${url}, tentando novamente em ${delayMs}ms...`);
      await new Promise<void>((resolve, reject) => {
        const sleepTimeout = setTimeout(resolve, delayMs);
        if (options.signal) {
          options.signal.addEventListener('abort', () => {
            clearTimeout(sleepTimeout);
            reject(options.signal?.reason || new DOMException('The user aborted a request.', 'AbortError'));
          }, { once: true });
        }
      });
      
      const nextDelay = Math.min(
        delayMs * RETRY_CONFIG.backoffMultiplier,
        RETRY_CONFIG.maxDelayMs
      );
      
      return fetchWithRetry(url, options, retries - 1, nextDelay);
    }

    return response;
  } catch (error: any) {
    clearTimeout(timeoutId);
    if (externalAbortListener && options.signal) {
      options.signal.removeEventListener('abort', externalAbortListener);
    }

    // Se o sinal externo foi abortado, relança o erro imediatamente sem tentar novamente
    if (options.signal?.aborted) {
      throw error;
    }

    // Se foi AbortError causado por timeout interno, tenta novamente
    if (isTimeout && retries > 0) {
      console.warn(`⏱️ Timeout em ${url}, tentando novamente em ${delayMs}ms...`);
      await new Promise<void>((resolve, reject) => {
        const sleepTimeout = setTimeout(resolve, delayMs);
        if (options.signal) {
          options.signal.addEventListener('abort', () => {
            clearTimeout(sleepTimeout);
            reject(options.signal?.reason || new DOMException('The user aborted a request.', 'AbortError'));
          }, { once: true });
        }
      });
      
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
