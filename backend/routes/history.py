from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

# Email padrão para usuário sem autenticação
DEFAULT_USER_EMAIL = "usuario@askfile.com"

@router.get("")
async def get_history(user_email: Optional[str] = Query(default=DEFAULT_USER_EMAIL)):
    """
    Obtém o histórico de conversas do usuário
    """
    try:
        # Importa a função do chat.py
        from routes.chat import get_user_history
        
        # Usa email padrão se não fornecido
        email = user_email or DEFAULT_USER_EMAIL
        
        history = get_user_history(email)
        
        logger.info(f"Histórico solicitado para {email}: {len(history)} itens")
        
        return {
            "history": history,
            "total_items": len(history),
            "user_email": email
        }
        
    except Exception as e:
        logger.error(f"Erro ao buscar histórico: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar histórico: {str(e)}")

@router.delete("")
async def clear_history(user_email: Optional[str] = Query(default=DEFAULT_USER_EMAIL)):
    """
    Limpa o histórico de conversas do usuário
    """
    try:
        # Importa o storage do chat.py
        from routes.chat import history_storage
        
        # Usa email padrão se não fornecido
        email = user_email or DEFAULT_USER_EMAIL
        
        if email in history_storage:
            items_count = len(history_storage[email])
            del history_storage[email]
            logger.info(f"Histórico limpo para {email}: {items_count} itens removidos")
            
            return {
                "success": True,
                "message": f"Histórico limpo ({items_count} itens removidos)",
                "user_email": email
            }
        else:
            return {
                "success": True,
                "message": "Nenhum histórico encontrado para limpar",
                "user_email": email
            }
        
    except Exception as e:
        logger.error(f"Erro ao limpar histórico: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao limpar histórico: {str(e)}")

@router.get("/status")
async def history_status():
    """
    Status do serviço de histórico
    """
    try:
        from routes.chat import history_storage
        
        total_users = len(history_storage)
        total_items = sum(len(history) for history in history_storage.values())
        
        return {
            "status": "ok",
            "total_users": total_users,
            "total_items": total_items,
            "storage_type": "in_memory",
            "default_user": DEFAULT_USER_EMAIL
        }
        
    except Exception as e:
        logger.error(f"Erro no status do histórico: {e}")
        return {
            "status": "error",
            "error": str(e)
        }