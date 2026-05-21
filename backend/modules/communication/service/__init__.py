"""Camada de serviços de comunicação."""
from .email import EmailClient, start_email_scheduler, stop_email_scheduler
from .whatsapp import *

__all__ = ["EmailClient", "start_email_scheduler", "stop_email_scheduler"]
