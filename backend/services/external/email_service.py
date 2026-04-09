import re
import socket
import smtplib
from typing import List

def verify_email(email: str) -> bool:
    """
    Validação de email genérica sem dependências de APIs externas.
    Usa validação sintática + verificação de domínio + SMTP check (opcional).
    """
    if not email or '@' not in email:
        return False
    
    # Validação sintática básica
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    
    domain = email.split('@')[1]
    
    try:
        # Verifica se o domínio existe
        socket.gethostbyname(domain)
        # ⚠️ Verificação SMTP foi removida pois gerava Timeout e gargalos no processamento em lote
        return True
            
    except socket.gaierror:
        return False
    
    return True

def get_permutations(first: str, last: str, domain: str) -> List[tuple]:
    """Retorna formatos possíveis e seu identificador de padrão."""
    return [
        (f"{first}.{last}@{domain}", "first.last"),
        (f"{first[0]}{last}@{domain}", "f_last"),
        (f"{first}{last}@{domain}", "firstlast"),
        (f"{first}@{domain}", "first")
    ]

def apply_pattern(first: str, last: str, domain: str, pattern: str) -> str:
    """Aplica o padrão vencedor a um novo funcionário."""
    if pattern == "first.last": return f"{first}.{last}@{domain}"
    if pattern == "f_last": return f"{first[0]}{last}@{domain}"
    if pattern == "firstlast": return f"{first}{last}@{domain}"
    if pattern == "first": return f"{first}@{domain}"
    return f"{first}.{last}@{domain}" # default
