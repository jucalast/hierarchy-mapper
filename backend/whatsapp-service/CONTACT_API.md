# Contact Search API - WhatsApp Service

## Endpoints Disponíveis

### 1. **Busca Fuzzy de Contatos** (Recomendado para UI)
```
GET /api/whatsapp/contacts/search?name=João&exactMatch=false&minSimilarity=0.7&limit=20
```

**Parâmetros Query:**
- `name` (obrigatório): Nome ou parte do nome para buscar
- `exactMatch` (opcional): `true` para busca exata, `false` para fuzzy. Default: `false`
- `minSimilarity` (opcional): Score mínimo (0-1). Default: `0.6`
- `limit` (opcional): Máximo de resultados. Default: `20`

**Respostas:**
- Usa algoritmo **Levenshtein** para busca aproximada
- Retorna ordenado por similitude decrescente
- Cada contato inclui score de similaridade (%)

**Exemplo:**
```bash
# Busca fuzzy por "joao" com limiar 70%
curl "http://localhost:8001/api/whatsapp/contacts/search?name=joao&minSimilarity=0.7"

# Busca exata
curl "http://localhost:8001/api/whatsapp/contacts/search?name=João Silva&exactMatch=true"
```

**Resposta:**
```json
{
  "query": "joao",
  "count": 3,
  "contacts": [
    {
      "id": "5511987654321@c.us",
      "name": "João Silva",
      "number": "5511987654321",
      "isBusiness": false,
      "isMyContact": true,
      "similarity": 95
    },
    {
      "id": "5512912345678@c.us",
      "name": "João Santos",
      "number": "5512912345678",
      "isBusiness": false,
      "isMyContact": true,
      "similarity": 91
    }
  ]
}
```

---

### 2. **Busca por Nome Exato**
```
GET /api/whatsapp/contacts/by-name/:name
```

**Parâmetros Path:**
- `name`: Nome exato do contato

**Exemplo:**
```bash
curl "http://localhost:8001/api/whatsapp/contacts/by-name/João Silva"
```

**Resposta (200):**
```json
{
  "id": "5511987654321@c.us",
  "name": "João Silva",
  "number": "5511987654321",
  "isBusiness": false,
  "isMyContact": true,
  "similarity": 100
}
```

**Erro (404):**
```json
{
  "error": "Contato \"João Silva\" não encontrado."
}
```

---

### 3. **Busca por Número de Telefone**
```
GET /api/whatsapp/contacts/by-number/:number
```

**Parâmetros Path:**
- `number`: Número do telefone (com ou sem @c.us)

**Exemplo:**
```bash
# Com código de país
curl "http://localhost:8001/api/whatsapp/contacts/by-number/5511987654321"

# Ou com sufixo WhatsApp
curl "http://localhost:8001/api/whatsapp/contacts/by-number/5511987654321%40c.us"
```

**Resposta (200):**
```json
{
  "id": "5511987654321@c.us",
  "name": "João Silva",
  "number": "5511987654321",
  "isBusiness": false,
  "isMyContact": true,
  "similarity": 100
}
```

---

### 4. **Listar Todos os Contatos**
```
GET /api/whatsapp/contacts/all?onlyMyContacts=true&limit=100
```

**Parâmetros Query:**
- `onlyMyContacts` (opcional): `true` para apenas contatos salvos, `false` para todos. Default: `true`
- `limit` (opcional): Máximo de resultados. Default: `100`

**Exemplo:**
```bash
# Apenas meus contatos salvos
curl "http://localhost:8001/api/whatsapp/contacts/all"

# Todos os contatos (incluindo números de grupo, etc)
curl "http://localhost:8001/api/whatsapp/contacts/all?onlyMyContacts=false&limit=500"
```

**Resposta:**
```json
{
  "count": 2,
  "contacts": [
    {
      "id": "5511987654321@c.us",
      "name": "João Silva",
      "number": "5511987654321",
      "isBusiness": false,
      "isMyContact": true
    },
    {
      "id": "5512912345678@c.us",
      "name": "João Santos",
      "number": "5512912345678",
      "isBusiness": false,
      "isMyContact": true
    }
  ]
}
```

---

## Algoritmo de Busca Fuzzy

A busca fuzzy implementa o algoritmo **Levenshtein Distance** que:
1. Normaliza strings (minúscula, trim, espaços múltiplos)
2. Calcula distância de edição entre strings
3. Retorna score de 0 a 1 (1 = idêntico)

**Regras especiais:**
- Match exato: score = 1.0
- Substring contido: score = 0.9
- Levenshtein distance normalizado: 0.0-0.8

**Comportamento da busca:**
```
Entrada: "joao silva"
Contatos encontrados:
  - "João Silva"        → 1.0  (exato)
  - "João S. Silva"     → 0.95 (muito similar)
  - "Joao Silva"        → 0.93 (caracteres diferentes)
  - "João Silvano"      → 0.85 (substring + diferenças)
  - "João Santos"       → 0.73 (parcial)
```

---

## Structure da Service

### Funções Exportadas em `contactService.js`:

1. **`searchContactsByName(client, searchName, options)`**
   - Busca fuzzy com opções customizáveis
   - Scores de similaridade
   - Suporta limite de resultados

2. **`findContactByExactName(client, name)`**
   - Busca por nome exato
   - Retorna um contato ou null

3. **`findContactByNumber(client, number)`**
   - Busca por número de telefone
   - Formata automaticamente @c.us

4. **`listAllContacts(client, options)`**
   - Lista todos com filtros
   - Suporta limite e filtro de "meus contatos"

5. **Helpers:**
   - `normalizeString()`: Normalização de strings
   - `calculateSimilarity()`: Calcula score fuzzy
   - `getEditDistance()`: Levenshtein distance

---

## Casos de Uso Recomendados

### Para autocomplete/busca rápida:
```javascript
GET /api/whatsapp/contacts/search?name=jo&minSimilarity=0.5&limit=10
```

### Para busca de contato específico (envio de mensagem):
```javascript
GET /api/whatsapp/contacts/by-name/João%20Silva?exactMatch=true
```

### Para validar se número existe:
```javascript
GET /api/whatsapp/contacts/by-number/5511987654321
```

### Para popular lista de contatos na UI:
```javascript
GET /api/whatsapp/contacts/all?limit=50
```

---

## Tratamento de Erros

**503 - WhatsApp não pronto:**
```json
{
  "error": "WhatsApp indisponível ou não logado."
}
```

**400 - Parâmetro inválido:**
```json
{
  "error": "Parâmetro \"name\" é obrigatório."
}
```

**404 - Contato não encontrado:**
```json
{
  "error": "Contato \"João Silva\" não encontrado."
}
```

**500 - Erro interno:**
```json
{
  "error": "Erro ao buscar contatos: [detalhes...]"
}
```

---

## Performance

- **Lazy Loading**: Contatos carregados sob demanda
- **Fuzzy Matching**: O(n * m) onde n = contatos, m = tamanho do nome
- **Caching**: Recomenda-se cache frontend (60s)
- **Limite padrão**: 20 resultados para não sobrecarregar

---

## Integração Frontend (React Example)

```typescript
// Hook para buscar contatos
const useContactSearch = () => {
  const [loading, setLoading] = useState(false);
  const [contacts, setContacts] = useState([]);

  const searchContacts = async (name: string) => {
    setLoading(true);
    try {
      const response = await fetch(
        `/api/whatsapp/contacts/search?name=${encodeURIComponent(name)}&minSimilarity=0.6&limit=10`
      );
      const data = await response.json();
      setContacts(data.contacts);
    } catch (error) {
      console.error('Erro ao buscar contatos:', error);
      setContacts([]);
    } finally {
      setLoading(false);
    }
  };

  return { searchContacts, contacts, loading };
};

// Uso em Autocomplete
export const ContactAutocomplete = () => {
  const { searchContacts, contacts, loading } = useContactSearch();

  return (
    <div>
      <input
        placeholder="Digite o nome..."
        onChange={(e) => searchContacts(e.target.value)}
      />
      {loading && <p>Carregando...</p>}
      <ul>
        {contacts.map((contact) => (
          <li key={contact.id}>
            {contact.name} ({contact.similarity}%)
          </li>
        ))}
      </ul>
    </div>
  );
};
```
