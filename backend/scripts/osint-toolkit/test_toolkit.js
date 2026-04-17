const EnrichmentEngine = require('./enrichment_engine');

async function test() {
    const engine = new EnrichmentEngine();

    console.log('--- AUTOMAÇÃO DE IDENTIFICAÇÃO DE WHATSAPP ---');

    const leadName = 'Fernando Bertanha Messias';
    const company = 'ABB';

    const result = await engine.deepIdentifyLead(leadName, company);

    console.log(`\n[RESULTADO]`);
    console.log(`> Lead: ${result.lead}`);
    console.log(`> Empresa: ${result.empresa}`);
    
    if (result.whatsapp.waLink) {
        console.log(`\n✅ WHATSAPP IDENTIFICADO:`);
        console.log(`> Número: ${result.whatsapp.numero}`);
        console.log(`> Link Direto: ${result.whatsapp.waLink}`);
    } else {
        console.log(`\n⚠️ WHATSAPP NÃO ENCONTRADO NO CNPJ:`);
        console.log(`> Telefone da Sede: ${result.contatosSede}`);
    }

    console.log('\n[LINKS DE BUSCA RECOMENDADOS]');
    result.estrategiaDorks.forEach(d => {
        console.log(` - ${d.objetivo}: ${d.link}`);
    });

    console.log(`\n> Nota: ${result.notas}`);
}

test().catch(console.error);
