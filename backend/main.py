from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
from routes import chat, history, login, upload
import os

# Carrega as variáveis de ambiente
load_dotenv()

# Cria a aplicação FastAPI
app = FastAPI(title="AskFile API", description="API para consultas inteligentes em PDFs")

# Configuração do CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especifique os domínios
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Inclusão das rotas
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(history.router, prefix="/api/history", tags=["History"])
app.include_router(login.router, prefix="/api/login", tags=["Login"])
app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])

# Rota de verificação de status
@app.get("/")
async def health_check():
    return {
        "status": "online",
        "message": "AskFile API está funcionando!",
        "services": ["chat", "history", "login", "upload"]
    }

# Execução local
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)