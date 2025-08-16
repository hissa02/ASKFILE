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
# Armazenamento do histórico
history_storage = {}

class ChatRequest(BaseModel):
    question: str
    file_id: str = None
    user_email: str = DEFAULT_USER_EMAIL

def generate_enhanced_search_terms(query: str) -> list:
    """Gera termos de busca mais precisos usando LLM"""
    try:
        if not groq_client:
            return [query.lower()]
        
        prompt = f"""Para a pergunta: "{query}"

Gere termos de busca específicos e abrangentes. Inclua:
- Sinônimos e variações das palavras principais
- Termos técnicos e informais
- Variações de gênero e número
- Palavras relacionadas ao contexto
- Abreviações comuns

Exemplo:
Pergunta: "de quem é o histórico?"
Termos: histórico, nome, estudante, aluno, aluna, titular, proprietário, pertence, pessoa, indivíduo, matrícula, registro, documento, nome principal, identificação

Para "{query}", liste termos separados por vírgula:"""

        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
            temperature=0.2
        )
        
        terms_text = response.choices[0].message.content
        terms = [term.strip().lower() for term in terms_text.split(',') if term.strip()]
        
        # Adiciona query original e suas palavras
        terms.insert(0, query.lower())
        query_words = query.lower().split()
        for word in query_words:
            if len(word) > 2 and word not in terms:
                terms.append(word)
        
        # Remove duplicatas mantendo ordem
        seen = set()
        unique_terms = []
        for term in terms:
            clean_term = term.strip()
            if clean_term not in seen and len(clean_term) >= 2:
                seen.add(clean_term)
                unique_terms.append(clean_term)
        
        logger.info(f"Termos gerados para '{query}': {unique_terms[:15]}")
        return unique_terms[:20]
        
    except Exception as e:
        logger.error(f"Erro ao gerar termos de busca: {e}")
        basic_terms = [query.lower()]
        query_words = query.lower().split()
        basic_terms.extend([word for word in query_words if len(word) > 2])
        return basic_terms

def contextual_search(query: str, file_id: str, user_email: str, max_results: int = 10) -> tuple:
    """Busca contextual que considera a estrutura dos chunks"""
    try:
        storage_key = f"{user_email}_{file_id}"
        if storage_key not in text_storage:
            return [], []
        
        file_data = text_storage[storage_key]
        chunks = file_data.get('chunks', [])
        
        if not chunks:
            return [], []
        
        search_terms = generate_enhanced_search_terms(query)
        
        if not search_terms:
            return [], []
        
        scored_chunks = []
        
        for i, chunk in enumerate(chunks):
            chunk_lower = chunk.lower()
            score = 0
            matched_terms = []
            context_info = ""
            
            # Extrai informação de contexto do chunk
            context_match = re.search(r'\[SECAO:\s*([^\]]+)\]', chunk)
            if context_match:
                context_info = context_match.group(1)
            
            # Busca exata da query completa - peso muito alto
            if query.lower() in chunk_lower:
                score += 20.0
                matched_terms.append("query_exata")
            
            # Frases de múltiplas palavras
            query_words = query.lower().split()
            if len(query_words) >= 2:
                for j in range(len(query_words) - 1):
                    phrase = " ".join(query_words[j:j+2])
                    if phrase in chunk_lower:
                        score += 12.0
                        matched_terms.append(f"frase_{phrase}")
            
            # Busca por termos individuais
            for term_idx, term in enumerate(search_terms):
                term_count = chunk_lower.count(term)
                if term_count > 0:
                    if term_idx == 0:  # Query original
                        weight = 8.0
                    elif term_idx < 3:  # Primeiros termos
                        weight = 5.0
                    else:
                        weight = max(3.0 - (term_idx * 0.1), 1.0)
                    
                    score += term_count * weight
                    matched_terms.append(term)
            
            # Bonus para contextos relevantes
            context_bonuses = {
                'IDENTIFICACAO': 15.0,  # Para perguntas sobre nomes/pessoas
                'DADOS_PESSOAIS': 15.0,
                'PAGINA_1': 8.0,  # Primeira página geralmente tem dados importantes
                'TABELA': 5.0
            }
            
            for context_type, bonus in context_bonuses.items():
                if context_type in context_info.upper():
                    # Verifica se a pergunta é relevante para este contexto
                    if any(keyword in query.lower() for keyword in ['nome', 'quem', 'estudante', 'pessoa', 'autor']):
                        if context_type in ['IDENTIFICACAO', 'DADOS_PESSOAIS']:
                            score += bonus
                            matched_terms.append(f"contexto_{context_type}")
                    elif context_type == 'PAGINA_1':
                        score += bonus * 0.5  # Bonus menor para primeira página
                        matched_terms.append("primeira_pagina")
            
            # Busca por variações e radicais
            for term in search_terms[:6]:
                if len(term) > 3:
                    term_root = term[:3]
                    similar_matches = len(re.findall(rf'\b{re.escape(term_root)}\w*', chunk_lower))
                    score += similar_matches * 0.8
            
            # Proximidade entre termos
            if len(search_terms) > 1:
                for i_term in range(min(3, len(search_terms) - 1)):
                    term1, term2 = search_terms[i_term], search_terms[i_term + 1]
                    if term1 in chunk_lower and term2 in chunk_lower:
                        pos1 = chunk_lower.find(term1)
                        pos2 = chunk_lower.find(term2)
                        distance = abs(pos1 - pos2)
                        if distance < 100:
                            proximity_bonus = max(3.0 - (distance / 50), 0.5)
                            score += proximity_bonus
                            matched_terms.append("proximidade")
            
            # Bonus para múltiplos termos únicos
            unique_terms_found = len(set(term for term in search_terms[:8] if term in chunk_lower))
            if unique_terms_found > 1:
                score += unique_terms_found * 2.0
                matched_terms.append(f"multi_termos_{unique_terms_found}")
            
            # Busca por números específicos
            numbers_in_query = re.findall(r'\b\d+\b', query)
            if numbers_in_query:
                for num in numbers_in_query:
                    if num in chunk:
                        score += 6.0
                        matched_terms.append(f"numero_{num}")
            
            # Palavras-chave importantes
            important_keywords = {
                'nome': 10.0, 'quem': 8.0, 'autor': 8.0, 'estudante': 6.0,
                'matrícula': 6.0, 'curso': 5.0, 'data': 4.0, 'nascimento': 4.0
            }
            
            for keyword, bonus in important_keywords.items():
                if keyword in query.lower() and keyword in chunk_lower:
                    score += bonus
                    matched_terms.append(f"palavra_chave_{keyword}")
            
            if score > 0:
                scored_chunks.append({
                    'content': chunk,
                    'score': score,
                    'index': i,
                    'matched_terms': matched_terms[:8],
                    'context_info': context_info
                })
        
        # Ordena por score e filtra os melhores
        scored_chunks.sort(key=lambda x: x['score'], reverse=True)
        best_chunks = scored_chunks[:max_results]
        
        context_parts = [chunk['content'] for chunk in best_chunks]
        sources = [{
            'content': chunk['content'][:300] + "..." if len(chunk['content']) > 300 else chunk['content'],
            'score': round(chunk['score'], 2),
            'file_id': file_id,
            'matched_terms': chunk['matched_terms'],
            'context_info': chunk['context_info']
        } for chunk in best_chunks]
        
        logger.info(f"Busca contextual retornou {len(context_parts)} resultados para: '{query}' (usuário: {user_email})")
        if best_chunks:
            logger.info(f"Melhores scores: {[round(c['score'], 2) for c in best_chunks[:3]]}")
        
        return context_parts, sources
        
    except Exception as e:
        logger.error(f"Erro na busca contextual: {e}")
        return [], []

def save_to_history(user_email: str, question: str, answer: str, sources: list, file_id: str = None):
    """Salva pergunta e resposta no histórico do usuário"""
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
    Endpoint principal para chat com análise contextual melhorada
    """
    try:
        question = request.question
        file_id = request.file_id
        user_email = request.user_email or DEFAULT_USER_EMAIL
        
        if not question:
            raise HTTPException(status_code=400, detail='Pergunta é obrigatória')

        if not file_id:
            raise HTTPException(status_code=400, detail='ID do arquivo é obrigatório')

        logger.info(f"Pergunta recebida: {question} (usuário: {user_email})")
        logger.info(f"Arquivo consultado: {file_id}")

        # Verifica se Groq está disponível
        if not groq_client:
            raise HTTPException(status_code=503, detail="Serviço de IA não disponível")

        # Busca contexto usando busca contextual melhorada
        context_parts, sources = contextual_search(
            query=question,
            file_id=file_id,
            user_email=user_email,
            max_results=12
        )

        if not context_parts:
            logger.warning(f"Nenhum contexto encontrado para: {question}")
            answer = "Não encontrei informações específicas no documento para responder sua pergunta.\n\n**Sugestões:**\n\n1. Verifique se usa termos que estão no documento\n2. Reformule a pergunta com palavras diferentes\n3. Tente termos mais específicos\n4. Use sinônimos\n\nExemplo: Em vez de 'responsável', tente 'nome', 'estudante' ou 'autor'"
            
            save_to_history(user_email, question, answer, [], file_id)
            
            return {
                'answer': answer,
                'sources': [],
                'context': '',
                'debug_info': {
                    'chunks_found': 0,
                    'context_length': 0,
                    'file_id': file_id,
                    'user_email': user_email,
                    'search_type': 'contextual_search'
                }
            }

        # Constrói contexto para o LLM
        context = "\n\n---\n\n".join(context_parts)
        
        logger.info(f"Contexto contextual encontrado: {len(context_parts)} partes, {len(context)} caracteres")

        # Prompt otimizado para análise contextual
        prompt = f"""Você é um assistente especializado em analisar documentos com precisão máxima.

PERGUNTA: {question}

CONTEXTO DO DOCUMENTO:
{context}

INSTRUÇÕES IMPORTANTES:
- Analise TODO o contexto fornecido com atenção
- Responda APENAS com base nas informações do contexto
- Se a informação estiver no contexto, cite-a diretamente
- Seja preciso com nomes, datas e números
- Se não encontrar a informação específica, diga claramente
- Organize a resposta de forma clara
- Priorize informações diretas sobre inferências

ATENÇÃO: Diferençie claramente entre "Nome:" (pessoa principal) e "Nome do Pai:" ou "Nome da Mãe:" (familiares).

RESPOSTA:"""

        # Gera resposta com Groq usando parâmetros otimizados
        try:
            response = groq_client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.02,  # Muito baixo para máxima precisão
                top_p=0.8
            )
            
            answer = response.choices[0].message.content
            logger.info(f"Resposta contextual gerada: {len(answer)} caracteres")
            
        except Exception as e:
            logger.error(f"Erro ao gerar resposta com Groq: {e}")
            answer = "Erro ao processar sua pergunta. Tente novamente."

        # Salva no histórico
        save_to_history(user_email, question, answer, sources, file_id)

        return {
            'answer': answer,
            'sources': sources,
            'context': context[:600] + "..." if len(context) > 600 else context,
            'debug_info': {
                'chunks_found': len(context_parts),
                'context_length': len(context),
                'best_scores': [s['score'] for s in sources[:3]],
                'context_types': [s.get('context_info', '') for s in sources[:3]],
                'file_id': file_id,
                'user_email': user_email,
                'search_type': 'contextual_search_enhanced',
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
            "contextual_search": True,
            "storage": True,
            "llm_semantic_expansion": groq_status,
            "history": True,
            "session_isolation": True,
            "enhanced_precision": True
        },
        "details": {
            "groq_model": "llama3-8b-8192" if groq_status else "Não disponível",
            "search_type": "contextual_search_enhanced",
            "storage_type": "in_memory_by_user",
            "files_indexed": storage_files,
            "history_users": len(history_storage),
            "total_unique_users": len(history_storage),
            "contextual_improvements": [
                "busca_contextual_estrutural",
                "identificacao_secoes_documento",
                "priorizacao_dados_pessoais",
                "distincao_nomes_familiares",
                "bonus_contexto_relevante",
                "precisao_maxima_llm"
            ]
        }
    }
    
    return response

def get_user_history(user_email: str) -> list:
    """Obtém o histórico do usuário específico"""
    return history_storage.get(user_email, [])

# Função auxiliar para salvar chunks (usada pelo upload.py)
def save_text_chunks(file_id: str, chunks: list, user_email: str = DEFAULT_USER_EMAIL):
    """Salva chunks contextuais no armazenamento de texto por usuário"""
    try:
        storage_key = f"{user_email}_{file_id}"
        text_storage[storage_key] = {
            'chunks': chunks,
            'created_at': datetime.now().isoformat(),
            'total_chunks': len(chunks),
            'contextual': True
        }
        
        logger.info(f"Salvos {len(chunks)} chunks contextuais para arquivo {file_id} (usuário: {user_email})")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao salvar chunks: {e}")
        return False