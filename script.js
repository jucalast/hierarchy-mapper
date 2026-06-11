
const fs = require('fs');
let code = fs.readFileSync('frontend/src/hooks/useHierarchy.ts', 'utf8');

// 1. Add refs at the top
code = code.replace(
  /const hasActiveJobRef = useRef\\(false\\);/, 
  \const hasActiveJobRef = useRef(false);
    const chatContextRef = useRef({ chatPrompted: false, orgId: null, orgName: '' });
    const scanFinishedRef = useRef(true);
    const chatDoneDispatchedRef = useRef(false);\
);

// 2. Add checkAndDispatchChatEvent in hook body
code = code.replace(
  /const updateEmployee = useCallback/, 
  \
    const checkAndDispatchChatEvent = useCallback(() => {
        if (!chatContextRef.current.chatPrompted) return;
        if (!scanFinishedRef.current) return; // Ainda mapeando
        
        // Verifica se ainda há pendências
        const hasPending = currentEmployeesRef.current.some(e => {
            const r = ((e as any).role || '').toLowerCase();
            return r.includes('análise humana') || r.includes('analise humana');
        });

        if (!hasPending && !chatDoneDispatchedRef.current) {
            chatDoneDispatchedRef.current = true;
            
            // FILTRO ESTILIZADO DE REPROVADOS
            const contactsList = currentEmployeesRef.current
                .filter(e => {
                    if (e.id === 'root_company' || !e.name) return false;
                    const r = ((e as any).role || '').toLowerCase();
                    const d = ((e as any).department || '').toLowerCase();
                    if (r.includes('reprovado') || d.includes('reprovado')) return false;
                    return true;
                })
                .map(e => ({
                    name: e.name,
                    role: (e as any).role || '',
                    email: (e as any).email || undefined,
                    department: (e as any).department || undefined,
                    temperature: (e as any).temperature || undefined,
                    level: (e as any).level,
                    decision_maker: [
                        'compras', 'procurement', 'suprimentos', 'logística', 'logistica',
                        'supply chain', 'supply', 'materiais', 'aquisição', 'aquisicao',
                        'estoque', 'sourcing'
                    ].some(k => ((e as any).role || '').toLowerCase().includes(k) || ((e as any).department || '').toLowerCase().includes(k)),
                }));

            console.log('[useHierarchy] Disparando hierarchy_scan_done', contactsList.length, 'contatos validos');
            window.dispatchEvent(new CustomEvent('hierarchy_scan_done', {
                detail: {
                    orgId: chatContextRef.current.orgId,
                    orgName: chatContextRef.current.orgName,
                    chatPrompted: true,
                    contacts: contactsList,
                },
            }));
        }
    }, [currentEmployeesRef]);

    const updateEmployee = useCallback\
);

fs.writeFileSync('temp_useHierarchy.ts', code);
console.log('Done script 1');

