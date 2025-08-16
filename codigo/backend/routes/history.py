from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_USER_EMAIL = "usuario@askfile.com"

@router.get("")
async def get_history(user_email: Optional[str] = Query(default=DEFAULT_USER_EMAIL)):
    """Obtem historico de conversas do usuario"""
    try:
        from routes.chat import get_user_history
        
        email = user_email or DEFAULT_USER_EMAIL
        
        history = get_user_history(email)
        
        # Ordena por timestamp mais recente
        if history:
            try:
                history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            except Exception as e:
                logger.warning(f"Erro ao ordenar historico: {e}")
        
        logger.info(f"Historico solicitado para {email}: {len(history)} itens")
        
        return {
            "history": history,
            "total_items": len(history),
            "user_email": email,
            "last_update": datetime.now().isoformat() if history else None
        }
        
    except Exception as e:
        logger.error(f"Erro ao buscar historico: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar historico: {str(e)}")

@router.delete("")
async def clear_history(user_email: Optional[str] = Query(default=DEFAULT_USER_EMAIL)):
    """Limpa historico de conversas do usuario"""
    try:
        from routes.chat import history_storage
        
        email = user_email or DEFAULT_USER_EMAIL
        
        if email in history_storage:
            items_count = len(history_storage[email])
            del history_storage[email]
            logger.info(f"Historico limpo para {email}: {items_count} itens removidos")
            
            return {
                "success": True,
                "message": f"Historico limpo ({items_count} itens removidos)",
                "user_email": email,
                "cleared_at": datetime.now().isoformat()
            }
        else:
            return {
                "success": True,
                "message": "Nenhum historico encontrado para limpar",
                "user_email": email,
                "cleared_at": datetime.now().isoformat()
            }
        
    except Exception as e:
        logger.error(f"Erro ao limpar historico: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao limpar historico: {str(e)}")

@router.get("/stats")
async def history_stats(user_email: Optional[str] = Query(default=DEFAULT_USER_EMAIL)):
    """Estatisticas do historico do usuario"""
    try:
        from routes.chat import get_user_history
        
        email = user_email or DEFAULT_USER_EMAIL
        history = get_user_history(email)
        
        if not history:
            return {
                "user_email": email,
                "total_conversations": 0,
                "total_questions": 0,
                "first_conversation": None,
                "last_conversation": None,
                "most_active_day": None
            }
        
        # Calcula estatisticas
        total_conversations = len(history)
        
        # Primeira e ultima conversa
        timestamps = [item.get('timestamp') for item in history if item.get('timestamp')]
        timestamps.sort()
        
        first_conversation = timestamps[0] if timestamps else None
        last_conversation = timestamps[-1] if timestamps else None
        
        # Analisa dias mais ativos
        days_activity = {}
        for item in history:
            if item.get('timestamp'):
                try:
                    date = datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00'))
                    day_key = date.strftime('%Y-%m-%d')
                    days_activity[day_key] = days_activity.get(day_key, 0) + 1
                except:
                    continue
        
        most_active_day = max(days_activity, key=days_activity.get) if days_activity else None
        
        return {
            "user_email": email,
            "total_conversations": total_conversations,
            "total_questions": total_conversations,
            "first_conversation": first_conversation,
            "last_conversation": last_conversation,
            "most_active_day": most_active_day,
            "days_with_activity": len(days_activity),
            "average_per_day": round(total_conversations / max(len(days_activity), 1), 2)
        }
        
    except Exception as e:
        logger.error(f"Erro ao calcular estatisticas: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao calcular estatisticas: {str(e)}")

@router.get("/search")
async def search_history(
    query: str = Query(..., description="Termo de busca"),
    user_email: Optional[str] = Query(default=DEFAULT_USER_EMAIL)
):
    """Busca no historico de conversas"""
    try:
        from routes.chat import get_user_history
        
        email = user_email or DEFAULT_USER_EMAIL
        history = get_user_history(email)
        
        if not history or not query.strip():
            return {
                "results": [],
                "total_found": 0,
                "query": query,
                "user_email": email
            }
        
        query_lower = query.lower().strip()
        results = []
        
        for item in history:
            score = 0
            matched_in = []
            
            # Busca na pergunta
            question = item.get('question', '').lower()
            if query_lower in question:
                score += 3
                matched_in.append('question')
            
            # Busca na resposta
            answer = item.get('answer', '').lower()
            if query_lower in answer:
                score += 2
                matched_in.append('answer')
            
            # Busca por palavras individuais
            query_words = query_lower.split()
            for word in query_words:
                if len(word) > 2:
                    if word in question:
                        score += 1
                    if word in answer:
                        score += 0.5
            
            if score > 0:
                results.append({
                    **item,
                    'search_score': score,
                    'matched_in': matched_in
                })
        
        # Ordena por relevancia
        results.sort(key=lambda x: x['search_score'], reverse=True)
        
        logger.info(f"Busca '{query}' para {email}: {len(results)} resultados")
        
        return {
            "results": results,
            "total_found": len(results),
            "query": query,
            "user_email": email,
            "searched_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Erro na busca do historico: {e}")
        raise HTTPException(status_code=500, detail=f"Erro na busca: {str(e)}")

@router.get("/status")
async def history_status():
    """Status do servico de historico"""
    try:
        from routes.chat import history_storage
        
        total_users = len(history_storage)
        total_items = sum(len(history) for history in history_storage.values())
        
        # Calcula estatisticas gerais
        users_with_history = []
        for user_email, user_history in history_storage.items():
            if user_history:
                users_with_history.append({
                    "user": user_email,
                    "conversations": len(user_history),
                    "last_activity": max(
                        (item.get('timestamp') for item in user_history if item.get('timestamp')),
                        default=None
                    )
                })
        
        return {
            "status": "ok",
            "total_users": total_users,
            "total_items": total_items,
            "active_users": len(users_with_history),
            "storage_type": "in_memory_by_user",
            "default_user": DEFAULT_USER_EMAIL,
            "features": {
                "session_isolation": True,
                "search_capability": True,
                "statistics": True,
                "automatic_sorting": True
            },
            "users_with_history": users_with_history[:10],  # Top 10 usuarios mais ativos
            "system_stats": {
                "average_conversations_per_user": round(total_items / max(total_users, 1), 2),
                "max_conversations_per_user": max(
                    (len(history) for history in history_storage.values()),
                    default=0
                )
            }
        }
        
    except Exception as e:
        logger.error(f"Erro no status do historico: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }