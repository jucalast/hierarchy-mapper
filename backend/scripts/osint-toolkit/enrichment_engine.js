const axios = require('axios');
const cheerio = require('cheerio');

/**
 * B2B Enrichment Toolkit - OSINT & Data Scraping
 * 
 * Este script implementa as técnicas descritas para encontrar contatos diretos
 * de tomadores de decisão usando Google Dorking, APIs de CNPJ e Extração por IA.
 */

class EnrichmentEngine {
    constructor(config = {}) {
        this.groqApiKey = config.groqApiKey || process.env.GROQ_API_KEY;
        this.userEmail = config.userEmail || 'test@example.com'; // Para APIs que pedem indentificação
    }

    /**
     * 1. Google Dorking Generator
     * Gera URLs de pesquisa do Google focadas em encontrar ramais e listas.
     */
    generateDorks(companyName, domain, leadName = '') {
        const dorks = [
            {
                title: 'PDFs de Ramais/Contatos',
                url: `https://www.google.com/search?q=site:${domain}+"ramal"+OR+"whatsapp"+filetype:pdf`
            },
            {
                title: 'Diretórios Públicos',
                url: `https://www.google.com/search?q=site:${domain}+"lista+de+contatos"+OR+"diretório"`
            },
            {
                title: 'Busca direta por Tomador no LinkedIn',
                url: `https://www.google.com/search?q="${leadName}"+"whatsapp"+OR+"celular"+site:br.linkedin.com`
            }
        ];

        return dorks;
    }

    /**
     * 2. Cruzamento de Dados Públicos (CNPJ)
     * Busca o telefone principal registrado na Receita Federal via ReceitaWS (Gratuito)
     */
    async fetchByCnpj(cnpj) {
        const cleanCnpj = cnpj.replace(/\D/g, '');
        console.log(`[CNPJ] Consultando dados para: ${cleanCnpj}...`);
        
        try {
            const response = await axios.get(`https://receitaws.com.br/v1/cnpj/${cleanCnpj}`, {
                timeout: 5000
            });
            
            if (response.data && response.data.status !== 'ERROR') {
                return {
                    empresa: response.data.nome,
                    telefone: response.data.telefone,
                    email: response.data.email,
                    situacao: response.data.situacao,
                    tipo: response.data.tipo
                };
            }
            return { error: 'CNPJ não encontrado ou limite de requisições atingido.' };
        } catch (error) {
            return { error: `Erro na API ReceitaWS: ${error.message}` };
        }
    }

    /**
     * 3. Scraping Institucional + Extração com IA
     * Captura o texto bruto de uma página e usa IA para estruturar os telefones.
     */
    async scrapeAndEnrich(url) {
        if (!this.groqApiKey) {
            throw new Error('Groq API Key necessária para a extração com IA.');
        }

        console.log(`[Scraper] Acessando ${url}...`);
        
        try {
            const { data: html } = await axios.get(url, {
                headers: { 'User-Agent': 'Mozilla/5.0' },
                timeout: 10000
            });

            const $ = cheerio.load(html);
            
            // Remove scripts, styles e lixo para não estourar contexto da IA
            $('script, style, nav, footer, iframe').remove();
            const rawText = $('body').text().replace(/\s+/g, ' ').trim().substring(0, 6000);

            console.log(`[AI] Enviando ${rawText.length} caracteres para análise...`);

            const aiResponse = await axios.post('https://api.groq.com/openai/v1/chat/completions', {
                model: 'llama-3.1-70b-versatile',
                messages: [
                    {
                        role: 'system',
                        content: 'Você é um extrator de contatos B2B especializado. Sua tarefa é ler um texto bruto de um site e extrair TODOS os números de telefone encontrados. Identifique se é WhatsApp, PABX ou Fixo. Forneça o nome da pessoa ou setor atrelado ao número se houver. Responda APENAS em JSON puro.'
                    },
                    {
                        role: 'user',
                        content: `Extraia os contatos deste texto:\n\n${rawText}`
                    }
                ],
                response_format: { type: 'json_object' }
            }, {
                headers: { 'Authorization': `Bearer ${this.groqApiKey}` }
            });

            return JSON.parse(aiResponse.data.choices[0].message.content);
        } catch (error) {
            return { error: `Falha no Scraping/IA: ${error.message}` };
        }
    }

    /**
     * 4. Identificação Profunda de Lead (AUTOMAÇÃO TOTAL)
     * Recebe nome e empresa, e faz o cruzamento de dorks + cnpj + sugestão de e-mail.
     */
    async deepIdentifyLead(leadName, companyName, officialDomain = null, officialCnpj = null) {
        console.log(`[DeepID] Iniciando identificação de: ${leadName} na empresa ${companyName}...`);
        
        const domain = officialDomain || (companyName.toLowerCase().replace(/\s+/g, '') + '.com.br');
        const dorks = this.generateDorks(companyName, domain, leadName);

        let companyPhone = 'Busca Manual Necessária';
        
        // Se temos o CNPJ oficial, pesquisamos direto na Receita
        if (officialCnpj) {
            const cnpjData = await this.fetchByCnpj(officialCnpj);
            companyPhone = cnpjData.telefone || companyPhone;
        } else if (companyName.toUpperCase().includes('ABB')) {
            // Fallback para ABB (caso não venha CNPJ)
            const cnpjData = await this.fetchByCnpj('33.449.965/0001-15');
            companyPhone = cnpjData.telefone || companyPhone;
        }

        // Tenta extrair e formatar o WhatsApp se o número parecer um celular
        const waInfo = this.formatWhatsApp(companyPhone);

        const nameParts = leadName.toLowerCase().split(' ');
        const emailPattern = `${nameParts[0]}.${nameParts[nameParts.length - 1]}@${domain}`;

        return {
            lead: leadName,
            empresa: companyName,
            contatosSede: companyPhone,
            whatsapp: waInfo,
            pabx: !waInfo.isMobile ? companyPhone : null,
            emailProvavel: emailPattern,
            estrategiaDorks: dorks.map(d => ({ objetivo: d.title, link: d.url })),
            notas: waInfo.isMobile ? "O script detectou um Celular/WhatsApp provável via CNPJ." : "O número fixo foi detectado. Use o ramal."
        };
    }

    /**
     * Auxiliar: Formata número para link de WhatsApp
     */
    formatWhatsApp(phoneStr) {
        const clean = phoneStr.replace(/\D/g, '');
        // Lógica básica para números do Brasil
        const isMobile = clean.length >= 10 && (clean.substring(2, 3) === '9' || clean.substring(0, 1) === '9');
        
        let waLink = null;
        if (isMobile) {
            const fullNumber = clean.startsWith('55') ? clean : '55' + clean;
            waLink = `https://wa.me/${fullNumber}`;
        }

        return {
            numero: clean,
            isMobile: isMobile,
            waLink: waLink
        };
    }
}

// --- EXEMPLO DE USO ---
async function runExample() {
    const engine = new EnrichmentEngine({
        groqApiKey: 'SEU_GROQ_API_KEY_AQUI' 
    });

    console.log('--- 1. GOOGLE DORKS ---');
    console.log(engine.generateDorks('Exemplo Corp', 'exemplo.com.br', 'João Silva'));

    console.log('\n--- 2. CONSULTA CNPJ (Ex: Google Brasil) ---');
    const cnpjData = await engine.fetchByCnpj('06.990.590/0001-23');
    console.log(cnpjData);

    console.log('\n--- 3. SCRAPING + IA ---');
    console.log('Nota: Requer Chave do Groq configurada.');
    // const results = await engine.scrapeAndEnrich('https://site-alvo.com.br/contato');
    // console.log(results);
}

// Para testar, descomente a linha abaixo:
// runExample();

module.exports = EnrichmentEngine;
