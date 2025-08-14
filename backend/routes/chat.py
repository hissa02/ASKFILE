from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv
import os
import logging
import re
from datetime import datetime

load_dotenv()

# Inicialização
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
logger = logging.getLogger(__name__)
router = APIRouter()

# Email padrão para usuário sem autenticação
DEFAULT_USER_EMAIL = "usuario@askfile.com"

# Armazenamento simples em memória
text_storage = {}

class ChatRequest(BaseModel):
    question: str
    file_id: str = None

def smart_text_search(query: str, file_id: str, user_email: str, max_results: int = 8) -> tuple:
    """Busca inteligente por texto usando palavras-chave e contexto"""
    try:
        # Verifica se há dados para este usuário e arquivo
        storage_key = f"{user_email}_{file_id}"
        if storage_key not in text_storage:
            return [], []
        
        file_data = text_storage[storage_key]
        chunks = file_data.get('chunks', [])
        
        if not chunks:
            return [], []
        
        # Prepara a consulta
        query_lower = query.lower()
        query_words = [word.strip() for word in query_lower.split() if len(word.strip()) > 2]
        
        if not query_words:
            return [], []
        
        scored_chunks = []
        
        for i, chunk in enumerate(chunks):
            chunk_lower = chunk.lower()
            score = 0
            
            # Pontuação por palavras exatas
            for word in query_words:
                word_count = chunk_lower.count(word)
                if word_count > 0:
                    score += word_count * 2  # Peso maior para matches exatos
            
            # Pontuação por palavras similares (raiz da palavra)
            for word in query_words:
                if len(word) > 4:
                    word_root = word[:4]
                    similar_matches = len(re.findall(rf'\b{word_root}\w*', chunk_lower))
                    score += similar_matches * 0.5
            
            # Pontuação por proximidade das palavras
            if len(query_words) > 1:
                for i in range(len(query_words) - 1):
                    word1, word2 = query_words[i], query_words[i + 1]
                    if word1 in chunk_lower and word2 in chunk_lower:
                        pos1 = chunk_lower.find(word1)
                        pos2 = chunk_lower.find(word2)
                        distance = abs(pos1 - pos2)
                        if distance < 100:  # Palavras próximas
                            score += 1.5
            
            # Adiciona bonus se o chunk contém a pergunta como um todo
            if len(query_lower) > 10 and query_lower in chunk_lower:
                score += 5
            
            if score > 0:
                scored_chunks.append({
                    'content': chunk,
                    'score': score,
                    'index': i
                })
        
        # Ordena por score e pega os melhores
        scored_chunks.sort(key=lambda x: x['score'], reverse=True)
        best_chunks = scored_chunks[:max_results]
        
        context_parts = [chunk['content'] for chunk in best_chunks]
        sources = [{
            'content': chunk['content'][:200] + "..." if len(chunk['content']) > 200 else chunk['content'],
            'score': round(chunk['score'], 2),
            'file_id': file_id
        } for chunk in best_chunks]
        
        logger.info(f"Busca inteligente retornou {len(context_parts)} resultados para: '{query}'")
        return context_parts, sources
        
    except Exception as e:
        logger.error(f"Erro na busca: {e}")
        return [], []

@router.post("")
async def send_message(request: ChatRequest = Body(...)):
    """
    Endpoint principal para chat com arquivo PDF
    """
    try:
        question = request.question
        file_id = request.file_id
        user_email = DEFAULT_USER_EMAIL
        
        if not question:
            raise HTTPException(status_code=400, detail='Pergunta é obrigatória')

        if not file_id:
            raise HTTPException(status_code=400, detail='ID do arquivo é obrigatório')

        logger.info(f"Pergunta recebida: {question}")
        logger.info(f"Arquivo consultado: {file_id}")

        # Verifica se Groq está disponível
        if not groq_client:
            raise HTTPException(status_code=503, detail="Serviço de IA não disponível")

        # Busca contexto relevante usando busca inteligente
        context_parts, sources = smart_text_search(
            query=question,
            file_id=file_id,
            user_email=user_email,
            max_results=10
        )

        if not context_parts:
            logger.warning(f"Nenhum contexto encontrado para: {question}")
            return {
                'answer': "Desculpe, não encontrei informações relevantes no seu arquivo para responder essa pergunta.\n\n**Dicas para melhor resultado:**\n\n1. Use palavras-chave específicas do documento\n2. Tente reformular a pergunta de forma mais direta\n3. Verifique se o conteúdo está relacionado ao arquivo enviado\n\nExemplo: Em vez de 'me fale sobre isso', pergunte 'quais são os principais resultados?' ou 'qual é a conclusão?'",
                'sources': [],
                'context': '',
                'debug_info': {
                    'chunks_found': 0,
                    'context_length': 0,
                    'file_id': file_id,
                    'search_type': 'smart_text_search'
                }
            }

        # Constrói contexto para o LLM
        context = "\n\n---\n\n".join(context_parts)
        
        logger.info(f"Contexto encontrado: {len(context_parts)} partes, {len(context)} caracteres")

        # Prompt otimizado para Groq
        prompt = f"""Você é um assistente especializado em analisar documentos e responder perguntas com base no conteúdo fornecido.

PERGUNTA DO USUÁRIO:
{question}

CONTEXTO DO DOCUMENTO:
{context}

INSTRUÇÕES IMPORTANTES:
- Responda APENAS com base no contexto fornecido
- Se a informação não estiver no contexto, diga claramente que não encontrou no documento
- Seja preciso e cite partes específicas quando relevante
- Use linguagem clara e organize a resposta de forma estruturada
- Se houver dados, números ou fatos específicos, mencione-os

RESPOSTA:"""

        # Gera resposta com Groq
        try:
            response = groq_client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.1,
                top_p=0.9
            )
            
            answer = response.choices[0].message.content
            logger.info(f"Resposta gerada: {len(answer)} caracteres")
            
        except Exception as e:
            logger.error(f"Erro ao gerar resposta com Groq: {e}")
            answer = "Desculpe, houve um erro ao processar sua pergunta. Tente novamente em alguns instantes."

        return {
            'answer': answer,
            'sources': sources,
            'context': context[:400] + "..." if len(context) > 400 else context,
            'debug_info': {
                'chunks_found': len(context_parts),
                'context_length': len(context),
                'best_scores': [s['score'] for s in sources[:3]],
                'file_id': file_id,
                'search_type': 'smart_text_search',
                'groq_available': True
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro interno no chat: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@router.get("/status")
async def chat_status():
    """Verifica status dos serviços"""
    
    groq_status = groq_client is not None
    storage_files = len(text_storage)
    
    response = {
        "status": "ok" if groq_status else "partial",
        "services": {
            "groq": groq_status,
            "text_search": True,
            "storage": True
        },
        "details": {
            "groq_model": "llama3-8b-8192" if groq_status else "Não disponível",
            "search_type": "smart_text_search",
            "storage_type": "in_memory",
            "files_indexed": storage_files
        }
    }
    
    return response

# Função auxiliar para salvar chunks (usada pelo upload.py)
def save_text_chunks(file_id: str, chunks: list, user_email: str = DEFAULT_USER_EMAIL):
    """Salva chunks no armazenamento de texto"""
    try:
        storage_key = f"{user_email}_{file_id}"
        text_storage[storage_key] = {
            'chunks': chunks,
            'created_at': datetime.now().isoformat(),
            'total_chunks': len(chunks)
        }
        
        logger.info(f"✅ Salvos {len(chunks)} chunks para arquivo {file_id}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro ao salvar chunks: {e}")
        return False