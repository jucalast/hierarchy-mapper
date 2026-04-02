import os
import re
import httpx
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

class RoleEngine:
    def __init__(self):
        # Unificando o nome da chave para evitar conflitos
        self.api_key = os.getenv("GROQ_API_KEY")
        self.model = "llama-3.1-8b-instant" # 🏎️ Rápido e evita 429 Rate Limit
        self.job_keywords = [
            "comprador", "buyer", "procurement", "supply chain", "gerente", "manager", "diretor", "director",
            "coordenador", "coordinator", "analista", "analyst", "supervisor", "specialist", "especialista",
            "logística", "logistics", "compras", "sourcing", "planner", "planejamento", "head", "vp", "chief",
            "engineer", "engenheiro", "assistant", "assistente", "auxiliar", "strategic sourcing"
        ]

    def _is_junk_slogan(self, text: str) -> bool:
        """Verifica se o texto extraído parece ser um slogan ou frase de marketing em vez de um cargo."""
        if not text: return False
        
        # Slogans comuns ou frases de marketing identificadas
        junk_patterns = [
            r"move o futuro", r"better way", r"discover more", r"new episode", r"parceria que",
            r"história de", r"conheça a", r"saiba mais", r"welcome to", r"prazer em",
            r"transforming the", r"shaping the", r"building a", r"pioneering",
            r"creative solutions", r"innovation for", r"driving excellence"
        ]
        
        text_norm = text.lower()
        if any(re.search(p, text_norm) for p in junk_patterns):
            return True
            
        # Se contiver verbos de ação na primeira pessoa ou imperativo (comum em slogans)
        if re.search(r"\b(venha|conheça|descubra|veja|assista|leia|participe|junte-se)\b", text_norm):
            return True
            
        return False

    async def distill_role(self, name: str, company: str, texts: List[str], query: str = "") -> str:
        """Usa a Groq AI (Llama-3.3-70b) para purificar o cargo de forma inteligente."""
        
        # 1. Limpeza e Consolidação de Textos (Remove lixo HTML e espaços extras)
        clean_sources = [re.sub(r'<[^>]*>', ' ', t).strip() for t in texts if t]
        combined_text = " | ".join(clean_sources)
        combined_text = re.sub(r'\s+', ' ', combined_text)[:5000] # Janela de 5000 caracteres
        
        if not combined_text or len(combined_text) < 10:
            # Se não há texto nenhum, tentamos deduzir apenas pela query
            if query:
                print(f"      [RoleEngine] Snippet vazio, deduzindo pela query: {query}")
                # Pega a última parte da query (geralmente o cargo buscado)
                q_clean = re.sub(r"(?i)(site:br\.linkedin\.com/in/|site:br\.linkedin\.com)","", query).strip()
                return q_clean.split()[-1].title()
            return "Professional"

        # TENTATIVA 1: GROQ AI (Llama-3.3-70b) - O Caminho de Ouro
        if self.api_key:
            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    prompt = (
                        f"Identify the professional job title for {name} who is affiliated with {company}.\n"
                        f"Search Query Context: '{query}'\n\n"
                        f"Rules:\n"
                        f"1. EXTRACT ONLY the CURRENT professional job title.\n"
                        f"2. CRITICAL: DO NOT use marketing slogans, company missions, or generic sentences (e.g., 'A Parceria Que Move o Futuro', 'The better way', 'Discover more', or 'Our new episode').\n"
                        f"3. DO NOT return generic words like 'Professional' or 'Employee'.\n"
                        f"4. If the data is noisy, use the Search Query keywords to deduce the role (e.g., if query has 'Comprador', the role is likely 'Comprador' or 'Buyer').\n"
                        f"5. Return ONLY the title (1-4 words). No introductions. No slogans.\n\n"
                        f"SNIPPET DATA: {combined_text}"
                    )
                    
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": self.model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0,
                            "max_tokens": 40
                        }
                    )
                    
                    if resp.status_code == 200:
                        result = resp.json()
                        extracted = result['choices'][0]['message']['content'].strip().strip('"').strip("'")
                        
                        # 🛡️ FILTRO DE SANIDADE ANTI-SLOGAN: Se parecer uma frase, não é um cargo!
                        is_slogan = self._is_junk_slogan(extracted) or any(x.lower() in extracted.lower() for x in ["episode", "partnership", "parceria", "missão", "mission", "future", "futuro", "conheça", "welcome", "prazer"])
                        is_sentence = len(extracted.split()) > 6 or "," in extracted or "." in extracted
                        
                        if len(extracted) > 3 and not is_slogan and not is_sentence:
                            # Limpeza final (Remove localidade ou empresa que a IA possa ter grudado)
                            extracted = re.sub(rf"(?i)\s+(at|na|no|em|da|do|atualmente)\s+.*$", "", extracted).strip()
                            print(f"   [IA] ✨ Cargo Purificado: {extracted}")
                            return extracted
                        else:
                            print(f"      [RoleEngine] IA retornou ruído ('{extracted}'), usando fallback de query.")
            except Exception as e:
                print(f"[RoleEngine] Groq AI Error: {e}")

        # --- [ TENTATIVA 2: FALLBACK HEURÍSTICO (Algoritmo de Seleção) ] ---
        # Se a IA estiver fora de combate, usamos nossa lógica estatística
        candidates = []
        noise_tags = ["<", ">", "class=", "div", "header", "span"]
        
        for source in clean_sources: 
            parts = re.split(r'[|·•\-\n:]', source)
            for p in parts:
                p = p.strip()
                if any(nt in p.lower() for nt in noise_tags): continue
                
                # Busca de cargo baseada em palavras-chave
                found_kw = False
                for kw in self.job_keywords:
                    if re.search(rf"\b{re.escape(kw)}\b", p.lower()):
                        found_kw = True
                        break
                
                if found_kw:
                    # Limpeza final (Remove nome da empresa e do colaborador se vazarem pro cargo)
                    p = re.sub(rf"(?i)\s+(at|na|no|em|da|do|trabalha na|atualmente na)(\s+.*|$)", "", p).strip()
                    if len(p) > 3 and len(p) < 60:
                        candidates.append(p)

        if candidates:
            # Retorna o candidato mais provável (maior e com bônus de senioridade)
            return max(candidates, key=lambda x: len(x) + (10 if any(k in x.lower() for k in ["pleno", "senior", "gerente"]) else 0))

        return "Professional"

# Instância Singleton
role_engine = RoleEngine()
