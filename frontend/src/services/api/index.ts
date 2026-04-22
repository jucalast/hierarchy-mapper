/**
 * Surface única do client HTTP — agrupa por domínio.
 * Use:
 *   import { ai, organizations, jobs, hierarchy, communication, health } from '@/services/api';
 */
export { api, ApiError } from './client';
export type { RequestOptions } from './client';

import * as ai from './ai';
import * as organizations from './organizations';
import * as hierarchy from './hierarchy';
import * as jobs from './jobs';
import * as communication from './communication';
import * as health from './health';

export { ai, organizations, hierarchy, jobs, communication, health };
