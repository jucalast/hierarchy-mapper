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
if (fs.existsSync(lockfilePath)) {
    try {
        console.log('[WA Service] Removendo lockfile órfão...');
        fs.unlinkSync(lockfilePath);
    } catch (e) {
        console.error('[WA Service] Falha ao remover lockfile:', e.message);
    }
}

const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        headless: 'new',
        executablePath: process.env.CHROME_PATH || undefined, // Permite override via env
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu',
            '--disable-software-rasterizer',
            '--disable-extensions',
            '--disable-features=IsolateOrigins,site-per-process',
            '--v8-cache-options=none'
        ]
    },
    webVersionCache: {
        type: 'remote',
        remotePath: 'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/2.3000.1037280436-alpha.html'
    }
});

let isReady = false;

client.on('qr', (qr) => {
    // Esse QR code aparece no terminal. Em produção tem que mandar pro Frontend ver via API.
    qrcode.generate(qr, { small: true });
    console.log('QR Code generated. Escaneie pelo WhatsApp do telefone.', qr);
});

client.on('ready', () => {
    console.log('Cliente WhatsApp está logado e pronto!');
    isReady = true;
});

client.on('message', async msg => {
    // Processamento de mensagem recebida
    console.log(`Mensagem recebida de ${msg.from}: ${msg.body}`);
});

client.initialize();

// Helper para atrasos
const delay = ms => new Promise(res => setTimeout(res, ms));

// Envio de mensagem
app.post('/api/whatsapp/send', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { number, message } = req.body;
    if (!number || !message) return res.status(400).json({ error: 'Faltam dados de number e message.' });

    let formattedNumber = number;
    if (!number.includes('@c.us') && !number.includes('@lid') && !number.includes('@g.us')) {
        let rawNumber = number.replace(/\D/g, ''); 
        formattedNumber = `${rawNumber}@c.us`;
    }

    try {
        let isRegistered = true;
        
        // Apenas verifica registro para números normais (@c.us)
        if (formattedNumber.includes('@c.us')) {
            isRegistered = await client.isRegisteredUser(formattedNumber);
            
            // Regra do 9º dígito brasileiro (Tenta alternar caso falhe o primário)
            let rawNumber = formattedNumber.replace('@c.us', '');
            if (!isRegistered && rawNumber.startsWith('55') && rawNumber.length === 13) {
                let altNumber = `55${rawNumber.substring(4)}`;
                if (await client.isRegisteredUser(`${altNumber}@c.us`)) {
                    formattedNumber = `${altNumber}@c.us`;
                    isRegistered = true;
                }
            } else if (!isRegistered && rawNumber.startsWith('55') && rawNumber.length === 12) {
                let altNumber = `55${rawNumber.substring(2,4)}9${rawNumber.substring(4)}`;
                if (await client.isRegisteredUser(`${altNumber}@c.us`)) {
                    formattedNumber = `${altNumber}@c.us`;
                    isRegistered = true;
                }
            }
        }
        
        if (!isRegistered) {
            return res.status(404).json({ error: 'Este número não está registrado no WhatsApp.' });
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
            console.log("Chat não encontrado no cache, enviando mensagem direta.");
        }

        await client.sendMessage(formattedNumber, message);

        res.json({ success: true, number: formattedNumber });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Falha no envio da mensagem.', details: err.message });
    }
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
        console.error('Erro ao buscar chats:', error);
        res.status(500).json({ error: error.message });
    }
});

// Endpoint para buscar histórico de mensagens de uma conversa dado o número de telefone
app.get('/api/whatsapp/chats/by-number/:number/messages', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    const { number } = req.params;
    const limit = parseInt(req.query.limit) || 30;

    let rawNumber = number.replace(/\D/g, '');
    let formattedNumber = `${rawNumber}@c.us`;

    try {
        const chat = await client.getChatById(formattedNumber);
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
            number: formattedNumber,
            messages: simplifiedMessages 
        });
    } catch (error) {
        console.error(error);
        res.status(500).json({ error: `Erro ao buscar mensagens para o número ${number}.` });
    }
});

// Endpoint p/ conversas (exemplo do Drawer)
app.get('/api/whatsapp/chats', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    try {
        const chats = await client.getChats();
        const simplifiedChats = chats.map(c => ({
            id: c.id._serialized,
            name: c.name || c.id.user,
            unreadCount: c.unreadCount,
            timestamp: c.timestamp
        }));
        res.json({ chats: simplifiedChats });
    } catch (error) {
        res.status(500).json({ error: 'Erro ao buscar conversas.' });
    }
});

// ==================== ENDPOINTS DE CONVERSAS E EVENTOS ====================

// Endpoint para buscar histórico de mensagens de uma conversa
app.get('/api/whatsapp/chats/:chatId/messages', async (req, res) => {
    if (!isReady) return res.status(503).json({ error: 'WhatsApp indisponível ou não logado.' });
    
    let { chatId } = req.params;
    const limit = parseInt(req.query.limit) || 50;

    try {
        let chat;
        try {
            chat = await client.getChatById(chatId);
        } catch (e) {
            console.log(`[WA Service] Falha ao buscar por ID ${chatId}. Tentando extrair número...`);
            // Se falhou e termina em @lid ou @c.us, tenta extrair apenas os números e buscar novamente
            const cleanNumber = chatId.split('@')[0];
            if (cleanNumber && cleanNumber.length > 5) {
                chat = await client.getChatById(`${cleanNumber}@c.us`);
            } else {
                throw e;
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

    let rawNumber = number.includes('@c.us') ? number.replace('@c.us', '') : number;
    rawNumber = rawNumber.replace(/\D/g, '');
    let formattedNumber = `${rawNumber}@c.us`;

    try {
        let isRegistered = await client.isRegisteredUser(formattedNumber);
        
        // Regra do 9º dígito brasileiro 
        if (!isRegistered && rawNumber.startsWith('55') && rawNumber.length === 13) {
            let altNumber = `55${rawNumber.substring(4)}`;
            if (await client.isRegisteredUser(`${altNumber}@c.us`)) {
                formattedNumber = `${altNumber}@c.us`;
            }
        } else if (!isRegistered && rawNumber.startsWith('55') && rawNumber.length === 12) {
            let altNumber = `55${rawNumber.substring(2,4)}9${rawNumber.substring(4)}`;
            if (await client.isRegisteredUser(`${altNumber}@c.us`)) {
                formattedNumber = `${altNumber}@c.us`;
            }
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
        const contacts = await contactService.searchContactsByName(client, name, {
            exactMatch: exactMatch === 'true',
            minSimilarity: parseFloat(minSimilarity),
            limit: parseInt(limit)
        });
        
        res.json({
            query: name,
            count: contacts.length,
            contacts
        });
    } catch (error) {
        console.error('Erro ao buscar contatos:', error);
        res.status(500).json({ error: error.message });
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
        const contact = await contactService.findContactByNumber(client, number);
        
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
        let profilePicUrl = await contactService.getProfilePic(client, number);
        
        // Fallback: Tenta com 55 se o número for brasileiro e a primeira tentativa falhar
        if (!profilePicUrl && !number.startsWith('55') && number.length >= 10) {
            const altNumber = `55${number}`;
            console.log(`[WA Service] Foto não encontrada para ${number}. Tentando fallback com ${altNumber}...`);
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
    
    const { onlyMyContacts = true, limit = 100 } = req.query;

    try {
        const contacts = await contactService.listAllContacts(client, {
            onlyMyContacts: onlyMyContacts === 'true',
            limit: parseInt(limit)
        });
        
        res.json({
            count: contacts.length,
            contacts
        });
    } catch (error) {
        console.error('Erro ao listar contatos:', error);
        res.status(500).json({ error: error.message });
    }
});

const PORT = process.env.PORT || 8001;
app.listen(PORT, () => {
    console.log(`Serviço WhatsApp rodando na porta ${PORT}`);
});
