# 🛠️ Toolkit de Enriquecimento B2B (OSINT)

Criei um script separado e modular que implementa as 4 técnicas de prospecção e enriquecimento que você descreveu. Ele está localizado em:
`scripts/osint-toolkit/`

## 🚀 Como usar

### 1. Instalação
Acesse a pasta e instale as dependências básicas:
```powershell
cd scripts/osint-toolkit
npm install
```

### 2. Executando o Teste
Para ver o script em ação (Dorking e Consulta CNPJ):
```powershell
node test_toolkit.js
```

## 🧠 Funcionalidades Implementadas

### 🔍 Google Dorking Generator
Gera automaticamente links de pesquisa poderosos para:
- Encontrar PDFs de ramais e diretórios internos.
- Localizar diretórios de contatos públicos no domínio da empresa.
- Buscar menções de WhatsApp de decisores específicos no LinkedIn.

### 🏢 Consulta de CNPJ Automática
Usa a API da **ReceitaWS** para puxar o telefone principal cadastrado na Receita Federal.
> **Dica:** Como você mencionou, muitas empresas cadastram o celular do sócio ou o número comercial direto aqui.

### 🌐 Scraping + Groq IA (Opcional)
Se você configurar uma `GROQ_API_KEY` no seu ambiente, o script pode:
1. Acessar a página de "Contato" ou "Sobre" de um site.
2. Limpar o HTML (removendo lixo e scripts).
3. Enviar o texto para o **Llama 3.1 (Groq)** para extrair e estruturar os contatos em JSON.

Exemplo de saída da IA:
```json
{
  "contatos": [
    { "nome": "Suprimentos", "numero": "(11) 99999-9999", "tipo": "WhatsApp" },
    { "nome": "Portaria", "numero": "Ramal 202", "tipo": "PABX" }
  ]
}
```

## 📂 Estrutura de Arquivos
- [enrichment_engine.js](file:///c:/Users/João Luccas/Desktop/LINKB2B/hierarchy-mapper/scripts/osint-toolkit/enrichment_engine.js): O motor principal com toda a lógica.
- [test_toolkit.js](file:///c:/Users/João Luccas/Desktop/LINKB2B/hierarchy-mapper/scripts/osint-toolkit/test_toolkit.js): Script de demonstração.
- [package.json](file:///c:/Users/João Luccas/Desktop/LINKB2B/hierarchy-mapper/scripts/osint-toolkit/package.json): Dependências (`axios`, `cheerio`).

---
Desenvolvido por Antigravity para LINKB2B.
