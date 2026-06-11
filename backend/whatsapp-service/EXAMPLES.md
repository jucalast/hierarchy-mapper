/**
 * Contact Search Examples & Tests
 * Use isto para testar os endpoints manualmente
 */

// Example 1: Busca Fuzzy (RECOMENDADO para UI)
// Testa com diferentes nomes e similaridades
const example1_fuzzySearch = async () => {
  const response = await fetch(
    'http://localhost:8001/api/whatsapp/contacts/search?name=joão&minSimilarity=0.6&limit=10'
  );
  const data = await response.json();
  console.log('1. Fuzzy Search Results:', data);
  // Output: Retorna todos os contatos similares a "joão"
};

// Example 2: Busca Exata
const example2_exactSearch = async () => {
  const response = await fetch(
    'http://localhost:8001/api/whatsapp/contacts/search?name=João Silva&exactMatch=true'
  );
  const data = await response.json();
  console.log('2. Exact Search Results:', data);
  // Output: Retorna apenas contatos com nome exato "João Silva"
};

// Example 3: Busca por Nome Exato (endpoint dedicado)
const example3_byName = async () => {
  const response = await fetch(
    'http://localhost:8001/api/whatsapp/contacts/by-name/João Silva'
  );
  if (response.ok) {
    const data = await response.json();
    console.log('3. Contact by Name:', data);
  } else {
    console.log('3. Contact not found');
  }
};

// Example 4: Busca por Número
const example4_byNumber = async () => {
  const response = await fetch(
    'http://localhost:8001/api/whatsapp/contacts/by-number/5511987654321'
  );
  if (response.ok) {
    const data = await response.json();
    console.log('4. Contact by Number:', data);
  } else {
    console.log('4. Contact not found');
  }
};

// Example 5: Listar Todos os Contatos
const example5_listAll = async () => {
  const response = await fetch(
    'http://localhost:8001/api/whatsapp/contacts/all?limit=50'
  );
  const data = await response.json();
  console.log('5. All Contacts:', data);
  // Output: Lista de contatos salvos
};

// Example 6: React Component usando a API
const ReactComponentExample = () => {
  const [searchTerm, setSearchTerm] = React.useState('');
  const [results, setResults] = React.useState([]);
  const [loading, setLoading] = React.useState(false);

  const handleSearch = async (value) => {
    setSearchTerm(value);
    if (value.length < 2) {
      setResults([]);
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(
        `/api/whatsapp/contacts/search?name=${encodeURIComponent(value)}&limit=10`
      );
      const data = await response.json();
      setResults(data.contacts);
    } catch (error) {
      console.error('Erro:', error);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input
        type="text"
        placeholder="Digite o nome do contato..."
        value={searchTerm}
        onChange={(e) => handleSearch(e.target.value)}
      />
      {loading && <p>Carregando...</p>}
      <ul>
        {results.map((contact) => (
          <li key={contact.id}>
            <strong>{contact.name}</strong> ({contact.similarity}%)
            <br />
            <small>{contact.number}</small>
          </li>
        ))}
      </ul>
    </div>
  );
};

// Example 7: Autocomplete com Debounce
const AutocompleteWithDebounce = () => {
  const [searchTerm, setSearchTerm] = React.useState('');
  const [results, setResults] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const debounceTimer = React.useRef(null);

  const searchContacts = async (value) => {
    if (value.length < 2) {
      setResults([]);
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(
        `/api/whatsapp/contacts/search?name=${encodeURIComponent(value)}&minSimilarity=0.5&limit=15`
      );
      const data = await response.json();
      setResults(data.contacts);
    } catch (error) {
      console.error('Erro:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (value) => {
    setSearchTerm(value);

    // Debounce: aguarda 300ms antes de fazer a requisição
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      searchContacts(value);
    }, 300);
  };

  return (
    <div className="autocomplete">
      <input
        type="text"
        placeholder="Procurar contato..."
        value={searchTerm}
        onChange={(e) => handleInputChange(e.target.value)}
      />
      {loading && <span className="spinner">⏳</span>}
      {results.length > 0 && (
        <div className="results">
          {results.map((contact) => (
            <div
              key={contact.id}
              className="result-item"
              onClick={() => selectContact(contact)}
            >
              <div className="contact-info">
                <strong>{contact.name}</strong>
                <small>{contact.number}</small>
              </div>
              <small className="similarity">{contact.similarity}%</small>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Example 8: Usar em um Select/Dropdown
const ContactSelect = () => {
  const [contacts, setContacts] = React.useState([]);
  const [selectedContact, setSelectedContact] = React.useState(null);

  React.useEffect(() => {
    const fetchContacts = async () => {
      const response = await fetch('/api/whatsapp/contacts/all?limit=100');
      const data = await response.json();
      setContacts(data.contacts);
    };
    fetchContacts();
  }, []);

  return (
    <select
      value={selectedContact?.id || ''}
      onChange={(e) => {
        const contact = contacts.find((c) => c.id === e.target.value);
        setSelectedContact(contact);
      }}
    >
      <option value="">Selecione um contato...</option>
      {contacts.map((contact) => (
        <option key={contact.id} value={contact.id}>
          {contact.name} ({contact.number})
        </option>
      ))}
    </select>
  );
};

// Example 9: Backend endpoint que usa contactService diretamente
const backendExample = async () => {
  const contactService = require('./contactService');
  
  // Buscar contatos dentro de outro serviço
  const contacts = await contactService.searchContactsByName(
    client,
    'joão',
    { minSimilarity: 0.7, limit: 5 }
  );
  
  console.log('Contatos encontrados:', contacts);
};

// Example 10: Error Handling Completo
const robustFetch = async () => {
  try {
    const contactName = 'João Silva';
    const response = await fetch(
      `/api/whatsapp/contacts/by-name/${encodeURIComponent(contactName)}`
    );

    if (!response.ok) {
      if (response.status === 404) {
        console.log(`Contato "${contactName}" não encontrado`);
      } else if (response.status === 503) {
        console.log('WhatsApp indisponível');
      } else {
        throw new Error(`HTTP Error: ${response.status}`);
      }
      return;
    }

    const contact = await response.json();
    console.log('Contato encontrado:', contact);
    
    // Agora pode usar o contato para enviar mensagem, etc
    await sendMessage(contact.number, 'Olá!');
  } catch (error) {
    console.error('Erro ao buscar contato:', error);
  }
};

// ============ INSTRUÇÕES PARA TESTAR ============
/*
1. Certifique-se que o serviço WhatsApp está rodando:
   node backend/services/whatsapp-service/index.js

2. Faça uma chamada HTTP (via curl, Postman ou fetch):

   # Fuzzy search
   curl "http://localhost:8001/api/whatsapp/contacts/search?name=joão&minSimilarity=0.6"

   # Busca exata
   curl "http://localhost:8001/api/whatsapp/contacts/search?name=João%20Silva&exactMatch=true"

   # Por número
   curl "http://localhost:8001/api/whatsapp/contacts/by-number/5511987654321"

   # Listar todos
   curl "http://localhost:8001/api/whatsapp/contacts/all"

3. No React Frontend, use qualquer um dos exemplos acima
*/
