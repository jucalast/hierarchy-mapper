const EnrichmentEngine = require('./enrichment_engine');

async function main() {
    const args = process.argv.slice(2);
    if (args.length < 2) {
        console.error(JSON.stringify({ error: "Uso: node cli_enrich.js 'Nome' 'Empresa'" }));
        process.exit(1);
    }

    const leadName = args[0];
    const companyName = args[1];
    const officialDomain = args[2] || null;
    const officialCnpj = args[3] || null;

    try {
        const engine = new EnrichmentEngine({
            groqApiKey: process.env.GROQ_API_KEY
        });
        const result = await engine.deepIdentifyLead(leadName, companyName, officialDomain, officialCnpj);
        console.log(JSON.stringify(result));
    } catch (error) {
        console.error(JSON.stringify({ error: error.message }));
        process.exit(1);
    }
}

main();
