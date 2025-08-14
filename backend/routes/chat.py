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
# ADICIONADO: Armazenamento do histórico
history_storage = {}

class ChatRequest(BaseModel):
    question: str
    file_id: str = None

def generate_search_terms(query: str) -> list:
    """Usa o LLM para gerar termos de busca alternativos"""
    try:
        if not groq_client:
            return [query.lower()]
        
        prompt = f"""Dado esta pergunta: "{query}"

Gere uma lista de termos e frases alternativas para buscar no documento. Inclua:
- Sinônimos das palavras principais
- Variações da pergunta
- Palavras-chave relacionadas
- Termos técnicos equivalentes

Exemplo:
Pergunta: "quem fez o TCC?"
Termos: autor, autora, quem escreveu, quem desenvolveu, nome do estudante, aluno, pesquisador, TCC, monografia, trabalho de conclusão, trabalho final

Para a pergunta "{query}", liste apenas os termos separados por vírgula:"""

        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3
        )
        
        terms_text = response.choices[0].message.content
        
        # Extrai os termos
        terms = [term.strip().lower() for term in terms_text.split(',') if term.strip()]
        
        # Adiciona a query original
        terms.insert(0, query.lower())
        
        # Remove duplicatas mantendo ordem
        seen = set()
        unique_terms = []
        for term in terms:
            if term not in seen and len(term) >= 3:
                seen.add(term)
                unique_terms.append(term)
        
        logger.info(f"Termos gerados para '{query}': {unique_terms[:10]}")
        return unique_terms[:15]  # Limita a 15 termos
        
    except Exception as e:
        logger.error(f"Erro ao gerar termos de busca: {e}")
        return [query.lower()]

def smart_text_search(query: str, file_id: str, user_email: str, max_results: int = 8) -> tuple:
    """Busca inteligente por texto usando LLM para expandir termos"""
    try:
        # Verifica se há dados para este usuário e arquivo
        storage_key = f"{user_email}_{file_id}"
        if storage_key not in text_storage:
            return [], []
        
        file_data = text_storage[storage_key]
        chunks = file_data.get('chunks', [])
        
        if not chunks:
            return [], []
        
        # Gera termos de busca usando LLM
        search_terms = generate_search_terms(query)
        
        if not search_terms:
            return [], []
        
        scored_chunks = []
        
        for i, chunk in enumerate(chunks):
            chunk_lower = chunk.lower()
            score = 0
            matched_terms = []
            
            # Busca por cada termo gerado
            for term_idx, term in enumerate(search_terms):
                term_count = chunk_lower.count(term)
                if term_count > 0:
                    # Primeiro termo (query original) tem peso maior
                    weight = 3.0 if term_idx == 0 else max(2.0 - (term_idx * 0.1), 0.5)
                    score += term_count * weight
                    matched_terms.append(term)
            
            # Busca por variações das palavras (prefixos)
            for term in search_terms[:5]:  # Só os 5 primeiros termos
                if len(term) > 4:
                    term_root = term[:4]
                    similar_matches = len(re.findall(rf'\b{term_root}\w*', chunk_lower))
                    score += similar_matches * 0.3
            
            # Proximidade entre termos
            if len(search_terms) > 1:
                for i_term in range(min(3, len(search_terms) - 1)):  # Só os 3 primeiros
                    term1, term2 = search_terms[i_term], search_terms[i_term + 1]
                    if term1 in chunk_lower and term2 in chunk_lower:
                        pos1 = chunk_lower.find(term1)
                        pos2 = chunk_lower.find(term2)
                        distance = abs(pos1 - pos2)
                        if distance < 100:
                            score += 1.5
                            matched_terms.append("proximidade")
            
            # Bonus para chunks com múltiplos termos
            unique_terms_found = len(set(term for term in search_terms if term in chunk_lower))
            if unique_terms_found > 1:
                score += unique_terms_found * 1.2
                matched_terms.append(f"multi_terms_{unique_terms_found}")
            
            # Busca por números
            numbers_in_query = re.findall(r'\b\d+\b', query)
            if numbers_in_query:
                for num in numbers_in_query:
                    if num in chunk:
                        score += 3
                        matched_terms.append(f"numero_{num}")
            
            if score > 0:
                scored_chunks.append({
                    'content': chunk,
                    'score': score,
                    'index': i,
                    'matched_terms': matched_terms[:8]
                })
        
        # Ordena por score e pega os melhores
        scored_chunks.sort(key=lambda x: x['score'], reverse=True)
        best_chunks = scored_chunks[:max_results]
        
        context_parts = [chunk['content'] for chunk in best_chunks]
        sources = [{
            'content': chunk['content'][:200] + "..." if len(chunk['content']) > 200 else chunk['content'],
            'score': round(chunk['score'], 2),
            'file_id': file_id,
            'matched_terms': chunk['matched_terms']
        } for chunk in best_chunks]
        
        logger.info(f"Busca com LLM retornou {len(context_parts)} resultados para: '{query}'")
        if best_chunks:
            logger.info(f"Melhor score: {best_chunks[0]['score']:.2f}")
        
        return context_parts, sources
        
    except Exception as e:
        logger.error(f"Erro na busca: {e}")
        return [], []

# ADICIONADO: Função para salvar no histórico
def save_to_history(user_email: str, question: str, answer: str, sources: list, file_id: str = None):
    """Salva pergunta e resposta no histórico"""
    try:
        if user_email not in history_storage:
            history_storage[user_email] = []
        
        history_item = {
            "question": question,
            "answer": answer,
            "sources": sources,
            "file_id": file_id,
            "timestamp": datetime.now().isoformat()
        }
        
        history_storage[user_email].append(history_item)
        
        # Limita o histórico a 50 itens por usuário
        if len(history_storage[user_email]) > 50:
            history_storage[user_email] = history_storage[user_email][-50:]
        
        logger.info(f"Item salvo no histórico para {user_email}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao salvar histórico: {e}")
        return False

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

        # Busca contexto relevante usando busca inteligente com LLM
        context_parts, sources = smart_text_search(
            query=question,
            file_id=file_id,
            user_email=user_email,
            max_results=10
        )

        if not context_parts:
            logger.warning(f"Nenhum contexto encontrado para: {question}")
            answer = "Desculpe, não encontrei informações relevantes no seu arquivo para responder essa pergunta.\n\n**Dicas para melhor resultado:**\n\n1. Use palavras-chave específicas do documento\n2. Tente reformular a pergunta de forma mais direta\n3. Verifique se o conteúdo está relacionado ao arquivo enviado\n\nExemplo: Em vez de 'me fale sobre isso', pergunte 'quais são os principais resultados?' ou 'qual é a conclusão?'"
            
            # ADICIONADO: Salva no histórico mesmo quando não encontra contexto
            save_to_history(user_email, question, answer, [], file_id)
            
            return {
                'answer': answer,
                'sources': [],
                'context': '',
                'debug_info': {
                    'chunks_found': 0,
                    'context_length': 0,
                    'file_id': file_id,
                    'search_type': 'llm_semantic_search'
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

        # ADICIONADO: Salva no histórico
        save_to_history(user_email, question, answer, sources, file_id)

        return {
            'answer': answer,
            'sources': sources,
            'context': context[:400] + "..." if len(context) > 400 else context,
            'debug_info': {
                'chunks_found': len(context_parts),
                'context_length': len(context),
                'best_scores': [s['score'] for s in sources[:3]],
                'file_id': file_id,
                'search_type': 'llm_semantic_search',
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
            "storage": True,
            "llm_semantic_expansion": groq_status,
            "history": True
        },
        "details": {
            "groq_model": "llama3-8b-8192" if groq_status else "Não disponível",
            "search_type": "llm_semantic_search",
            "storage_type": "in_memory",
            "files_indexed": storage_files,
            "history_users": len(history_storage)
        }
    }
    
    return response

# ADICIONADO: Função para obter histórico
def get_user_history(user_email: str) -> list:
    """Obtém o histórico do usuário"""
    return history_storage.get(user_email, [])

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
        
        logger.info(f" Salvos {len(chunks)} chunks para arquivo {file_id}")
        return True
        
    except Exception as e:
        logger.error(f" Erro ao salvar chunks: {e}")
        return False