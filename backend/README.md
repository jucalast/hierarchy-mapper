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

4. Executar Servidor Redis:
- No Windows, basta dar um duplo clique no arquivo `ligar_redis.bat` na raiz do projeto.
- Isso abrirá uma janela do Redis que deve permanecer aberta.

5. Executar o Worker (Processamento em segundo plano):
```bash
cd backend
arq services.worker.WorkerSettings
```

6. Executar servidor de desenvolvimento do Backend:
```bash
cd backend
uvicorn main:app --reload --port 8000
```

## Features
- **Motor B2B Genérico**: Descobre funcionários de qualquer empresa brasileira via OSINT
- **Rate Limiting**: Proteção contra spam usando `slowapi`
- **Estrutura Modular**: Integração flexível com APIs de email
- **CORS**: Configurado para aceitar requisições do frontend
- **Filtro Inteligente**: Foco em cadeia de suprimentos e operações
