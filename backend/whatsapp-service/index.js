const express = require('express');
const cors = require('cors');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const contactService = require('./contactService');

const app = express();
app.use(cors());
app.use(express.json());

// Anti-ban configurations for whatsapp-web.js
// - Usage of existing sessions (LocalAuth) to avoid multiple logins.
// - Chromium arguments to run in stable mode.

// Limpeza manual do lockfile para evitar erro EBUSY em crashes
const fs = require('fs');
const path = require('path');
const lockfilePath = path.join(__dirname, '.wwebjs_auth', 'session', 'lockfile');
const sessionPath = path.join(__dirname, '.wwebjs_auth', 'session');

if (fs.existsSync(lockfilePath)) {
    try {
        console.log('[WA Service] 🧹 Removendo lockfile órfão para liberar a sessão...');
        fs.unlinkSync(lockfilePath);
    } catch (e) {
        console.warn('[WA Service] ⚠️ Não foi possível remover o lockfile (pode estar em uso por outro processo):', e.message);
    }
}

const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        headless: false, // Abrir janela visível para depuração
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--disable-gpu',
            '--disable-extensions',
            '--disable-features=IsolateOrigins,site-per-process',
            '--window-size=1280,720',
            '--disable-web-security',
            '--no-default-browser-check',
            '--disable-software-rasterizer',
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        ],
        timeout: 90000 // Aumentar timeout para 90s
    }
});

// Contador de falhas fatais para auto-restart
let fatalErrorCount = 0;
const MAX_FATAL_ERRORS = 3;
let isRestarting = false;

/**
 * Detects if an error is a fatal Puppeteer/Chrome frame error that requires restart.
 * Covers: detached Frame, Execution context destroyed, Protocol error, 't' crash.
 */
const isFatalPuppeteerError = (error) => {
    if (!error) return false;
    const msg = typeof error === 'string' ? error : (error.message || '');
    return (
        msg === 't' ||
        msg.includes('detached Frame') ||
        msg.includes('Execution context was destroyed') ||
        msg.includes('Session closed') ||
        msg.includes('Protocol error') ||
        msg.includes('Target closed') ||
        msg.includes('frame was detached') ||
        msg.includes('Cannot find context') ||
        msg.includes('Navigating frame was detached')
    );
};

/**
 * Increments the fatal error counter and triggers restart if threshold is reached.
 * Returns true if a restart was triggered.
 */
const trackFatalError = (error) => {
    if (!isFatalPuppeteerError(error)) return false;
    fatalErrorCount++;
    console.warn(`[WA Service] ⚠️ Erro fatal de Puppeteer detectado (${fatalErrorCount}/${MAX_FATAL_ERRORS}): ${error.message || error}`);
    if (fatalErrorCount >= MAX_FATAL_ERRORS) {
        restartClient();
        return true;
    }
    return false;
};

const restartClient = async () => {
    if (isRestarting) {
        console.log('[WA Service] ⏳ Restart já em andamento, ignorando...');
        return;
    }
    isRestarting = true;
    console.log('[WA Service] 🔄 Reiniciando cliente devido a falhas excessivas...');
    isReady = false;
    fatalErrorCount = 0;
    
    // Invalidate contact cache since the frame is gone
    try {
        const cs = require('./contactService');
        if (cs._invalidateCache) cs._invalidateCache();
    } catch (e) {}
    
    try {
        await client.destroy();
    } catch (e) {
        console.warn('[WA Service] ⚠️ Erro ao destruir cliente:', e.message);
    }
    await delay(3000);
    try {
        await client.initialize();
        console.log('[WA Service] ✅ Cliente reinicializado com sucesso.');
    } catch (err) {
        console.error('[WA Service] ❌ Erro no re-init:', err);
    } finally {
        isRestarting = false;
    }
};

let isReady = false;

console.log('[WA Service] 🚀 Iniciando processo de autenticação e bot...');

client.on('qr', (qr) => {
    console.log('[WA Service] ⚠️ QR Code recebido! Por favor, escaneie com o WhatsApp do celular:');
    qrcode.generate(qr, { small: true });
});

client.on('loading_screen', (percent, message) => {
    console.log(`[WA Service] ⏳ Carregando WhatsApp Web: ${percent}% - ${message}`);
});

client.on('authenticated', () => {
    console.log('[WA Service] ✅ Autenticado com sucesso!');
});

client.on('auth_failure', msg => {
    console.error('[WA Service] ❌ FALHA DE AUTENTICAÇÃO:', msg);
    console.error('[WA Service] DICA: Tente apagar a pasta .wwebjs_auth se o erro persistir.');
    isReady = false;
});

client.on('ready', () => {
    console.log('[WA Service] 🚀 Cliente WhatsApp está logado e pronto!');
    isReady = true;
    fatalErrorCount = 0; // Reset on successful ready
    isRestarting = false;
    
    // Attach page-level crash listener to detect detached frames proactively
    try {
        const page = client.pupPage;
        if (page) {
            page.on('error', (err) => {
                console.error('[WA Service] 💥 Puppeteer page crash:', err.message);
                trackFatalError(err);
            });
            page.on('close', () => {
                console.error('[WA Service] 💥 Puppeteer page was closed unexpectedly!');
                isReady = false;
                restartClient();
            });
        }
    } catch (e) {
        console.warn('[WA Service] ⚠️ Não foi possível anexar listener de crash na page:', e.message);
    }
});

client.on('disconnected', (reason) => {
    console.log('[WA Service] 🔌 Cliente foi desconectado:', reason);
    isReady = false;
    if (!isRestarting) {
        setTimeout(() => client.initialize().catch(err => console.error('[WA Service] ❌ Erro no re-init após desconexão:', err)), 5000);
    }
});

client.on('message', async msg => {
    console.log(`[WA Service] 💬 Mensagem de ${msg.from}: ${msg.body.substring(0, 50)}${msg.body.length > 50 ? '...' : ''}`);
});

console.log('[WA Service] 🛠️ Inicializando o cliente Puppeteer...');
client.initialize().then(() => {
    console.log('[WA Service] ⚙️ Comando de inicialização aceito. Aguardando eventos de login...');
}).catch(err => {
    console.error('[WA Service] ❌ Erro fatal na inicialização:', err);
    console.error('[WA Service] DICA: Verifique se o Chrome está instalado em C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe');
});

// Helper para atrasos
const delay = ms => new Promise(res => setTimeout(res, ms));

/**
 * Normaliza número ou JID garantindo que números brasileiros de 10 ou 11 dígitos
 * sem DDI (55) recebam o prefixo 55.
 */
const normalizeNumberJid = (jid) => {
    if (!jid) return jid;
    if (jid.includes('@g.us') || jid.includes('@lid')) return jid;
    
    let clean = jid.replace('@c.us', '').replace(/\D/g, '');
    if (clean.length === 10 || clean.length === 11) {
        if (!clean.startsWith('55')) {
            clean = `55${clean}`;
        }
    }
    return `${clean}@c.us`;
};

// Envio de mensagem
app.post('/api/whatsapp/send', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { number, message } = req.body;
    if (!number || !message) return res.status(400).json({ error: 'Faltam dados de number e message.' });

    let formattedNumber = normalizeNumberJid(number);
    if (!formattedNumber) {
        return res.status(400).json({ error: 'Número inválido ou malformado. Certifique-se de enviar um número de telefone ou um ID válido.' });
    }

    try {
        // Validação contra IDs truncados (ex: "5511... @c.us")
        if (formattedNumber.includes('...')) {
            throw new Error(`ID de contato truncado/inválido recebido: ${formattedNumber}. Verifique o frontend.`);
        }

        let isRegistered = true;
        
        // Apenas verifica registro para números normais (@c.us)
        if (formattedNumber.includes('@c.us') && formattedNumber.length > 5) {
            try {
                isRegistered = await client.isRegisteredUser(formattedNumber);
                fatalErrorCount = 0; // Reset se funcionar
            } catch (regError) {
                console.error(`[WA Service] Erro ao verificar registro para ${formattedNumber}: ${regError.message}`);
                
                // Detecta erros fatais de Puppeteer (detached frame, context destroyed, etc.)
                trackFatalError(regError);

                // Se falhar o check, assumimos true e deixamos o envio tentar (mais resiliente a erros 't: t')
                isRegistered = true;
            }
            
            // Regra do 9º dígito brasileiro (Tenta alternar caso falhe o primário)
            if (!isRegistered && formattedNumber.startsWith('55')) {
                const raw = formattedNumber.replace('@c.us', '');
                if (raw.length === 13) {
                    // Tem 9 dígitos, tenta sem o 9
                    let altNumber = `55${raw.substring(4)}@c.us`;
                    try {
                        if (await client.isRegisteredUser(altNumber)) {
                            formattedNumber = altNumber;
                            isRegistered = true;
                        }
                    } catch (e) {}
                } else if (raw.length === 12) {
                    // Não tem 9 dígitos, tenta com o 9
                    let altNumber = `55${raw.substring(2,4)}9${raw.substring(4)}@c.us`;
                    try {
                        if (await client.isRegisteredUser(altNumber)) {
                            formattedNumber = altNumber;
                            isRegistered = true;
                        }
                    } catch (e) {}
                }
            }

            if (!isRegistered) {
                return res.status(404).json({ error: 'Este número não está registrado no WhatsApp.' });
            }
        }
        let chat;
        try {
            chat = await client.getChatById(formattedNumber);
            if (chat) {
                // Simular digitação real pra evitar bans
                await chat.sendStateTyping();
                const typingDelay = Math.max(1000, Math.min(message.length * 50, 5000));
                await delay(typingDelay);
                await chat.clearState(); // Para de reportar que está digitando
            }
        } catch (e) {
            console.log(`[WA Service] Chat ${formattedNumber} não encontrado no cache ou erro Puppeteer: ${e.message}`);
            trackFatalError(e);
        }

        await client.sendMessage(formattedNumber, message);
        fatalErrorCount = 0; // Sucesso no envio reseta contador de erros

        res.json({ success: true, number: formattedNumber });
    } catch (err) {
        console.error('[WA Service] Erro no envio:', err.message);
        
        trackFatalError(err);

        res.status(500).json({ error: 'Falha no envio da mensagem.', details: err.message });
    }
});

// Endpoint de Status e Saúde
app.get('/api/whatsapp/status', (req, res) => {
    res.json({
        isReady,
        authenticated: client.info ? true : false,
        pushname: client.info ? client.info.pushname : null,
        wid: client.info ? client.info.wid : null,
        platform: process.platform,
        fatalErrors: fatalErrorCount
    });
});

// Endpoint para buscar chats por nome (fuzzy search)
app.get('/api/whatsapp/chats/search', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { name, minSimilarity = 0.5, limit = 10 } = req.query;
    
    if (!name) {
        return res.status(400).json({ error: 'Parâmetro "name" é obrigatório.' });
    }

    try {
        const chats = await contactService.searchChatsByName(client, name, {
            minSimilarity: parseFloat(minSimilarity),
            limit: parseInt(limit)
        });
        
        res.json({
            query: name,
            count: chats.length,
            chats
        });
    } catch (error) {
        console.error('[WA Service] Erro ao buscar chats:', error);
        res.status(500).json({ error: error.message, isReady });
    }
});

// Endpoint para buscar histórico de mensagens de uma conversa dado o número de telefone
app.get('/api/whatsapp/chats/by-number/:number/messages', async (req, res) => {
    // Aceita requisições se estiver autenticado, não apenas se isReady for true
    // isReady pode demorar a ficar true após reload, mas authenticated indica que está funcionando
    if (!isReady && !client.info) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });

    const { number } = req.params;
    const limit = parseInt(req.query.limit) || 30;

    let rawNumber = number.replace(/\D/g, '');

    // Normalização Brasil (Garante prefixo 55 se faltar)
    if (rawNumber.length === 10 || rawNumber.length === 11) {
        if (!rawNumber.startsWith('55')) rawNumber = `55${rawNumber}`;
    }

    try {
        let chat;
        let resolvedId = null;

        // 1. Tenta resolver ID oficial via getNumberId (resolve @c.us, @lid e 9º dígito)
        try {
            const info = await client.getNumberId(rawNumber);
            if (info) {
                resolvedId = info._serialized;
            } else if (rawNumber.startsWith('55')) {
                // Tenta alternar 9º dígito se o primeiro falhou
                let altNumber;
                if (rawNumber.length === 13) altNumber = `55${rawNumber.substring(4)}`; // Remove o 9
                else if (rawNumber.length === 12) altNumber = `55${rawNumber.substring(2,4)}9${rawNumber.substring(4)}`; // Adiciona o 9

                if (altNumber) {
                    const altInfo = await client.getNumberId(altNumber);
                    if (altInfo) resolvedId = altInfo._serialized;
                }
            }
        } catch (e) {
            console.warn(`[WA Service] getNumberId falhou para ${rawNumber}:`, e.message);
        }

        // 2. Tenta buscar o chat pelo ID resolvido
        if (resolvedId) {
            try {
                chat = await client.getChatById(resolvedId);
            } catch (e) {}
        }

        // 3. Fallback: Busca manual na lista de chats ativos (mais resiliente)
        if (!chat) {
            console.log(`[WA Service] ID oficial não resolvido. Buscando manual na lista de chats para: ${rawNumber}`);
            const chats = await client.getChats();
            const candidates = [rawNumber];
            if (rawNumber.startsWith('55')) {
                if (rawNumber.length === 13) candidates.push(`55${rawNumber.substring(4)}`);
                else if (rawNumber.length === 12) candidates.push(`55${rawNumber.substring(2,4)}9${rawNumber.substring(4)}`);
            }

            chat = chats.find(c => {
                const user = c.id.user;
                return candidates.some(cand => user === cand || user.includes(cand) || cand.includes(user));
            });
        }

        if (!chat) {
            return res.status(404).json({ error: `Conversa não encontrada para o número ${number}` });
        }

        const messages = await chat.fetchMessages({ limit });

        const simplifiedMessages = messages.map(m => ({
            id: m.id._serialized,
            fromMe: m.fromMe,
            body: m.body,
            type: m.type,
            timestamp: m.timestamp,
            hasMedia: m.hasMedia
        }));

        res.json({
            number: chat.id._serialized,
            messages: simplifiedMessages
        });
    } catch (error) {
        console.error("[WA Service] Erro crítico ao buscar mensagens por número:", error.message);
        res.status(500).json({ error: `Erro ao buscar mensagens para o número ${number}: ${error.message}` });
    }
});

// Endpoint p/ conversas (exemplo do Drawer)
app.get('/api/whatsapp/chats', async (req, res) => {
    // Aceita requisições se estiver autenticado, não apenas se isReady for true
    if (!isReady && !client.info) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });

    try {
        const chats = await client.getChats();
        const simplifiedChats = chats.map(c => ({
            id: c.id._serialized,
            name: c.name || c.id.user,
            unreadCount: c.unreadCount,
            timestamp: c.timestamp
        }));
        fatalErrorCount = 0; // Reset on success
        res.json({ chats: simplifiedChats });
    } catch (error) {
        console.error('[WA Service] Erro ao buscar conversas:', error.message);
        const triggered = trackFatalError(error);
        const statusCode = isFatalPuppeteerError(error) ? 503 : 500;
        res.status(statusCode).json({ 
            error: 'Erro ao buscar conversas.',
            recoverable: triggered,
            details: error.message
        });
    }
});

// ==================== ENDPOINTS DE CONVERSAS E EVENTOS ====================

// Endpoint para buscar histórico de mensagens de uma conversa
app.get('/api/whatsapp/chats/:chatId/messages', async (req, res) => {
    // Aceita requisições se estiver autenticado, não apenas se isReady for true
    if (!isReady && !client.info) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    let { chatId } = req.params;
    const limit = parseInt(req.query.limit) || 50;

    try {
        let chat;
        try {
            // Verifica ID truncado
            if (chatId.includes('...')) {
                throw new Error(`ID truncado detectado: ${chatId}. O frontend provavelmente enviou um valor visual em vez do ID real.`);
            }

            chat = await client.getChatById(chatId);
            fatalErrorCount = 0;
        } catch (e) {
            console.warn(`[WA Service] Falha na primeira tentativa de getChatById(${chatId}):`, e.message);
            trackFatalError(e);

            // Se falhou e termina em @lid ou @c.us, tenta extrair apenas os números e buscar novamente
            const cleanNumber = chatId.replace('@c.us', '').replace('@lid', '').replace('@g.us', '').replace('@', '');
            if (cleanNumber && cleanNumber.length > 5 && !isNaN(cleanNumber) && !cleanNumber.includes('..')) {
                chat = await client.getChatById(`${cleanNumber}@c.us`);
            } else {
                throw new Error(isFatalPuppeteerError(e) ? 'Erro de comunicação com o WhatsApp (Puppeteer Crash - reiniciando...)' : `ID de conversa inválido: ${chatId}`);
            }
        }

        const messages = await chat.fetchMessages({ limit });
        
        const simplifiedMessages = messages.map(m => ({
            id: m.id._serialized,
            fromMe: m.fromMe,
            body: m.body,
            type: m.type,
            timestamp: m.timestamp,
            hasMedia: m.hasMedia
        }));
        
        res.json({ messages: simplifiedMessages });
    } catch (error) {
        console.error("[WA Service] Erro fatal ao buscar mensagens:", error.message);
        res.status(500).json({ error: `Erro ao buscar mensagens da conversa: ${error.message}` });
    }
});

// Endpoint para marcar conversa como Lida/Não Lida
app.post('/api/whatsapp/chats/:chatId/read-status', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { chatId } = req.params;
    const { read } = req.body; // boolean

    try {
        const chat = await client.getChatById(chatId);
        if (read) {
            await chat.sendSeen();
        } else {
            await chat.markUnread();
        }
        res.json({ success: true, chatId, read });
    } catch (error) {
        res.status(500).json({ error: 'Erro ao atualizar status da conversa.' });
    }
});

// Endpoint para fixar/desfixar (Pin) ou arquivar conversa
app.post('/api/whatsapp/chats/:chatId/state', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { chatId } = req.params;
    const { action } = req.body; // 'pin', 'unpin', 'archive', 'unarchive'

    try {
        const chat = await client.getChatById(chatId);
        
        switch (action) {
            case 'pin': await chat.pin(); break;
            case 'unpin': await chat.unpin(); break;
            case 'archive': await chat.archive(); break;
            case 'unarchive': await chat.unarchive(); break;
            default: return res.status(400).json({ error: 'Ação inválida. Use pin, unpin, archive ou unarchive' });
        }
        res.json({ success: true, chatId, action });
    } catch (error) {
        res.status(500).json({ error: 'Erro ao atualizar estado da conversa.' });
    }
});

// ==================== ENDPOINTS DE GRUPOS ====================

// Endpoint para criar um grupo
app.post('/api/whatsapp/groups/create', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { name, participants } = req.body; 
    // participants deve ser array de números, ex: ['5511999999999', '5511888888888']
    
    if (!name || !participants || !Array.isArray(participants)) {
        return res.status(400).json({ error: 'Faltam dados: name (string) e participants (array).' });
    }

    try {
        const formattedParticipants = participants.map(p => p.includes('@c.us') ? p : `${p}@c.us`);
        const result = await client.createGroup(name, formattedParticipants);
        res.json({ success: true, group: result });
    } catch (error) {
        console.error(error);
        res.status(500).json({ error: 'Erro ao criar o grupo.' });
    }
});

// ==================== ENDPOINTS DE MÍDIAS (IMAGENS, PDF) ====================

// Envio de mídia (Imagem, Documento) via URL ou Base64
app.post('/api/whatsapp/send-media', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { number, mediaUrl, mediaBase64, mediaName, caption } = req.body;
    
    if (!number || (!mediaUrl && !mediaBase64)) {
        return res.status(400).json({ error: 'Faltam dados: number e mediaUrl (ou mediaBase64).' });
    }

    let formattedNumber = normalizeNumberJid(number);
    let rawNumber = formattedNumber.replace('@c.us', '');

    try {
        try {
            isRegistered = await client.isRegisteredUser(formattedNumber);
        } catch (regError) {
            console.error(`[WA Service] Erro ao verificar registro (Media) para ${formattedNumber}: ${regError.message}`);
            isRegistered = true;
        }
        
        // Regra do 9º dígito brasileiro 
        if (!isRegistered && rawNumber.startsWith('55') && rawNumber.length === 13) {
            let altNumber = `55${rawNumber.substring(4)}`;
            try {
                if (await client.isRegisteredUser(`${altNumber}@c.us`)) {
                    formattedNumber = `${altNumber}@c.us`;
                    isRegistered = true;
                }
            } catch (e) {}
        } else if (!isRegistered && rawNumber.startsWith('55') && rawNumber.length === 12) {
            let altNumber = `55${rawNumber.substring(2,4)}9${rawNumber.substring(4)}`;
            try {
                if (await client.isRegisteredUser(`${altNumber}@c.us`)) {
                    formattedNumber = `${altNumber}@c.us`;
                    isRegistered = true;
                }
            } catch (e) {}
        } else if (!isRegistered) {
            return res.status(404).json({ error: 'Este número não está registrado no WhatsApp.' });
        }

        let media;
        if (mediaUrl) {
            media = await MessageMedia.fromUrl(mediaUrl, { unsafeMime: true });
        } else if (mediaBase64) {
            // base64 deve vir no formato data:image/png;base64,iVBOR...
            const [mimetype, data] = mediaBase64.split(';base64,');
            const mime = mimetype.replace('data:', '');
            media = new MessageMedia(mime, data, mediaName || 'documento');
        }

        try {
            let chat = await client.getChatById(formattedNumber);
            if (chat) {
                await chat.sendStateTyping();
                await delay(1500); // Simulando carregamento
                await chat.clearState();
            }
        } catch (e) { }

        await client.sendMessage(formattedNumber, media, { caption: caption || '' });

        res.json({ success: true, number: formattedNumber });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Falha no envio da mídia.', details: err.message });
    }
});

// ==================== ENDPOINTS DE CONTATOS ====================

/**
 * GET /api/whatsapp/contacts/search?name=João&exactMatch=false&minSimilarity=0.7&limit=20
 * Busca contatos pelo nome com suporte a busca fuzzy
 */
app.get('/api/whatsapp/contacts/search', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { name, exactMatch = false, minSimilarity = 0.6, limit = 20 } = req.query;
    
    if (!name) {
        return res.status(400).json({ error: 'Parâmetro "name" é obrigatório.' });
    }

    try {
        console.log(`[WA Service] Recebida busca de contatos: "${name}" (exact: ${exactMatch}, minSim: ${minSimilarity})`);
        const contacts = await contactService.searchContactsByName(client, name, {
            exactMatch: exactMatch === 'true',
            minSimilarity: parseFloat(minSimilarity),
            limit: parseInt(limit)
        });
        
        console.log(`[WA Service] Busca por "${name}" retornou ${contacts.length} resultados.`);
        res.json({
            query: name,
            count: contacts.length,
            contacts
        });
    } catch (error) {
        console.error('[WA Service] Erro ao buscar contatos:', error);
        res.status(500).json({ error: error.message, isReady });
    }
});

/**
 * GET /api/whatsapp/contacts/by-name/:name
 * Busca um contato único pelo nome exato
 */
app.get('/api/whatsapp/contacts/by-name/:name', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { name } = req.params;

    try {
        const contact = await contactService.findContactByExactName(client, name);
        
        if (!contact) {
            return res.status(404).json({ error: `Contato "${name}" não encontrado.` });
        }
        
        res.json(contact);
    } catch (error) {
        console.error('Erro ao buscar contato:', error);
        res.status(500).json({ error: error.message });
    }
});

/**
 * GET /api/whatsapp/contacts/by-number/:number
 * Busca um contato pelo número de telefone
 */
app.get('/api/whatsapp/contacts/by-number/:number', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { number } = req.params;

    try {
        const normalizedNumber = normalizeNumberJid(number).replace('@c.us', '');
        const contact = await contactService.findContactByNumber(client, normalizedNumber);
        
        if (!contact) {
            return res.status(404).json({ error: `Contato com número ${number} não encontrado.` });
        }
        
        res.json(contact);
    } catch (error) {
        console.error('Erro ao buscar contato:', error);
        res.status(500).json({ error: error.message });
    }
});

/**
 * GET /api/whatsapp/contacts/by-number/:number/profile-pic
 * Busca a URL da foto de perfil de um contato pelo número
 */
app.get('/api/whatsapp/contacts/by-number/:number/profile-pic', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { number } = req.params;

    try {
        const normalizedNumber = normalizeNumberJid(number).replace('@c.us', '');
        let profilePicUrl = await contactService.getProfilePic(client, normalizedNumber);
        
        // Fallback: Tenta com 55 se o número for brasileiro e a primeira tentativa falhar
        if (!profilePicUrl && !normalizedNumber.startsWith('55') && normalizedNumber.length >= 10) {
            const altNumber = `55${normalizedNumber}`;
            console.log(`[WA Service] Foto não encontrada para ${normalizedNumber}. Tentando fallback com ${altNumber}...`);
            profilePicUrl = await contactService.getProfilePic(client, altNumber);
        }
        
        if (!profilePicUrl) {
            return res.status(404).json({ error: `Foto de perfil para o número ${number} não encontrada ou privada.` });
        }
        
        res.json({ profilePicUrl });
    } catch (error) {
        console.error('Erro ao buscar foto de perfil:', error);
        res.status(500).json({ error: error.message });
    }
});

/**
 * GET /api/whatsapp/contacts/all?onlyMyContacts=true&limit=100
 * Lista todos os contatos
 */
app.get('/api/whatsapp/contacts/all', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { onlyMyContacts = true, limit = 5000 } = req.query;

    try {
        console.log(`[WA Service] 📥 Requisição de sincronia total recebida. Buscando contatos (limite: ${limit})...`);
        const contacts = await contactService.listAllContacts(client, {
            onlyMyContacts: onlyMyContacts === 'true',
            limit: parseInt(limit)
        });
        
        console.log(`[WA Service] ✅ Sincronia pronta: Enviando ${contacts.length} contatos para o Backend.`);
        res.json({
            count: contacts.length,
            contacts
        });
    } catch (error) {
        console.error('[WA Service] Erro ao listar contatos:', error);
        res.status(500).json({ error: error.message });
    }
});

const PORT = process.env.PORT || 8001;
app.listen(PORT, () => {
    console.log(`Serviço WhatsApp rodando na porta ${PORT}`);
});
