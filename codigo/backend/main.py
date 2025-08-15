from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
import os
import time

# IMPORTANTE: Importe também o módulo history
from routes import chat, upload, history

# Carrega as variáveis de ambiente
load_dotenv()

# Cria a aplicação FastAPI
app = FastAPI(
    title="AskFile API", 
    description="API para consultas inteligentes em PDFs - Processamento temporário de arquivos",
    version="2.0.0"
)

# Configuração do CORS - CORRIGIDA para todos os domínios Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://askfile.vercel.app",
        "https://askfile-seven.vercel.app",
        "https://askfile-*.vercel.app",
        "https://*.vercel.app",
        "https://askfile.onrender.com",
        "*"  # Temporariamente permite todos os origins
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Inclusão das rotas (AGORA COM history)
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(history.router, prefix="/api/history", tags=["History"])

# Rota de verificação de status
@app.get("/")
async def health_check():
    return {
        "status": "online",
        "message": "AskFile API está funcionando!",
        "version": "2.0.0",
        "features": [
            "Upload temporário de PDFs",
            "Chat com IA sobre documentos", 
            "Histórico de conversas",
            "Processamento sem armazenamento permanente"
        ],
        "services": ["chat", "upload", "history"],
        "storage_mode": "temporary_processing",
        "authentication": "disabled",
        "cors": "enabled_for_all_origins"
    }

# Rota de informações sobre o sistema
@app.get("/api/info")
async def system_info():
    return {
        "name": "AskFile",
        "version": "2.0.0",
        "description": "Sistema de consultas inteligentes em PDFs",
        "storage_policy": {
            "files": "Processamento temporário - arquivos removidos após indexação",
            "embeddings": "Armazenamento em memória para consultas",
            "history": "Mantido em memória durante a sessão"
        },
        "supported_formats": ["PDF"],
        "max_file_size": "25MB",
        "features": {
            "ai_chat": True,
            "document_analysis": True,
            "history": True,
            "user_authentication": False,
            "file_storage": False
        },
        "cors_enabled": True
    }

# Middleware para log de requisições
@app.middleware("http")
async def log_requests(request, call_next):
    start_time = time.time()
    
    # Log da requisição
    client_host = request.client.host if request.client else "unknown"
    logger.info(f"Request: {request.method} {request.url.path} from {client_host}")
    
    response = await call_next(request)
    process_time = time.time() - start_time
    
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.4f}s")
    return response

# Middleware adicional para CORS
@app.middleware("http")
async def add_cors_header(request, call_next):
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# Execução local
if __name__ == "__main__":
    import uvicorn
    logger.info("=== Iniciando AskFile API v2.0 ===")
    logger.info("Modo: Processamento temporário sem autenticação")
    logger.info("Recursos: Upload PDF + Chat IA + Histórico em memória")
    logger.info("CORS: Habilitado para todos os origins")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")