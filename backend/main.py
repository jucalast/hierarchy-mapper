from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.v1.api import api_router
from api.v1.endpoints.communication import router as comm_router
from core.rate_limiter import limiter
from services.communication.scheduler import start_email_scheduler
# Backend Reload - Neon Official Key Fix (ssl=true).

app = FastAPI(
    title="Hierarchy API",
    description="API for fetching company employee hierarchy and building supply chain networks.",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all since this will be integrated elsewhere
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiter setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.on_event("startup")
async def startup_event():
    print("[Server] Inicializando Componentes de Inteligencia...")
    start_email_scheduler()
    try:
        from core.database import init_db
        await init_db()
    except Exception as e:
        import traceback
        print(f"[Database] Erro Critico de Conexao no Neon DB: {str(e)}")
        traceback.print_exc()

# Include Communication Router
app.include_router(comm_router, prefix="/api/v1/communication", tags=["communication"])

@app.on_event("shutdown")
async def shutdown_event():
    print("[Server] Desligando e limpando conexoes...")
    try:
        from core.database import engine
        await engine.dispose()
        print("[Database] Conexoes com o banco encerradas com seguranca.")
    except:
        pass

# Include API routes
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
@limiter.limit("10/minute")
def read_root(request: Request):
    return {"message": "Welcome to the Hierarchy API"}
