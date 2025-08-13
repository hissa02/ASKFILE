from fastapi import APIRouter, Body, HTTPException, Depends
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv
import os
import logging
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone
from routes.login import get_current_active_user

load_dotenv()

# Inicialização
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
logger = logging.getLogger(__name__)
router = APIRouter()

# Modelo de embedding
try:
    embedding_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-mpnet-base-v2')
    logger.info("Modelo de embedding para chat carregado")
except Exception as e:
    logger.error(f"Erro ao carregar modelo de embedding para chat: {e}")
    embedding_model = None

# Pinecone
try:
    pinecone_client = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    pinecone_index = pinecone_client.Index(os.getenv("PINECONE_INDEX_NAME"))
    logger.info("Pinecone para chat inicializado")
except Exception as e:
    logger.error(f"Erro ao inicializar Pinecone para chat: {e}")
    pinecone_index = None

class ChatRequest(BaseModel):
    question: str
    file_id: str = None

def generate_query_embedding(text: str) -> list:
    """Gera embedding para consulta"""
    try:
        if not embedding_model:
            raise RuntimeError("Modelo de embedding não disponível")
        
        embedding = embedding_model.encode([text], normalize_embeddings=True)
        return embedding[0].tolist()
        
    except Exception as e:
        logger.error(f"Erro ao gerar embedding da consulta: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar consulta")

def search_in_pinecone(query_embedding: list, user_email: str, file_id: str = None, top_k: int = 10) -> list:
    """Busca no Pinecone"""
    try:
        if not pinecone_index:
            raise RuntimeError("Pinecone não disponível")
        
        # Filtros de busca
        filter_dict = {"user_email": user_email}
        if file_id:
            filter_dict["file_id"] = file_id
        
        # Busca vetorial
        query_results = pinecone_index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True,
            filter=filter_dict
        )
        
        # Processa resultados
        context_parts = []
        sources = []
        
        for match in query_results.matches:
            content = match.metadata.get('content', '')
            file_id_meta = match.metadata.get('file_id', 'Arquivo')
            score = match.score
            
            if content.strip() and score > 0.3:  # Filtro de qualidade
                context_parts.append(content)
                sources.append({
                    'content': content[:200] + "..." if len(content) > 200 else content,
                    'score': score,
                    'file_id': file_id_meta
                })
        
        return context_parts, sources
        
    except Exception as e:
        logger.error(f"Erro na busca Pinecone: {e}")
        return [], []

@router.post("")
async def send_message(
    request: ChatRequest = Body(...),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Endpoint principal para chat com arquivo PDF
    """
    try:
        question = request.question
        file_id = request.file_id
        user_email = current_user["email"]
        
        if not question:
            raise HTTPException(status_code=400, detail='Pergunta é obrigatória')

        if not file_id:
            raise HTTPException(status_code=400, detail='ID do arquivo é obrigatório')

        logger.info(f"Pergunta recebida de {user_email}: {question}")
        logger.info(f"Arquivo consultado: {file_id}")

        # Gera embedding da pergunta
        question_embedding = generate_query_embedding(question)

        # Busca contexto relevante no Pinecone
        context_parts, sources = search_in_pinecone(
            query_embedding=question_embedding,
            user_email=user_email,
            file_id=file_id,
            top_k=15
        )

        if not context_parts:
            return {
                'answer': "Desculpe, não encontrei informações relevantes no seu arquivo para responder essa pergunta. Tente reformular a pergunta ou verificar se o conteúdo está relacionado ao arquivo enviado.",
                'sources': [],
                'context': '',
                'debug_info': {
                    'chunks_found': 0,
                    'context_length': 0,
                    'file_id': file_id
                }
            }

        # Constrói contexto para o LLM
        context = "\n\n".join(context_parts)
        
        logger.info(f"Contexto encontrado: {len(context_parts)} chunks, {len(context)} caracteres")

        # Constrói prompt otimizado
        prompt = f"""Você é um assistente especializado em analisar documentos PDF e responder perguntas baseadas no conteúdo.

Pergunta do usuário: {question}

Contexto do arquivo PDF:
{context}

Instruções:
- Responda APENAS com base no contexto fornecido do arquivo PDF
- Se a informação não estiver no contexto, diga que não encontrou a informação no arquivo
- Seja preciso e cite trechos específicos quando relevante
- Use uma linguagem clara e didática
- Se possível, organize a resposta de forma estruturada

Resposta baseada no arquivo:"""

        # Gera resposta com Groq
        try:
            response = groq_client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500,
                temperature=0.1,  # Baixa temperatura para máxima precisão
                top_p=0.9
            )
            
            answer = response.choices[0].message.content
            logger.info(f"Resposta gerada: {len(answer)} caracteres")
            
        except Exception as e:
            logger.error(f"Erro ao gerar resposta com Groq: {e}")
            answer = "Desculpe, houve um erro ao processar sua pergunta. Tente novamente."

        # Salva no histórico automaticamente
        try:
            from routes.history import add_chat_entry
            add_chat_entry(
                user_email=user_email,
                question=question,
                answer=answer,
                sources=sources
            )
            logger.info(f"Conversa salva no histórico para {user_email}")
        except Exception as history_error:
            logger.warning(f"Erro ao salvar no histórico: {history_error}")

        return {
            'answer': answer,
            'sources': sources,
            'context': context[:500] + "..." if len(context) > 500 else context,
            'debug_info': {
                'chunks_found': len(context_parts),
                'context_length': len(context),
                'similarity_scores': [f"{s['score']:.3f}" for s in sources[:5]],
                'file_id': file_id
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro interno no chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@router.get("/status")
async def chat_status():
    """Verifica status dos serviços de chat"""
    status = {
        "embedding_model": embedding_model is not None,
        "pinecone": pinecone_index is not None,
        "groq": groq_client is not None
    }
    
    return {
        "status": "ok" if all(status.values()) else "partial",
        "services": status
    }