from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv
import os
import logging
import re
from datetime import datetime
import difflib

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_USER_EMAIL = "usuario@askfile.com"

text_storage = {}
history_storage = {}

class ChatRequest(BaseModel):
    question: str
    file_id: str = None
    user_email: str = DEFAULT_USER_EMAIL

def detect_document_context(text: str) -> str:
    """Detecta o contexto do documento baseado em padrões"""
    contexts = {
        'academico': ['nota', 'disciplina', 'aprovado', 'reprovado', 'media', 'credito', 'historico', 'curso', 'semestre'],
        'financeiro': ['valor', 'pagamento', 'debito', 'credito', 'saldo', 'fatura', 'boleto', 'conta'],
        'juridico': ['processo', 'tribunal', 'acao', 'sentenca', 'advogado', 'lei', 'artigo'],
        'medico': ['paciente', 'exame', 'medicamento', 'sintoma', 'diagnostico', 'tratamento'],
        'tecnico': ['sistema', 'configuracao', 'instalacao', 'manutencao', 'especificacao']
    }
    
    text_lower = text.lower()
    scores = {}
    
    for context, keywords in contexts.items():
        score = sum(text_lower.count(keyword) for keyword in keywords)
        scores[context] = score
    
    return max(scores, key=scores.get) if max(scores.values()) > 0 else 'geral'

def extract_key_entities(text: str, context: str) -> dict:
    """Extrai entidades chave baseadas no contexto"""
    entities = {}
    
    if context == 'academico':
        # Notas e medias
        notas = re.findall(r'(?:nota|média|pontos?)[:\s]*([0-9]+[,.]?[0-9]*)', text, re.IGNORECASE)
        entities['notas'] = notas
        
        # Situacoes academicas
        situacoes = re.findall(r'(aprovado|reprovado|cancelado|trancado|dispensado)', text, re.IGNORECASE)
        entities['situacoes'] = situacoes
        
        # Disciplinas
        disciplinas = re.findall(r'(?:disciplina|matéria|componente)[^0-9\n]*?([A-ZÁÀÁÂÃÉÊÍÓÔÕÚÇ][^0-9\n]{10,50})', text, re.IGNORECASE)
        entities['disciplinas'] = disciplinas
        
        # Periodos
        periodos = re.findall(r'(\d{4}\.\d{1,2})', text)
        entities['periodos'] = periodos
    
    elif context == 'financeiro':
        # Valores monetarios
        valores = re.findall(r'R?\$?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)', text)
        entities['valores'] = valores
        
        # Datas
        datas = re.findall(r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})', text)
        entities['datas'] = datas
    
    return entities

def generate_enhanced_search_terms(query: str, context: str, entities: dict) -> list:
    """Gera termos de busca melhorados baseados no contexto"""
    try:
        base_prompt = f"""
        Pergunta: "{query}"
        Contexto do documento: {context}
        Entidades encontradas: {entities}
        
        Gere termos de busca alternativos incluindo:
        - Sinônimos das palavras principais
        - Variações da pergunta
        - Termos técnicos relacionados ao contexto
        - Palavras-chave que podem aparecer no documento
        
        Retorne apenas os termos separados por vírgula:
        """
        
        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": base_prompt}],
            max_tokens=200,
            temperature=0.3
        )
        
        terms_text = response.choices[0].message.content
        terms = [term.strip().lower() for term in terms_text.split(',') if term.strip()]
        
        # Adiciona query original
        terms.insert(0, query.lower())
        
        # Remove duplicatas
        seen = set()
        unique_terms = []
        for term in terms:
            if term not in seen and len(term) >= 2:
                seen.add(term)
                unique_terms.append(term)
        
        return unique_terms[:15]
        
    except Exception as e:
        logger.error(f"Erro ao gerar termos: {e}")
        return [query.lower()]

def calculate_similarity_score(query_word: str, chunk_word: str) -> float:
    """Calcula similaridade entre palavras usando sequencematcher"""
    return difflib.SequenceMatcher(None, query_word.lower(), chunk_word.lower()).ratio()

def smart_text_search(query: str, file_id: str, user_email: str, max_results: int = 8) -> tuple:
    """Busca inteligente melhorada"""
    try:
        storage_key = f"{user_email}_{file_id}"
        if storage_key not in text_storage:
            return [], []
        
        file_data = text_storage[storage_key]
        chunks = file_data.get('chunks', [])
        
        if not chunks:
            return [], []
        
        # Analisa contexto do documento
        full_text = ' '.join(chunks[:3])
        doc_context = detect_document_context(full_text)
        entities = extract_key_entities(full_text, doc_context)
        
        logger.info(f"Contexto detectado: {doc_context}")
        
        # Gera termos de busca melhorados
        search_terms = generate_enhanced_search_terms(query, doc_context, entities)
        
        scored_chunks = []
        
        for i, chunk in enumerate(chunks):
            chunk_lower = chunk.lower()
            score = 0
            matched_terms = []
            
            # Busca exata por termos
            for term_idx, term in enumerate(search_terms):
                exact_matches = chunk_lower.count(term)
                if exact_matches > 0:
                    weight = 4.0 if term_idx == 0 else max(2.5 - (term_idx * 0.1), 0.8)
                    score += exact_matches * weight
                    matched_terms.append(term)
            
            # Busca por similaridade de palavras
            query_words = re.findall(r'\w+', query.lower())
            chunk_words = re.findall(r'\w+', chunk_lower)
            
            for q_word in query_words:
                if len(q_word) > 3:
                    for c_word in chunk_words:
                        if len(c_word) > 3:
                            similarity = calculate_similarity_score(q_word, c_word)
                            if similarity > 0.85:
                                score += similarity * 2.0
                                matched_terms.append(f"{q_word}~{c_word}")
            
            # Proximidade entre termos importantes
            for i_term in range(min(3, len(search_terms) - 1)):
                term1, term2 = search_terms[i_term], search_terms[i_term + 1]
                if term1 in chunk_lower and term2 in chunk_lower:
                    pos1 = chunk_lower.find(term1)
                    pos2 = chunk_lower.find(term2)
                    distance = abs(pos1 - pos2)
                    if distance < 80:
                        proximity_bonus = 2.0 * (80 - distance) / 80
                        score += proximity_bonus
                        matched_terms.append("proximidade")
            
            # Bonus para multiplos termos
            unique_found = len(set(term for term in search_terms if term in chunk_lower))
            if unique_found > 1:
                score += unique_found * 1.5
                matched_terms.append(f"multi_termos_{unique_found}")
            
            # Busca por numeros na query
            numbers_in_query = re.findall(r'\b\d+(?:[.,]\d+)?\b', query)
            for num in numbers_in_query:
                if num in chunk or num.replace(',', '.') in chunk or num.replace('.', ',') in chunk:
                    score += 3.5
                    matched_terms.append(f"numero_{num}")
            
            # Bonus para contexto especifico
            if doc_context == 'academico':
                academic_keywords = ['aprovado', 'reprovado', 'nota', 'média', 'disciplina', 'matéria']
                for keyword in academic_keywords:
                    if keyword in query.lower() and keyword in chunk_lower:
                        score += 2.0
                        matched_terms.append(f"contexto_{keyword}")
            
            if score > 0:
                scored_chunks.append({
                    'content': chunk,
                    'score': score,
                    'index': i,
                    'matched_terms': matched_terms[:8],
                    'context': doc_context
                })
        
        # Ordena por score
        scored_chunks.sort(key=lambda x: x['score'], reverse=True)
        best_chunks = scored_chunks[:max_results]
        
        context_parts = [chunk['content'] for chunk in best_chunks]
        sources = [{
            'content': chunk['content'][:180] + "..." if len(chunk['content']) > 180 else chunk['content'],
            'score': round(chunk['score'], 2),
            'file_id': file_id,
            'matched_terms': chunk['matched_terms'],
            'context': chunk['context']
        } for chunk in best_chunks]
        
        logger.info(f"Busca melhorada retornou {len(context_parts)} resultados para: '{query}'")
        if best_chunks:
            logger.info(f"Melhor score: {best_chunks[0]['score']:.2f}")
        
        return context_parts, sources
        
    except Exception as e:
        logger.error(f"Erro na busca melhorada: {e}")
        return [], []

def save_to_history(user_email: str, question: str, answer: str, sources: list, file_id: str = None):
    """Salva no historico"""
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
        
        # Limita historico
        if len(history_storage[user_email]) > 50:
            history_storage[user_email] = history_storage[user_email][-50:]
        
        logger.info(f"Item salvo no historico para {user_email}")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao salvar historico: {e}")
        return False

@router.post("")
async def send_message(request: ChatRequest = Body(...)):
    """Endpoint principal para chat"""
    try:
        question = request.question
        file_id = request.file_id
        user_email = request.user_email or DEFAULT_USER_EMAIL
        
        if not question:
            raise HTTPException(status_code=400, detail='Pergunta obrigatoria')

        if not file_id:
            raise HTTPException(status_code=400, detail='ID do arquivo obrigatorio')

        logger.info(f"Pergunta recebida: {question} (usuario: {user_email})")

        if not groq_client:
            raise HTTPException(status_code=503, detail="Servico de IA nao disponivel")

        # Busca melhorada
        context_parts, sources = smart_text_search(
            query=question,
            file_id=file_id,
            user_email=user_email,
            max_results=10
        )

        if not context_parts:
            logger.warning(f"Nenhum contexto encontrado para: {question}")
            answer = "Nao encontrei informacoes relevantes no arquivo para responder essa pergunta.\n\nDicas para melhor resultado:\n\n1. Use palavras-chave especificas do documento\n2. Tente reformular a pergunta de forma mais direta\n3. Verifique se o conteudo esta relacionado ao arquivo enviado"
            
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
                    'search_type': 'enhanced_search'
                }
            }

        # Constroi contexto
        context = "\n\n---\n\n".join(context_parts)
        
        logger.info(f"Contexto encontrado: {len(context_parts)} partes, {len(context)} caracteres")

        # Prompt melhorado
        prompt = f"""Voce e um assistente especializado em analisar documentos e responder perguntas com base no conteudo fornecido.

PERGUNTA DO USUARIO:
{question}

CONTEXTO DO DOCUMENTO:
{context}

INSTRUCOES:
- Responda APENAS com base no contexto fornecido
- Se a informacao nao estiver no contexto, diga que nao encontrou no documento
- Seja preciso e cite partes especificas quando relevante
- Use linguagem clara e organize a resposta de forma estruturada
- Se houver dados, numeros ou fatos especificos, mencione-os
- Para perguntas sobre notas ou situacoes academicas, seja muito preciso nos valores e status
- Quando houver multiplas ocorrencias de algo, liste todas claramente

RESPOSTA:"""

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
            logger.error(f"Erro ao gerar resposta: {e}")
            answer = "Erro ao processar sua pergunta. Tente novamente."

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
                'user_email': user_email,
                'search_type': 'enhanced_search'
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro interno: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

@router.get("/status")
async def chat_status():
    """Status dos servicos"""
    
    groq_status = groq_client is not None
    storage_files = len(text_storage)
    
    response = {
        "status": "ok" if groq_status else "partial",
        "services": {
            "groq": groq_status,
            "enhanced_search": True,
            "context_detection": True,
            "similarity_matching": True,
            "storage": True,
            "history": True
        },
        "details": {
            "groq_model": "llama3-8b-8192" if groq_status else "Nao disponivel",
            "search_type": "enhanced_contextual_search",
            "storage_type": "in_memory_by_user",
            "files_indexed": storage_files,
            "history_users": len(history_storage),
            "improvements": [
                "deteccao_contexto_documento",
                "extracao_entidades",
                "busca_similaridade",
                "analise_proximidade_termos",
                "scoring_melhorado"
            ]
        }
    }
    
    return response

def get_user_history(user_email: str) -> list:
    """Obtem historico do usuario"""
    return history_storage.get(user_email, [])

def save_text_chunks(file_id: str, chunks: list, user_email: str = DEFAULT_USER_EMAIL):
    """Salva chunks no armazenamento"""
    try:
        storage_key = f"{user_email}_{file_id}"
        text_storage[storage_key] = {
            'chunks': chunks,
            'created_at': datetime.now().isoformat(),
            'total_chunks': len(chunks)
        }
        
        logger.info(f"Salvos {len(chunks)} chunks para arquivo {file_id} (usuario: {user_email})")
        return True
        
    except Exception as e:
        logger.error(f"Erro ao salvar chunks: {e}")
        return False