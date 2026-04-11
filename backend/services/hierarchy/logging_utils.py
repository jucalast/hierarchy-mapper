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

def log_candidate_rejection(name, link, reason):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[FILTRO MECÂNICO] CANDIDATO: {name}\n")
        f.write(f"LINK: {link}\n")
        f.write(f"MOTIVO: 🚫 {reason}\n")
        f.write("-" * 50 + "\n\n")

def log_candidate_analysis(name, link, raw_meta, ai_result, theorg_result, final_decision):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n[PROCESSO COMPLETO] CANDIDATO: {name}\n")
        f.write(f"LINK: {link}\n")
        
        f.write("--- [METADADOS BRUTOS] ---\n")
        f.write(f"GOOGLE TITLE: {raw_meta.get('title')}\n")
        f.write(f"GOOGLE BODY: {raw_meta.get('body')}\n")
        f.write(f"LINKEDIN STATUS: {raw_meta.get('meta')}\n")
        f.write(f"LINKEDIN BIO: {raw_meta.get('bio_lkn', 'N/A')}\n")
            
        f.write("--- [CONSULTA IA] ---\n")
        f.write(f"RESULTADO: {'✅ APROVADO' if ai_result.get('is_valid') else '🚫 REJEITADO'}\n")
        f.write(f"EVIDÊNCIA: {ai_result.get('evidence', 'Sem evidência detalhada')}\n")
        
        f.write("--- [HUNT RESULT (THE ORG)] ---\n")
        f.write(f"CARGO THE ORG: {theorg_result.get('role', 'Não Encontrado')}\n")
        f.write(f"URL THE ORG: {theorg_result.get('url', 'N/A')}\n")
        
        f.write("--- [DECISÃO DA INTELIGÊNCIA ARTIFICIAL] ---\n")
        f.write(f"RESULTADO: {'✅ APROVADO' if final_decision.get('is_valid') else '🚫 REJEITADO'}\n")
        f.write(f"CARGO FINAL: {final_decision.get('role')}\n")
        f.write(f"DEPARTAMENTO: {final_decision.get('department')}\n")
        f.write(f"CONFIANÇA: {final_decision.get('matching_score')}%\n")
        if final_decision.get("evidence") and final_decision.get("evidence") != ai_result.get("evidence"):
            f.write(f"MOTIVO FINAL: {final_decision.get('evidence')}\n")
        f.write("-" * 50 + "\n")
