"""Serviços de email: cliente Outlook/SMTP e scheduler IMAP."""
from .client import EmailClient
from .scheduler import start_email_scheduler, stop_email_scheduler

__all__ = ["EmailClient", "start_email_scheduler", "stop_email_scheduler"]
