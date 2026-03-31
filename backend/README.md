# Hierarchy Mapper Backend

Backend genérico construído com FastAPI para análise de hierarquia organizacional de qualquer empresa. Funciona como um motor B2B independente para descoberta de funcionários e estrutura de cadeia de suprimentos.

## Setup

1. Criar ambiente virtual:
```bash
python -m venv venv
venv\Scripts\activate
```

2. Instalar dependências:
```bash
pip install -r requirements.txt
```

3. Configurar variáveis de ambiente (opcional):
- Copie `.env` e configure `EMAIL_API_KEY` para validação de emails

4. Executar servidor de desenvolvimento:
```bash
uvicorn main:app --reload --port 8000
```

## Features
- **Motor B2B Genérico**: Descobre funcionários de qualquer empresa brasileira via OSINT
- **Rate Limiting**: Proteção contra spam usando `slowapi`
- **Estrutura Modular**: Integração flexível com APIs de email
- **CORS**: Configurado para aceitar requisições do frontend
- **Filtro Inteligente**: Foco em cadeia de suprimentos e operações
