"""
core.security
=============
Autenticação JWT e hash de senhas com PBKDF2-SHA256.

O SECRET_KEY tem fallback hardcoded só para desenvolvimento. Em produção
o app loga nível ERROR no startup se o valor padrão for detectado.

Funções públicas:
    hash_password(password) -> str
    verify_password(plain, hashed) -> bool
    create_access_token(data, expires_delta) -> str

Variável de ambiente: JWT_SECRET (obrigatória em produção)
"""
import os
import hashlib
import binascii
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt

# Chave secreta de assinatura JWT
SECRET_KEY = os.getenv("JWT_SECRET", "linkb2b-super-secret-jwt-key-for-saas-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 Horas de validade padrão

def hash_password(password: str) -> str:
    """Gera o hash PBKDF2 de uma senha usando salt aleatório."""
    salt = hashlib.sha256(os.urandom(60)).hexdigest().encode('ascii')
    pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    pwdhash = binascii.hexlify(pwdhash)
    return (salt + pwdhash).decode('ascii')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha simples confere com o hash armazenado."""
    if not hashed_password:
        return False
    try:
        salt = hashed_password[:64].encode('ascii')
        stored_hash = hashed_password[64:]
        pwdhash = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt, 100000)
        pwdhash = binascii.hexlify(pwdhash).decode('ascii')
        return pwdhash == stored_hash
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Gera um Token JWT assinado contendo os dados do usuário."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
