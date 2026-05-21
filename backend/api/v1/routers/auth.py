import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.infra.database import get_db
from core.observability.logging_config import get_logger
from core.security import verify_password, create_access_token, SECRET_KEY, ALGORITHM
from models import User, Tenant

log = get_logger(__name__)

router = APIRouter()

# OAuth2 scheme config (allows Swagger UI integration)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

class LoginPayload(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str
    user_name: str
    user_email: str
    user_role: str
    tenant_id: str
    tenant_name: str

@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginPayload, session: AsyncSession = Depends(get_db)):
    """Realiza o login do usuário e gera o token de acesso SaaS JWT."""
    stmt = select(User).where(User.email == payload.email)
    res = await session.execute(stmt)
    user = res.scalars().first()
    
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos."
        )
        
    # Carrega o Tenant associado
    tenant_stmt = select(Tenant).where(Tenant.id == user.tenant_id)
    tenant_res = await session.execute(tenant_stmt)
    tenant = tenant_res.scalars().first()
    
    # Prepara os dados de reivindicação JWT
    token_data = {
        "sub": user.email,
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "role": user.user_role
    }
    
    token = create_access_token(token_data)
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user.id,
        user_name=user.name,
        user_email=user.email,
        user_role=user.user_role,
        tenant_id=user.tenant_id,
        tenant_name=tenant.name if tenant else "Default Tenant"
    )

async def get_current_user_from_token(token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_db)) -> User:
    """Dependência para extrair e autenticar o usuário ativo pelo token JWT."""
    if not token:
        if not settings.is_development:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de autenticação obrigatório.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Fallback apenas em desenvolvimento: retorna o primeiro usuário cadastrado.
        log.warning("auth.no_token.dev_fallback")
        res = await session.execute(select(User).limit(1))
        user = res.scalars().first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Nenhum usuário cadastrado no banco de dados."
            )
        return user

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido ou sessão expirada.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    stmt = select(User).where(User.id == user_id)
    res = await session.execute(stmt)
    user = res.scalars().first()
    
    if user is None:
        raise credentials_exception
        
    return user

@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user_from_token), session: AsyncSession = Depends(get_db)):
    """Retorna as informações do perfil do usuário autenticado."""
    tenant_stmt = select(Tenant).where(Tenant.id == current_user.tenant_id)
    tenant_res = await session.execute(tenant_stmt)
    tenant = tenant_res.scalars().first()
    
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "user_role": current_user.user_role,
        "tenant_id": current_user.tenant_id,
        "tenant_name": tenant.name if tenant else "Default Tenant"
    }
