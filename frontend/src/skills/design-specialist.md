# 💎 Habilidade de Especialista em Design do Sistema (Design Specialist Skill)

Esta habilidade serve como a **fonte da verdade e guia de implementação** para o padrão de design visual de alta fidelidade e premium do LINKB2B Hierarchy Mapper. Ela contém a documentação exaustiva, as especificações e as regras de implementação para os quatro grandes pilares do nosso design de interface (UI): **Drawer**, **Chat Panel**, **Floating Toolbar** e **Card Node**.

Use este arquivo sempre que precisar implementar novos componentes ou estender as interfaces existentes, garantindo integração total e mantendo a estética Obsidian/Console de luxo.

---

## 🎨 1. A Filosofia de Design e o Sistema de Tokens

O design do sistema é projetado para impressionar e transmitir sofisticação profissional. Ele adota uma estética **Obsidian/Console Dark** (padrão) e um modo **Software Professional Light**.

### 🌟 Princípios Visuais Fundamentais
*   **Vidro e Transparência (Glassmorphism):** Uso controlado de opacidades, fundos desfocados (`backdrop-filter: blur()`) e bordas ultrafinas para sobreposições flutuantes.
*   **Micro-Animações Reativas:** Efeitos de hover suaves com transições `cubic-bezier(0.16, 1, 0.3, 1)` que dão sensação de vida e fluidez.
*   **Tipografia Hierárquica:** Tipografia limpa escalada do tamanho base `15px` até `48px`, usando fontes modernas e arredondadas (como Google Sans, Nexa e Inter).
*   **Contraste e Foco Semântico:** As cores principais são neutras e escuras, enquanto os estados ativos, aprovações e categorias se destacam em tons de lavanda, verde esmeralda e ciano.

### 🔑 Tokens CSS Globais (da raiz `:root` em globals.css)
*   `--sw-bg`: Cor de fundo da aplicação (Preto Obsidian `#0c0d0e` / Branco `#ffffff`).
*   `--sw-sidebar`: Fundo de painéis laterais fixos (`#131313` / `#ffffff`).
*   `--sw-surface-base` / `--sw-surface-raised`: Superfícies de cards e elementos de UI.
*   `--sw-border` / `--sw-border-strong`: Linhas de contorno (`rgba(255,255,255,0.08)` / `rgba(255,255,255,0.15)`).
*   `--sw-border-width`: Espessura padrão de borda (`1.5px`).
*   `--sw-primary`: Cor de destaque do sistema (Lavanda/Índigo `#818cf8` / `#4f46e5`).
*   `--sw-primary-soft`: Destaques suaves translúcidos (`rgba(129, 140, 248, 0.12)`).
*   `--sw-text-base` / `--sw-text-muted`: Níveis hierárquicos de texto.
*   `--radius-md` (12px) e `--radius-lg` (16px): Arredondamentos primários de bordas.

---

## 📦 2. Os Quatro Pilares de UI do Sistema

### 🚪 A. O Drawer (Painel de Detalhes Lateral)
O **Drawer** é o painel deslizante que contém informações ricas sobre a empresa selecionada ou listas de navegação.

*   **Estrutura Física:**
    *   Largura fixa (`360px`), `height: 100%`, `flex-shrink: 0`, acoplado lateralmente.
    *   Animação de entrada `swSlideIn` de 0.3s que translada o painel suavemente a partir de `translateX(-20px)`.
*   **Componentes Internos e Padrão Visual:**
    *   **Header:** Barra superior contendo botão voltar de design minimalista, input de busca integrado de estilo cápsula translúcida com ícone do lado esquerdo e ações de controle de estado do lado direito.
    *   **Tabs (Navegação Interna):** Botões de abas horizontais com espaçamento largo (`gap: 28px`), peso de fonte `500` para a aba ativa e um sublinhado azul/lavanda (`--sw-primary`) criado via pseudo-elemento `::after` com transição suave.
    *   **Lists e Badges:** Listagem de sub-itens com hover suave, efeito de borda esquerda reativa (`box-shadow: inset 3px 0 0 0 var(--sw-primary)`). Avatares empilhados para colaboradores e badges semânticos translúcidos para status (ex: `mappedBadge`, `empCountBadge`).
*   **Exemplo de CSS de Estrutura:**
    ```css
    .drawer {
        height: 100%;
        width: 360px;
        background: var(--sw-sidebar);
        border-right: var(--sw-border-width) solid var(--sw-border);
        display: flex;
        flex-direction: column;
        animation: swSlideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .mainNavActive::after {
        content: '';
        position: absolute;
        bottom: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: var(--sw-primary);
    }
    ```

---

### 💬 B. O Chat Panel (Painel de Conversação com Agente)
O **Chat Panel** é o ambiente interativo de comunicação com os agentes de IA. Ele combina logs de terminal, diálogos humanos e blocos de aprovação de fluxo de trabalho.

*   **Estrutura de Balões (Bubbles):**
    *   Mensagens do Usuário: Alto contraste (`--chat-user-msg-bg`: `#ffffff` com texto preto no modo escuro) com arredondamento assimétrico (mais agudo no canto inferior direito).
    *   Mensagens da IA: Fundo translúcido escuro (`rgba(255,255,255,0.05)`) com borda fina (`var(--chat-border-weak)`).
*   **Componentes de Integração de Fluxo (ActionApproval & ContextModules):**
    *   Cards de Ação / Aprovação: Bordas arredondadas de `12px`, fundo `--sw-surface-raised` e botões de ação reativos.
    *   Efeito de Waveform de Áudio e Log de Transações em formato de terminal (mono-espaçado, cores verdes e laranjas reativas para monitoramento em tempo real).
*   **Tokens Específicos (`chat-tokens.css`):**
    *   Sempre use as variáveis `--chat-` baseadas nos equivalentes `--sw-` para manter o chat perfeitamente sintonizado com o tema ativo.

---

### 🛸 C. A Floating Toolbar (Barra de Inteligência Flutuante)
A **Floating Toolbar** é uma barra de ferramentas suspensa de alta tecnologia que sobrepõe o mapa ou grafo de rede. Ela atua como a central de busca (CNPJ, domínios, etc.).

*   **Estrutura Física e Posicionamento:**
    *   Elemento posicionado de forma absoluta no fundo da tela (`position: absolute`, `bottom: 24px`, `left: 50%`, `transform: translateX(-50%)`).
    *   Alinhamento inteligente: Reage à abertura de painéis laterais (ex: se o chat estiver aberto, move-se ligeiramente usando variáveis de transição para evitar sobreposição).
*   **Estilo Visual Glassmorphic:**
    *   Fundo ultrafino de vidro translúcido (`backdrop-filter: blur(12px)`), sombra proeminente (`var(--sw-shadow)`) e borda contornando.
*   **Dual-Row Mode (Formulário Avançado de Confirmação):**
    *   Possui dois modos: modo de busca simples (uma linha com campos divididos por pequenos filetes verticais transparentes `.toolbarDivider`) e modo expandido (duas linhas organizadas quando uma empresa é capturada, mostrando o logo da marca e botões de ação como "Mapear" e seletores de área).
*   **Efeitos Especiais de Atenção:**
    *   `inputAttention`: Quando campos críticos estão vazios, o campo pulsa com uma borda sutil avermelhada ou amarela de atenção.
    *   `cleanSearchLoading`: Botões de IA rodam o ícone de carregamento infinitamente com a animação `swSpin`.

---

### 🃏 D. O Card Node (Nódulo de Grafo / Compact Card)
O **Card Node** é a unidade fundamental de representação visual de contatos, leads e funcionários dentro do grafo de hierarquia.

*   **Estética Zero-Background:**
    *   Diferente de cards tradicionais pesados, o nódulo do grafo adota fundo **transparente** ou translúcido e foca a atenção no contorno do contorno (`var(--sw-border-width) solid var(--sw-border)`) e na excelente tipografia.
*   **Identificação por Nível de Senioridade (Seniority Hierarchy):**
    *   Cada nível hierárquico possui uma cor e tag de texto dedicada para visualização rápida:
        *   **Board / C-Level (Level 6/5):** Lavanda/Azul Claro (`#7A8BFF` / `#60A5FA`).
        *   **Diretor / Gerente (Level 4/3):** Ciano / Verde Esmeralda (`#2DD4BF` / `#4ADE80`).
        *   **Coordenador / Especialista (Level 2/1):** Amarelo Ouro / Cinza Neutro (`#FBBF24` / `#A1A1AA`).
    *   O cargo é sempre renderizado em letras menores e cor secundária, garantindo contraste correto.
*   **Avatares Redondos e Clean:**
    *   Molduras de avatares com borda fina e suporte automático a fallback de letras com cores harmoniosas se a foto do contato não estiver disponível.

---

## 🛠️ 3. Guia de Implementação Passo a Passo para Novos Componentes

Quando for criar um novo componente (exemplo: `ContactScheduler.tsx`), siga esta receita para integrá-lo perfeitamente ao padrão do sistema:

### Passo 1: Use CSS Modules e Importe Globais
Nunca use cores hexadecimais explícitas ou Tailwind cru no CSS. Mapeie diretamente as variáveis globais.

```css
/* ContactScheduler.module.css */
.schedulerContainer {
    background: var(--sw-surface-base);
    border: var(--sw-border-width) solid var(--sw-border);
    border-radius: var(--radius-md);
    padding: 16px;
    box-shadow: var(--sw-shadow);
    transition: var(--transition-fast);
}

.schedulerContainer:hover {
    border-color: var(--sw-primary-border);
    background: var(--sw-hover);
}
```

### Passo 2: Implemente a Animação de Entrada Reativa
Adicione animações de transição suave em seu componente usando os keyframes globais definidos em `globals.css`:

```tsx
// ContactScheduler.tsx
import React from 'react';
import styles from './ContactScheduler.module.css';

export const ContactScheduler: React.FC = () => {
    return (
        <div className={`${styles.schedulerContainer} animate-fadeIn`}>
            {/* Cabeçalho no padrão DrawerHeader */}
            <div className={styles.header}>
                <h3 className={styles.title}>Agendar Contato</h3>
            </div>
        </div>
    );
};
```

### Passo 3: Use os Ícones e Padrões de Botão do Sistema
*   **Ícones:** Utilize a biblioteca `lucide-react`. Sempre passe tamanhos consistentes (`14px` ou `16px` para botões, `20px` para barras).
*   **Botões de Ação:** Siga a lógica dos botões do Pipedrive e da Toolbar. Ações primárias recebem preenchimento `--sw-primary-soft` e mudam para `--sw-primary` no hover. Ações secundárias são transparentes com hover sutil.

---

## 📋 4. Lista de Verificação (Checklist) do Especialista

Antes de declarar um novo componente como pronto, valide-o contra os seguintes critérios:

*   [ ] **Modo Escuro / Claro:** O componente suporta alternância dinâmica de temas sem quebrar contrastes de fontes? (Testar usando variáveis `--sw-text-base` e `--sw-text-subtle`).
*   [ ] **Curva de Animação:** Os hovers utilizam `cubic-bezier(0.16, 1, 0.3, 1)` com duração entre `0.2s` e `0.3s`?
*   [ ] **Bordas Coerentes:** A espessura da borda é controlada por `var(--sw-border-width)`? (Isso evita disparidade visual de linhas finas e grossas).
*   [ ] **Sem Cantos Afiados:** Todos os elementos utilizam os raios de arredondamento oficiais (`--radius-sm`, `--radius-md` ou `--radius-lg`)?
*   [ ] **Responsividade Flutuante:** Elementos sobrepostos possuem `backdrop-filter: blur(...)` para garantir legibilidade sobre o mapa ou grafo?

---

### 📣 Como Chamar esta Habilidade
Sempre que for instruir um agente a construir um novo módulo ou componente, inicie o comando referenciando esta habilidade:
> *"Implemente o componente [NOME] seguindo estritamente as diretrizes contidas no arquivo de habilidade `frontend/src/skills/design-specialist.md` para garantir total aderência ao ecossistema visual de Drawer, ChatPanel, FloatingToolbar e CardNode."*
