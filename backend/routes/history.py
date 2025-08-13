from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging
from routes.login import get_current_active_user

logger = logging.getLogger(__name__)
router = APIRouter()

# Modelos
class ChatEntry(BaseModel):
    id: int
    question: str
    answer: str
    timestamp: datetime
    sources: Optional[List[dict]] = []

class SaveChatRequest(BaseModel):
    question: str
    answer: str
    sources: Optional[List[dict]] = []

# Armazenamento em memória do histórico
user_history_store = {}
message_id_counter = 1

# Funções auxiliares
def get_user_history(user_email: str) -> List[dict]:
    return user_history_store.get(user_email, [])

def add_chat_entry(user_email: str, question: str, answer: str, sources: List[dict] = None) -> int:
    global message_id_counter
    
    if user_email not in user_history_store:
        user_history_store[user_email] = []
    
    new_entry = {
        "id": message_id_counter,
        "question": question,
        "answer": answer,
        "timestamp": datetime.now(),
        "sources": sources or []
    }
    
    user_history_store[user_email].append(new_entry)
    message_id_counter += 1
    
    logger.info(f"Nova entrada adicionada ao histórico de {user_email}")
    return new_entry["id"]

def clear_user_history(user_email: str) -> bool:
    if user_email in user_history_store:
        user_history_store[user_email] = []
        logger.info(f"Histórico limpo para usuário {user_email}")
        return True
    return False

def delete_chat_entry(user_email: str, entry_id: int) -> bool:
    if user_email not in user_history_store:
        return False
    
    user_history = user_history_store[user_email]
    for i, entry in enumerate(user_history):
        if entry["id"] == entry_id:
            del user_history[i]
            logger.info(f"Entrada {entry_id} removida do histórico de {user_email}")
            return True
    return False

# Endpoints
@router.get("", response_model=dict)
async def get_history(current_user: dict = Depends(get_current_active_user)):
    try:
        user_email = current_user["email"]
        history = get_user_history(user_email)
        
        # Converte datetime para string
        serialized_history = []
        for entry in history:
            serialized_entry = {
                "id": entry["id"],
                "question": entry["question"],
                "answer": entry["answer"],
                "timestamp": entry["timestamp"].isoformat(),
                "sources": entry["sources"]
            }
            serialized_history.append(serialized_entry)
        
        logger.info(f"Histórico recuperado para {user_email}: {len(history)} entradas")
        
        return {
            "history": serialized_history,
            "total_entries": len(history),
            "user": user_email
        }
        
    except Exception as e:
        logger.error(f"Erro ao buscar histórico: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar histórico"
        )

@router.post("/save")
async def save_chat(
    chat_data: SaveChatRequest,
    current_user: dict = Depends(get_current_active_user)
):
    try:
        user_email = current_user["email"]
        
        if not chat_data.question.strip() or not chat_data.answer.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pergunta e resposta são obrigatórias"
            )
        
        entry_id = add_chat_entry(
            user_email=user_email,
            question=chat_data.question.strip(),
            answer=chat_data.answer.strip(),
            sources=chat_data.sources or []
        )
        
        return {
            "message": "Conversa salva com sucesso",
            "entry_id": entry_id,
            "user": user_email
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao salvar conversa: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao salvar conversa"
        )

@router.delete("/clear")
async def clear_history(current_user: dict = Depends(get_current_active_user)):
    try:
        user_email = current_user["email"]
        success = clear_user_history(user_email)
        
        if success:
            return {
                "message": "Histórico limpo com sucesso",
                "user": user_email
            }
        else:
            return {
                "message": "Nenhum histórico encontrado para limpar",
                "user": user_email
            }
            
    except Exception as e:
        logger.error(f"Erro ao limpar histórico: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao limpar histórico"
        )

@router.delete("/{entry_id}")
async def delete_entry(
    entry_id: int,
    current_user: dict = Depends(get_current_active_user)
):
    try:
        user_email = current_user["email"]
        success = delete_chat_entry(user_email, entry_id)
        
        if success:
            return {
                "message": f"Entrada {entry_id} removida com sucesso",
                "user": user_email
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entrada não encontrada no histórico"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao remover entrada: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao remover entrada"
        )

@router.get("/stats")
async def get_history_stats(current_user: dict = Depends(get_current_active_user)):
    try:
        user_email = current_user["email"]
        history = get_user_history(user_email)
        
        total_entries = len(history)
        if total_entries == 0:
            return {
                "total_entries": 0,
                "first_entry": None,
                "last_entry": None,
                "user": user_email
            }
        
        first_entry = min(history, key=lambda x: x["timestamp"])
        last_entry = max(history, key=lambda x: x["timestamp"])
        
        return {
            "total_entries": total_entries,
            "first_entry": first_entry["timestamp"].isoformat(),
            "last_entry": last_entry["timestamp"].isoformat(),
            "user": user_email
        }
        
    except Exception as e:
        logger.error(f"Erro ao buscar estatísticas: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao buscar estatísticas"
        )