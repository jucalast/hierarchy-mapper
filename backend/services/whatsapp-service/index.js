const express = require('express');
const cors = require('cors');
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const contactService = require('./contactService');

const app = express();
app.use(cors());
app.use(express.json());

// Anti-ban configurations for whatsapp-web.js
// - Usage of existing sessions (LocalAuth) to avoid multiple logins.
// - Chromium arguments to run in stable mode.
const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        headless: true, // Ou false se a pessoa precisar depurar o login
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--single-process', // Pode ajudar em containers
            '--disable-gpu'
        ]
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

    const formattedNumber = number.includes('@c.us') ? number : `${number}@c.us`;

    try {
        const chat = await client.getChatById(formattedNumber);
        
        // Simular digitação real pra evitar bans
        await chat.sendStateTyping();
        // Atraso aleatório entre 1000 e 3000 ms, ou baseado no tamanho da text string
        const typingDelay = Math.max(1000, Math.min(message.length * 50, 5000));
        await delay(typingDelay);

        await client.sendMessage(formattedNumber, message);
        await chat.clearState(); // Para de reportar que está digitando

        res.json({ success: true, number: formattedNumber });
    } catch (err) {
        console.error(err);
        res.status(500).json({ error: 'Falha no envio da mensagem.' });
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
