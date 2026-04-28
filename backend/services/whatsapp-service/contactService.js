/**
 * Contact Service - Gerencia buscas e operações com contatos do WhatsApp
 */

// Cache para evitar buscas pesadas frequentes
let contactsCache = {
    all: [],
    chats: [],
    lastUpdate: 0,
    isUpdating: false
};

const CACHE_TTL = 5 * 60 * 1000; // 5 minutos

/**
 * Normaliza string para comparação case-insensitive e sem espaços
 * @param {string} str - String a normalizar
 * @returns {string} String normalizada
 */
const normalizeString = (str) => {
    if (!str) return '';
    return str.toString()
        .toLowerCase()
        .normalize('NFD') // Decompõe caracteres acentuados (ex: 'ã' -> 'a' + '~')
        .replace(/[\u0300-\u036f]/g, '') // Remove os acentos
        .replace(/[^a-z0-9\s]/g, '') // Remove tudo que não é alfanumérico básico ou espaço
        .trim()
        .replace(/\s+/g, ' ');
};

/**
 * Calcula a similaridade entre duas strings (Levenshtein distance)
 * @param {string} str1 - Primeira string
 * @param {string} str2 - Segunda string
 * @returns {number} Score de 0 a 1 (1 = idêntico)
 */
const calculateSimilarity = (str1, str2) => {
    const s1 = normalizeString(str1);
    const s2 = normalizeString(str2);
    
    if (s1 === s2) return 1;
    
    // Prioridade altíssima para prefixos exatos
    if (s1.startsWith(s2)) return 0.95;
    
    // Contém a string (Inclusão simples) - Subimos para 0.85 para garantir que apareça
    if (s1.includes(s2) || s2.includes(s1)) return 0.85;
    
    // Fallback para Levenshtein
    const longer = s1.length > s2.length ? s1 : s2;
    const shorter = s1.length > s2.length ? s2 : s1;
    
    if (longer.length === 0) return 1;
    
    // Se a query for muito curta (1-2 chars) e não deu matching de prefixo/inclusão, ignorar fuzzy
    if (s2.length <= 2) return 0;

    const editDistance = getEditDistance(longer, shorter);
    const score = (longer.length - editDistance) / longer.length;
    
    // Log para ajuste fino (apenas se for razoavelmente parecido)
    if (score > 0.3) {
        console.log(`[WA Search] Similarity "${s1}" vs "${s2}": ${score.toFixed(2)}`);
    }
    
    return score;
};

/**
 * Calcula Levenshtein distance entre duas strings
 * @param {string} s1 - String 1
 * @param {string} s2 - String 2
 * @returns {number} Distância
 */
const getEditDistance = (s1, s2) => {
    const costs = [];
    for (let k = 0; k <= s1.length; k++) costs[k] = [k];
    for (let k = 0; k <= s2.length; k++) costs[0][k] = k;
    for (let i = 1; i <= s1.length; i++) {
        for (let j = 1; j <= s2.length; j++) {
            if (s1[i - 1] === s2[j - 1]) {
                costs[i][j] = costs[i - 1][j - 1];
            } else {
                costs[i][j] = 1 + Math.min(costs[i - 1][j], costs[i][j - 1], costs[i - 1][j - 1]);
            }
        }
    }
    return costs[s1.length][s2.length];
};

/**
 * Busca contatos por nome com suporte a busca fuzzy
 * @param {Object} client - Cliente WhatsApp
 * @param {string} searchName - Nome ou parte do nome para buscar
 * @param {Object} options - Opções de busca
 * @param {boolean} options.exactMatch - Se true, busca apenas matches exatos
 * @param {number} options.minSimilarity - Score mínimo de similaridade (0-1)
 * @param {number} options.limit - Número máximo de resultados
 * @returns {Promise<Array>} Array de contatos encontrados
 */
const searchContactsByName = async (client, searchName, options = {}) => {
    const {
        exactMatch = false,
        minSimilarity = 0.4,
        limit = 20
    } = options;

    if (!searchName || typeof searchName !== 'string') {
        throw new Error('Nome de busca inválido');
    }

    if (!client) {
        throw new Error('Cliente WhatsApp não fornecido');
    }

    try {
        if (typeof client.getContacts !== 'function') {
            throw new Error('Instância do cliente inválida ou não inicializada corretamente');
        }

        const now = Date.now();
        let allContacts = [];
        let allChats = [];

        // Verifica cache
        if (contactsCache.all.length > 0 && (now - contactsCache.lastUpdate < CACHE_TTL)) {
            allContacts = contactsCache.all;
            allChats = contactsCache.chats;
            console.log(`[WA ContactService] Usando cache (${allContacts.length} contatos).`);
        } else {
            // Se já estiver atualizando, usa o cache antigo se houver, ou espera
            if (contactsCache.isUpdating && contactsCache.all.length > 0) {
                allContacts = contactsCache.all;
                allChats = contactsCache.chats;
            } else {
                contactsCache.isUpdating = true;
                try {
                    // Busca em Contatos e em Chats com tratamento individual de erros
                    const contactsPromise = client.getContacts().catch(err => {
                        console.error('[WA ContactService] Erro ao buscar contatos:', err.message);
                        return [];
                    });
                    
                    const chatsPromise = client.getChats().catch(err => {
                        console.error('[WA ContactService] Erro ao buscar chats:', err.message);
                        return [];
                    });

                    [allContacts, allChats] = await Promise.all([contactsPromise, chatsPromise]);
                    
                    // Atualiza cache apenas se encontramos contatos (evita cachear lista vazia em inicialização)
                    if (allContacts.length > 0 || allChats.length > 0) {
                        contactsCache.all = allContacts;
                        contactsCache.chats = allChats;
                        contactsCache.lastUpdate = now;
                        console.log(`[WA ContactService] Cache atualizado: ${allContacts.length} contatos, ${allChats.length} chats.`);
                    } else {
                        console.log('[WA ContactService] Nenhum contato encontrado. Cache não atualizado.');
                    }
                } finally {
                    contactsCache.isUpdating = false;
                }
            }
        }
        
        console.log(`[WA ContactService] Pesquisando "${searchName}" em ${allContacts.length} contatos e ${allChats.length} chats.`);

        // Combina e remove duplicatas baseadas no ID
        const combinedMap = new Map();
        
        // Processa Contatos
        allContacts.forEach(c => {
            if (c && c.id && c.id._serialized) {
                combinedMap.set(c.id._serialized, {
                    ...c,
                    displayName: c.name || c.pushname || c.id.user,
                    source: 'contact'
                });
            }
        });
        
        // Processa Chats (contatos recentes que podem não estar salvos)
        allChats.forEach(c => {
            if (c && c.id && c.id._serialized && !combinedMap.has(c.id._serialized)) {
                combinedMap.set(c.id._serialized, {
                    ...c,
                    displayName: c.name || c.id.user,
                    source: 'chat'
                });
            }
        });

        const results = Array.from(combinedMap.values())
            .map(contact => {
                try {
                    const similarity = calculateSimilarity(contact.displayName, searchName);
                    return {
                        id: contact.id._serialized,
                        name: contact.displayName,
                        number: contact.id.user,
                        isBusiness: !!contact.isBusiness,
                        isMyContact: !!contact.isMyContact,
                        source: contact.source,
                        similarity
                    };
                } catch (e) { return null; }
            })
            .filter(contact => {
                if (!contact || !contact.id) return false;
                if (exactMatch) {
                    return normalizeString(contact.name) === normalizeString(searchName);
                }
                return contact.similarity >= minSimilarity;
            })
            .sort((a, b) => b.similarity - a.similarity)
            .slice(0, limit)
            .map(contact => ({
                ...contact,
                similarity: Math.round(contact.similarity * 100)
            }));

        return results;
    } catch (error) {
        throw new Error(`Erro ao buscar contatos: ${error.message}`);
    }
};

/**
 * Busca um contato único pelo nome exato
 * @param {Object} client - Cliente WhatsApp
 * @param {string} name - Nome do contato
 * @returns {Promise<Object|null>} Contato encontrado ou null
 */
const findContactByExactName = async (client, name) => {
    const results = await searchContactsByName(client, name, {
        exactMatch: true,
        limit: 1
    });
    return results.length > 0 ? results[0] : null;
};

/**
 * Busca contatos pelo número de telefone
 * @param {Object} client - Cliente WhatsApp
 * @param {string} number - Número do telefone
 * @returns {Promise<Object|null>} Contato encontrado ou null
 */
const findContactByNumber = async (client, number) => {
    try {
        const formattedNumber = number.includes('@c.us') ? number : `${number}@c.us`;
        const contact = await client.getContactById(formattedNumber);
        
        if (!contact || !contact.id) return null;

        return {
            id: contact.id._serialized,
            name: contact.name || contact.id.user,
            number: contact.id.user,
            isBusiness: contact.isBusiness,
            isMyContact: contact.isMyContact,
            similarity: 100
        };
    } catch (error) {
        return null;
    }
};

/**
 * Lista todos os contatos
 * @param {Object} client - Cliente WhatsApp
 * @param {Object} options - Opções de listagem
 * @param {number} options.limit - Número máximo de contatos
 * @param {boolean} options.onlyMyContacts - Se true, retorna apenas os contatos salvos
 * @returns {Promise<Array>} Array de contatos
 */
const listAllContacts = async (client, options = {}) => {
    const {
        limit = 5000,
        onlyMyContacts = false
    } = options;

    try {
        console.log(`[WA ContactService] Listando todos os contatos (Somente agenda: ${onlyMyContacts})...`);
        
        // Busca contatos e chats em paralelo para maior abrangência
        const [contacts, chats] = await Promise.all([
            client.getContacts().catch(() => []),
            client.getChats().catch(() => [])
        ]);
        
        const combinedMap = new Map();
        
        // Processa Contatos da Agenda
        contacts.forEach(c => {
            if (c && c.id && c.id._serialized) {
                if (onlyMyContacts && !c.isMyContact) return;
                combinedMap.set(c.id._serialized, {
                    id: c.id._serialized,
                    name: c.name || c.pushname || c.id.user,
                    number: c.id.user,
                    isBusiness: !!c.isBusiness,
                    isMyContact: !!c.isMyContact
                });
            }
        });
        
        // Adiciona Chats (contatos recentes que podem não estar na agenda)
        if (!onlyMyContacts) {
            chats.forEach(c => {
                if (c && c.id && c.id._serialized && !c.isGroup && !combinedMap.has(c.id._serialized)) {
                    combinedMap.set(c.id._serialized, {
                        id: c.id._serialized,
                        name: c.name || c.id.user,
                        number: c.id.user,
                        isBusiness: !!c.isBusiness,
                        isMyContact: false
                    });
                }
            });
        }
        
        const results = Array.from(combinedMap.values()).slice(0, limit);
        console.log(`[WA ContactService] Total de contatos únicos encontrados: ${results.length}`);
        return results;
    } catch (error) {
        throw new Error(`Erro ao listar contatos: ${error.message}`);
    }
};

/**
 * Busca chats por nome com suporte a busca fuzzy
 * @param {Object} client - Cliente WhatsApp
 * @param {string} searchName - Nome ou parte do nome para buscar
 * @param {Object} options - Opções de busca
 * @param {number} options.minSimilarity - Score mínimo de similaridade (0-1)
 * @param {number} options.limit - Número máximo de resultados
 * @returns {Promise<Array>} Array de chats encontrados
 */
const searchChatsByName = async (client, searchName, options = {}) => {
    const {
        minSimilarity = 0.5,
        limit = 10
    } = options;

    if (!searchName || typeof searchName !== 'string') {
        throw new Error('Nome de busca inválido');
    }

    try {
        const allChats = await client.getChats();
        
        const results = allChats
            .map(chat => ({
                ...chat,
                similarity: calculateSimilarity(chat.name || chat.id.user, searchName),
                displayName: chat.name || chat.id.user
            }))
            .filter(chat => chat.similarity >= minSimilarity)
            .sort((a, b) => b.similarity - a.similarity)
            .slice(0, limit)
            .map(chat => ({
                id: chat.id._serialized,
                name: chat.displayName,
                unreadCount: chat.unreadCount,
                timestamp: chat.timestamp,
                similarity: Math.round(chat.similarity * 100)
            }));

        return results;
    } catch (error) {
        throw new Error(`Erro ao buscar chats: ${error.message}`);
    }
};

/**
 * Obtém a URL da foto de perfil de um contato
 * @param {Object} client - Cliente WhatsApp
 * @param {string} contactId - ID do contato ou número
 * @returns {Promise<string|null>} URL da foto ou null
 */
const getProfilePic = async (client, contactId) => {
    try {
        let id = contactId.includes('@c.us') ? contactId : `${contactId}@c.us`;
        let url = await client.getProfilePicUrl(id);
        
        // Se falhou e o número parece ser brasileiro sem o 55
        if (!url && !contactId.startsWith('55') && contactId.replace(/\D/g, '').length >= 10) {
            const altId = `55${contactId.replace(/\D/g, '')}@c.us`;
            url = await client.getProfilePicUrl(altId);
        }
        
        return url;
    } catch (error) {
        return null;
    }
};

/**
 * Invalidates the contact cache (called on client restart).
 */
const _invalidateCache = () => {
    contactsCache.all = [];
    contactsCache.chats = [];
    contactsCache.lastUpdate = 0;
    contactsCache.isUpdating = false;
    console.log('[WA ContactService] 🧹 Cache invalidado por restart do cliente.');
};

module.exports = {
    searchContactsByName,
    findContactByExactName,
    findContactByNumber,
    listAllContacts,
    searchChatsByName,
    getProfilePic,
    normalizeString,
    calculateSimilarity,
    _invalidateCache
};
