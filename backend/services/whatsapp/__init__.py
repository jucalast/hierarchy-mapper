"""
Pacote WhatsApp — Re-exporta módulos de integração e resolução de contatos.
Permite imports limpos: `from services.whatsapp import WhatsAppIntegration, WhatsAppResolverService`
"""
from services.whatsapp_integration import WhatsAppIntegration
from services.whatsapp_resolver import WhatsAppResolverService

__all__ = ["WhatsAppIntegration", "WhatsAppResolverService"]
