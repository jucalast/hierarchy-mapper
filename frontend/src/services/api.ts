/**
 * Compatibilidade — re-exporta tipos e a surface por domínio da nova locação canônica.
 * Componentes legados continuam funcionando com `import { HierarchyEmployee } from '@/services/api'`,
 * enquanto novo código pode usar diretamente os namespaces de domínio.
 *
 * Uso moderno:
 *   import { HierarchyEmployee, HierarchyResponse } from '@/types';
 *   import { ai, organizations, hierarchy, jobs, communication, health } from '@/services/api';
 */
export type { HierarchyEmployee, HierarchyResponse } from '@/types';

// Surface domain-namespaced re-exportada a partir de /services/api/index.ts
export {
  api,
  ApiError,
  ai,
  organizations,
  hierarchy,
  jobs,
  communication,
  health,
} from './api/index';
export type { RequestOptions } from './api/index';
