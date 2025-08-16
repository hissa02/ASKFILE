from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
import os
import time

# Importa os modulos de rotas
from routes import chat, upload, history

# Carrega as variaveis de ambiente
load_dotenv()

# Cria a aplicacao FastAPI
app = FastAPI(
    title="AskFile API", 
    description="API para consultas inteligentes em PDFs - Processamento temporario de arquivos",
    version="2.0.0",
    redirect_slashes=True # Adicionado para corrigir o erro 405
)

# Configuracao do CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://askfile-seven.vercel.app",
        "https://*.vercel.app",
        "https://askfile.onrender.com",
        "http://127.0.0.1:3000",
        "http://localhost:8000"
    ],
    allow_origin_regex="https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

# Configuracao de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Inclusao das rotas com prefixos corretos
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(history.router, prefix="/api/history", tags=["History"])

# Rota de verificacao de status
@app.get("/")
async def health_check():
    return {
        "status": "online",
        "message": "AskFile API funcionando",
        "version": "2.0.0",
        "features": [
            "Upload temporario de PDFs",
            "Chat com IA sobre documentos", 
            "Historico de conversas",
            "Processamento sem armazenamento permanente",
            "Deteccao de contexto de documento",
            "Busca inteligente melhorada"
        ],
        "services": ["chat", "upload", "history"],
        "storage_mode": "temporary_processing",
        "authentication": "disabled"
    }

# Rota de informacoes sobre o sistema
@app.get("/api/info")
async def system_info():
    return {
        "name": "AskFile",
        "version": "2.0.0",
        "description": "Sistema de consultas inteligentes em PDFs",
        "storage_policy": {
            "files": "Processamento temporario - arquivos removidos apos indexacao",
            "embeddings": "Armazenamento em memoria para consultas",
            "history": "Mantido em memoria durante a sessao"
        },
        "supported_formats": ["PDF"],
        "max_file_size": "25MB",
        "features": {
            "ai_chat": True,
            "document_analysis": True,
            "context_detection": True,
            "enhanced_search": True,
            "history": True,
            "user_authentication": False,
            "file_storage": False
        },
        "improvements": [
            "deteccao_contexto_documento",
            "busca_similaridade_palavras",
            "extracao_entidades_chave",
            "chunking_otimizado",
            "limpeza_texto_avancada"
        ]
    }

# Rota para listar todas as rotas disponiveis (debug)
@app.get("/api/routes")
async def list_routes():
    routes = []
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            routes.append({
                "path": route.path,
                "methods": list(route.methods)
            })
    return {
        "total_routes": len(routes),
        "routes": routes
    }

# Middleware para log de requisicoes
@app.middleware("http")
async def log_requests(request, call_next):
    start_time = time.time()
    
    # Log da requisicao
    logger.info(f"Requisicao: {request.method} {request.url.path}")
    
    response = await call_next(request)
    process_time = time.time() - start_time
    
    # Log da resposta
    logger.info(f"Resposta: {request.method} {request.url.path} - {response.status_code} - {process_time:.4f}s")
    
    return response

# Handler para opcoes CORS
@app.options("/{path:path}")
async def options_handler(path: str):
    return {"message": "OK"}

# Execucao local
if __name__ == "__main__":
    import uvicorn
    logger.info("=== Iniciando AskFile API v2.0 ===")
    logger.info("Modo: Processamento temporario sem autenticacao")
    logger.info("Recursos: Upload PDF + Chat IA + Historico em memoria")
    logger.info("Melhorias: Deteccao contexto + Busca inteligente")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")