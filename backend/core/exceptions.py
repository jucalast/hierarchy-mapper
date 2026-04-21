"""
Exceções de negócio padronizadas para respostas consistentes.
"""
from fastapi import HTTPException


class ServiceUnavailableError(HTTPException):
    """Serviço externo indisponível (WhatsApp, Pipedrive, etc)."""
    def __init__(self, service_name: str, detail: str = None):
        super().__init__(
            status_code=503,
            detail=detail or f"Serviço '{service_name}' indisponível no momento."
        )


class AIProcessingError(HTTPException):
    """Falha no processamento de IA (todas as opções esgotadas)."""
    def __init__(self, detail: str = None):
        super().__init__(
            status_code=500,
            detail=detail or "Erro ao processar inteligência artificial."
        )


class ContactNotFoundError(HTTPException):
    """Contato não encontrado no WhatsApp/Pipedrive/DB."""
    def __init__(self, identifier: str = ""):
        super().__init__(
            status_code=404,
            detail=f"Contato não encontrado: {identifier}" if identifier else "Contato não encontrado."
        )


class OrganizationNotFoundError(HTTPException):
    """Organização não encontrada no banco."""
    def __init__(self, identifier: str = ""):
        super().__init__(
            status_code=404,
            detail=f"Organização não encontrada: {identifier}" if identifier else "Organização não encontrada."
        )
