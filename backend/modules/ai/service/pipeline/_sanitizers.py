"""
Funções de limpeza e sanitização de texto para o pipeline de IA.
Extraídas de data_fetcher.py para manter a responsabilidade única.
"""


def sanitize_email_body(body: str) -> str:
    """
    Limpeza robusta de e-mails para reduzir ruído e tokens antes de injetar no LLM.

    Etapas:
        1. Remove tags HTML
        2. Corta no primeiro delimitador de resposta (From:, De:, ---Original---, etc.)
        3. Remove links e linhas de disclaimer
        4. Normaliza espaços e limita a 800 caracteres
    """
    if not body:
        return ""
    import re

    body = re.sub(r'<[^>]+>', ' ', body)

    delimiters = [
        "________________________________", "From:", "De:", "Enviada:", "Subject:", "Assunto:",
        "--- Mensagem Original ---", "Sent from my iPhone", "Enviado do meu iPhone",
        "Obter o Outlook para", "Get Outlook for"
    ]
    for d in delimiters:
        if d in body:
            body = body.split(d)[0]

    body = re.sub(r'https?://[^\s]+', '', body)
    disclaimers = ["confidencial", "destinatário", "notify the sender", "error in transmission", "legal notice"]
    lines = body.split('\n')
    clean_lines = [l for l in lines if not any(d in l.lower() for d in disclaimers) and len(l.strip()) > 2]

    text = " ".join(clean_lines)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()[:800]
