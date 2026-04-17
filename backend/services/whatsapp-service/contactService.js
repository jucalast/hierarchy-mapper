/**
 * Contact Service - Gerencia buscas e operações com contatos do WhatsApp
 */

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
    if (s1.includes(s2) || s2.includes(s1)) return 0.9;
    
    const longer = s1.length > s2.length ? s1 : s2;
    const shorter = s1.length > s2.length ? s2 : s1;
    
    if (longer.length === 0) return 1;
    
    const editDistance = getEditDistance(longer, shorter);
    return (longer.length - editDistance) / longer.length;
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
        minSimilarity = 0.6,
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

        // Busca em Contatos e em Chats em paralelo para máxima abrangência
        const [allContacts, allChats] = await Promise.all([
            client.getContacts(),
            client.getChats()
        ]);
        
        // Combina e remove duplicatas baseadas no ID
        const combinedMap = new Map();
        
        // Processa Contatos
        allContacts.forEach(c => {
            if (c && c.id && c.id._serialized) {
                combinedMap.set(c.id._serialized, {
                    ...c,
                    displayName: c.name || c.id.user,
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
        limit = 100,
        onlyMyContacts = true
    } = options;

    try {
        let contacts = await client.getContacts();
        
        let filtered = contacts.filter(c => c && c.id && c.id._serialized);
        
        if (onlyMyContacts) {
            filtered = filtered.filter(c => c.isMyContact);
        }
        
        return filtered
            .slice(0, limit)
            .map(contact => {
                try {
                    if (!contact || !contact.id || !contact.id._serialized) return null;
                    return {
                        id: contact.id._serialized,
                        name: contact.name || contact.displayName || (contact.id ? contact.id.user : "Contato"),
                        number: contact.id ? contact.id.user : "",
                        isBusiness: !!contact.isBusiness,
                        isMyContact: !!contact.isMyContact
                    };
                } catch (e) {
                    return null;
                }
            })
            .filter(c => c !== null);
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

module.exports = {
    searchContactsByName,
    findContactByExactName,
    findContactByNumber,
    listAllContacts,
    searchChatsByName,
    getProfilePic,
    normalizeString,
    calculateSimilarity
};
