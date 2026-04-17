import os
from datetime import datetime

LOG_FILE = "../engine_raw.log"

def log_session_start(brand, location, focus):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + "="*80 + "\n")
        f.write(f"SESSÃO: {brand.upper()} | LOCAL: {location.upper() if location else 'BRASIL'} | FOCO: {focus.upper() if focus else 'GERAL'}\n")
        f.write(f"DATA: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n\n")

def log_query_start(query):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n" + "="*30 + "\n")
        f.write(f"🔍 NOVA CONSULTA: {query}\n")
        f.write("="*30 + "\n\n")

def log_candidate_rejection(name, link, reason, stage="FILTRO MECÂNICO"):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{stage}] CANDIDATO: {name}\n")
        f.write(f"LINK: {link}\n")
        f.write(f"MOTIVO: 🚫 {reason}\n")
        f.write("-" * 50 + "\n\n")

def log_candidate_analysis(name, link, raw_meta, ai_result, theorg_result, final_decision):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n" + "·"*80 + "\n")
        f.write(f"🔍 [ANÁLISE DE PERFIL] CANDIDATO: {name}\n")
        f.write(f"🔗 LINKEDIN: {link}\n")
        f.write("·"*80 + "\n")
        
        # FASE 4: FÁBRICA DE CANDIDATOS (DADOS BRUTOS)
        f.write("\n📦 FASE 4: CANDIDATE PROCESSOR (DADOS BRUTOS)\n")
        f.write(f"   ∟ [SEARCH SNIPPET] TITLE: {raw_meta.get('title')}\n")
        f.write(f"   ∟ [SEARCH SNIPPET] BODY: {raw_meta.get('body')}\n")
        f.write(f"   ∟ [THE ORG CHECK]: {'✅ ENCONTRADO' if theorg_result.get('role') != 'Não Encontrado' else '❌ NÃO CONSTA'}\n")
        if theorg_result.get('role') != 'Não Encontrado':
            f.write(f"      ∟ CARGO OFICIAL: {theorg_result.get('role')}\n")
        
        f.write(f"   ∟ [METADATA ENRICHMENT] (PREVIEW SILENCIOSO):\n")
        f.write(f"      ∟ META ROLE (LKN): {raw_meta.get('meta')}\n")
        f.write(f"      ∟ MECHANICAL ROLE: {raw_meta.get('mechanical_role', 'N/D')}\n")
        f.write(f"      ∟ BIO/DESCRIPTION: {raw_meta.get('bio_lkn', 'N/A')}\n")
            
        # FASE 5: PIPELINE DE INTELIGÊNCIA IA
        f.write("\n🧠 FASE 5: PIPELINE DE INTELIGÊNCIA IA (4 ESTÁGIOS)\n")
        
        # 1. SNIPER
        clean_data = ai_result.get("clean_data", {})
        target = clean_data.get("target_profile", {})
        others = clean_data.get("all_mappings", [])
        
        f.write(f"   🎯 [ESTÁGIO 1: SNIPER] (HIGIENIZAÇÃO):\n")
        if clean_data:
            f.write(f"      ∟ ALVO ISOLADO: {target.get('name')} | CARGO: {target.get('detected_role')}\n")
            f.write(f"      ∟ BIO PROCESSADA: {target.get('clean_bio', 'N/A')[:150]}...\n")
            if len(others) > 1:
                f.write(f"      ∟ OUTROS PERFIS NO RUÍDO: {len(others)-1} detectados\n")
        else:
            f.write("      ∟ FALHA NA HIGIENIZAÇÃO\n")

        # 2. DETETIVE
        facts = ai_result.get("facts", {})
        f.write(f"   🕵️ [ESTÁGIO 2: DETETIVE] (EXTRAÇÃO DE FATOS):\n")
        if facts:
            f.write(f"      ∟ EMPRESA ATUAL CONFIRMADA: {'SIM' if facts.get('employer_found') else 'NÃO/INCERTO'}\n")
            f.write(f"      ∟ SNIPPETS RELEVANTES: {', '.join(facts.get('snippets', []))[:200]}...\n")
            f.write(f"      ∟ PERFIL INSTITUCIONAL: {'⚠️ SIM' if facts.get('is_institutional') else 'NÃO'}\n")
        else:
            f.write("      ∟ SEM FATOS EXTRAÍDOS\n")

        # 3. ESPECIALISTA
        spec = ai_result.get("specialist", {})
        f.write(f"   👔 [ESTÁGIO 3: ESPECIALISTA RH] (REFINO TÉCNICO):\n")
        if spec:
            f.write(f"      ∟ DEPARTAMENTO: {spec.get('dept')}\n")
            f.write(f"      ∟ RELEVANTE: {'SIM' if spec.get('is_relevant') else 'NÃO'}\n")
            f.write(f"      ∟ MOTIVO: {spec.get('reasoning')}\n")
        else:
            f.write(f"      ∟ DEPARTAMENTO SUGERIDO: {final_decision.get('department')}\n")
            f.write(f"      ∟ RELEVANTE PARA O FOCO: {'SIM' if final_decision.get('is_valid') else 'NÃO'}\n")

        # 4. JUIZ (VEREDITO)
        f.write(f"   ⚖️ [ESTÁGIO 4: JUIZ FINAL] (VEREDITO):\n")
        f.write(f"      ∟ RESULTADO: {'✅ APROVADO' if final_decision.get('is_valid') else '❌ REJEITADO'}\n")
        f.write(f"      ∟ CARGO FINAL: {final_decision.get('role')}\n")
        f.write(f"      ∟ SCORE DE MATCHING: {final_decision.get('matching_score')}%\n")
        f.write(f"      ∟ EVIDÊNCIA DO JUIZ: {ai_result.get('evidence', 'Sem detalhes')}\n")

        if "REPESCAGEM" in str(ai_result.get('evidence', '')):
            f.write("\n🔄 [AUTO-REPESCAGEM] Ativada (Investigação Profunda realizada).\n")
        elif "INVESTIGADO" in str(ai_result.get('evidence', '')):
            f.write("\n🔄 [AUTO-REPESCAGEM] Ativada (Investigação Profunda realizada).\n")

        f.write("\n" + "—"*50 + "\n")

def register_raw_data(name, link, raw_meta, ai_result, theorg_result, final_decision):
    """
    Grava os dados brutos estruturados em um arquivo JSONL para auditoria posterior.
    """
    import json
    RAW_DATA_FILE = "../raw_data_registry.jsonl"
    
    raw_payload = {
        "timestamp": datetime.now().isoformat(),
        "candidate": name,
        "linkedin": link,
        "raw_inputs": {
            "search_snippets": {
                "title": raw_meta.get('title'),
                "body": raw_meta.get('body')
            },
            "osint_metadata": {
                "role": raw_meta.get('meta'),
                "bio": raw_meta.get('bio_lkn')
            },
            "theorg": theorg_result
        },
        "ai_pipeline": ai_result,
        "final_decision": final_decision
    }
    
    try:
        os.makedirs(os.path.dirname(RAW_DATA_FILE), exist_ok=True)
        with open(RAW_DATA_FILE, "a", encoding="utf-8") as rf:
            rf.write(json.dumps(raw_payload, indent=4, ensure_ascii=False) + "\n")
            rf.write("-" * 80 + "\n") # Separador para facilitar leitura visual
    except Exception as e:
        print(f"      [Logging] ⚠️ Erro ao registrar dados brutos: {e}")

def log_candidate_analysis(name, link, raw_meta, ai_result, theorg_result, final_decision):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n" + "·"*80 + "\n")
        f.write(f"🔍 [ANÁLISE DE PERFIL] CANDIDATO: {name}\n")
        f.write(f"🔗 LINKEDIN: {link}\n")
        f.write("·"*80 + "\n")
        
        # FASE 4: FÁBRICA DE CANDIDATOS (DADOS BRUTOS)
        f.write("\n📦 FASE 4: CANDIDATE PROCESSOR (DADOS BRUTOS)\n")
        f.write(f"   ∟ [SEARCH SNIPPET] TITLE: {raw_meta.get('title')}\n")
        f.write(f"   ∟ [SEARCH SNIPPET] BODY: {raw_meta.get('body')}\n")
        f.write(f"   ∟ [THE ORG CHECK]: {'✅ ENCONTRADO' if theorg_result.get('role') != 'Não Encontrado' else '❌ NÃO CONSTA'}\n")
        if theorg_result.get('role') != 'Não Encontrado':
            f.write(f"      ∟ CARGO OFICIAL: {theorg_result.get('role')}\n")
        
        f.write(f"   ∟ [METADATA ENRICHMENT] (PREVIEW SILENCIOSO):\n")
        f.write(f"      ∟ ROLE DETECTED: {raw_meta.get('meta')}\n")
        f.write(f"      ∟ BIO/DESCRIPTION: {raw_meta.get('bio_lkn', 'N/A')}\n")
            
        # FASE 5: PIPELINE DE INTELIGÊNCIA IA
        f.write("\n🧠 FASE 5: PIPELINE DE INTELIGÊNCIA IA (4 ESTÁGIOS)\n")
        
        # 1. SNIPER
        clean_data = ai_result.get("clean_data", {})
        target = clean_data.get("target_profile", {})
        others = clean_data.get("all_mappings", [])
        
        f.write(f"   🎯 [ESTÁGIO 1: SNIPER] (HIGIENIZAÇÃO):\n")
        if clean_data:
            f.write(f"      ∟ ALVO ISOLADO: {target.get('name')} | CARGO: {target.get('detected_role')}\n")
            f.write(f"      ∟ BIO PROCESSADA: {target.get('clean_bio', 'N/A')[:150]}...\n")
            if len(others) > 1:
                f.write(f"      ∟ OUTROS PERFIS NO RUÍDO: {len(others)-1} detectados\n")
        else:
            f.write("      ∟ FALHA NA HIGIENIZAÇÃO\n")

        # 2. DETETIVE
        facts = ai_result.get("facts", {})
        f.write(f"   🕵️ [ESTÁGIO 2: DETETIVE] (EXTRAÇÃO DE FATOS):\n")
        if facts:
            f.write(f"      ∟ EMPRESA ATUAL CONFIRMADA: {'SIM' if facts.get('employer_found') else 'NÃO/INCERTO'}\n")
            f.write(f"      ∟ SNIPPETS RELEVANTES: {', '.join(facts.get('snippets', []))[:200]}...\n")
            f.write(f"      ∟ PERFIL INSTITUCIONAL: {'⚠️ SIM' if facts.get('is_institutional') else 'NÃO'}\n")
        else:
            f.write("      ∟ SEM FATOS EXTRAÍDOS\n")

        # 3. ESPECIALISTA
        spec = ai_result.get("specialist", {})
        f.write(f"   👔 [ESTÁGIO 3: ESPECIALISTA RH] (REFINO TÉCNICO):\n")
        if spec:
            f.write(f"      ∟ DEPARTAMENTO: {spec.get('dept')}\n")
            f.write(f"      ∟ RELEVANTE: {'SIM' if spec.get('is_relevant') else 'NÃO'}\n")
            f.write(f"      ∟ MOTIVO: {spec.get('reasoning')}\n")
        else:
            f.write(f"      ∟ DEPARTAMENTO SUGERIDO: {final_decision.get('department')}\n")
            f.write(f"      ∟ RELEVANTE PARA O FOCO: {'SIM' if final_decision.get('is_valid') else 'NÃO'}\n")

        # 4. JUIZ (VEREDITO)
        f.write(f"   ⚖️ [ESTÁGIO 4: JUIZ FINAL] (VEREDITO):\n")
        f.write(f"      ∟ RESULTADO: {'✅ APROVADO' if final_decision.get('is_valid') else '❌ REJEITADO'}\n")
        f.write(f"      ∟ CARGO FINAL: {final_decision.get('role')}\n")
        f.write(f"      ∟ SCORE DE MATCHING: {final_decision.get('matching_score')}%\n")
        f.write(f"      ∟ EVIDÊNCIA DO JUIZ: {ai_result.get('evidence', 'Sem detalhes')}\n")

        if "REPESCAGEM" in str(ai_result.get('evidence', '')):
            f.write("\n🔄 [AUTO-REPESCAGEM] Ativada (Investigação Profunda realizada).\n")
        elif "INVESTIGADO" in str(ai_result.get('evidence', '')):
            f.write("\n🔄 [AUTO-REPESCAGEM] Ativada (Investigação Profunda realizada).\n")

        f.write("\n" + "—"*50 + "\n")

    # Chama o novo registro de dados brutos
    register_raw_data(name, link, raw_meta, ai_result, theorg_result, final_decision)


