from fastapi import APIRouter, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse
import os
import uuid
import json
from datetime import datetime
from pathlib import Path
import logging
from dotenv import load_dotenv
from pypdf import PdfReader
from groq import Groq
from sentence_transformers import SentenceTransformer
from pinecone import Pinecone, ServerlessSpec

# Configuração
load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter()

# Configurações
UPLOAD_DIR = "user_files"
USER_DATA_FILE = "user_files_data.json"
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Email padrão para usuário sem autenticação
DEFAULT_USER_EMAIL = "usuario@askfile.com"

# Inicialização dos serviços
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Modelo de embedding
try:
    embedding_model_name = os.getenv("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
    embedding_model = SentenceTransformer(embedding_model_name)
    logger.info(f"Modelo de embedding carregado: {embedding_model_name}")
except Exception as e:
    logger.error(f"Erro ao carregar modelo de embedding: {e}")
    embedding_model = None

# Pinecone com configuração correta
try:
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    pinecone_index_name = os.getenv("PINECONE_INDEX_NAME", "askfile")
    pinecone_host = os.getenv("PINECONE_HOST")
    embedding_dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", 768))
    
    if pinecone_api_key:
        # Inicializa cliente Pinecone
        pc = Pinecone(api_key=pinecone_api_key)
        
        # Verifica se o índice existe, se não, cria
        try:
            # Lista índices existentes
            existing_indexes = pc.list_indexes().names()
            
            if pinecone_index_name not in existing_indexes:
                logger.info(f"Criando índice Pinecone: {pinecone_index_name}")
                pc.create_index(
                    name=pinecone_index_name,
                    dimension=embedding_dimensions,
                    metric='cosine',
                    spec=ServerlessSpec(
                        cloud='aws',
                        region='us-east-1'
                    )
                )
                logger.info(f"Índice {pinecone_index_name} criado com sucesso")
            
            # Conecta ao índice
            if pinecone_host:
                pinecone_index = pc.Index(pinecone_index_name, host=pinecone_host)
            else:
                pinecone_index = pc.Index(pinecone_index_name)
            
            logger.info(f"Pinecone conectado ao índice: {pinecone_index_name}")
            
        except Exception as e:
            logger.error(f"Erro ao configurar índice Pinecone: {e}")
            pinecone_index = None
            
    else:
        pinecone_index = None
        logger.warning("PINECONE_API_KEY não configurado")
        
except Exception as e:
    logger.error(f"Erro ao inicializar Pinecone: {e}")
    pinecone_index = None

# Armazenamento em memória dos arquivos dos usuários
user_files_data = {}

def load_user_files_data():
    """Carrega dados dos arquivos dos usuários"""
    global user_files_data
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                user_files_data = json.load(f)
            logger.info(f"Dados de arquivos carregados: {len(user_files_data)} usuários")
    except Exception as e:
        logger.error(f"Erro ao carregar dados de arquivos: {e}")
        user_files_data = {}

def save_user_files_data():
    """Salva dados dos arquivos dos usuários"""
    try:
        with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_files_data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Dados de arquivos salvos: {len(user_files_data)} usuários")
    except Exception as e:
        logger.error(f"Erro ao salvar dados de arquivos: {e}")

# Carrega dados ao inicializar
load_user_files_data()

def extract_text_from_pdf(file_path: str) -> str:
    """Extrai texto do PDF - otimizado para memória"""
    try:
        reader = PdfReader(file_path)
        text_parts = []
        max_pages = 50  # Limita páginas processadas
        
        total_pages = min(len(reader.pages), max_pages)
        
        for page_num in range(total_pages):
            try:
                page = reader.pages[page_num]
                page_text = page.extract_text()
                
                if page_text and page_text.strip():
                    # Limita o texto por página
                    page_text = page_text.strip()
                    if len(page_text) > 5000:  # Máximo 5KB por página
                        page_text = page_text[:5000] + "..."
                    
                    text_parts.append(f"\n\n--- Página {page_num + 1} ---\n{page_text}\n")
                    
            except Exception as e:
                logger.warning(f"Erro na página {page_num + 1}: {e}")
                continue
        
        if not text_parts:
            raise ValueError("Nenhum texto foi extraído do PDF")
        
        # Junta o texto com limite total
        full_text = ''.join(text_parts)
        max_total_size = 200000  # 200KB total
        
        if len(full_text) > max_total_size:
            logger.warning(f"Texto muito grande ({len(full_text)} chars), truncando para {max_total_size}")
            full_text = full_text[:max_total_size] + "\n\n[Texto truncado devido ao tamanho]"
        
        logger.info(f"Texto extraído: {len(full_text):,} caracteres de {total_pages} páginas")
        return full_text
        
    except Exception as e:
        logger.error(f"Erro ao extrair texto: {e}")
        raise HTTPException(status_code=400, detail=f"Erro ao processar PDF: {str(e)}")

def generate_summary(text: str, filename: str) -> str:
    """Gera resumo do documento usando Groq"""
    try:
        if not groq_client:
            return f"Documento PDF: {filename}\n\nEste arquivo foi processado com sucesso e contém {len(text)} caracteres de texto. Faça perguntas sobre o conteúdo para obter informações específicas."
        
        # Pega primeiros caracteres para o resumo
        text_for_summary = text[:8000] if len(text) > 8000 else text
        
        prompt = f"""Analise o seguinte documento PDF e crie um resumo conciso:

ARQUIVO: {filename}

CONTEÚDO:
{text_for_summary}

Crie um resumo de 2-3 parágrafos que inclua:
1. Tipo de documento e propósito principal
2. Principais tópicos e informações abordadas
3. Conclusões ou pontos importantes

Mantenha o resumo claro e objetivo."""

        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.3
        )
        
        summary = response.choices[0].message.content
        
        if not summary or len(summary.strip()) < 50:
            return f"Documento PDF: {filename}\n\nEste arquivo foi processado com sucesso e contém {len(text)} caracteres de texto. Faça perguntas sobre o conteúdo para obter informações específicas."
        
        logger.info(f"Resumo gerado para {filename}: {len(summary)} caracteres")
        return summary
        
    except Exception as e:
        logger.error(f"Erro ao gerar resumo: {e}")
        return f"Documento PDF: {filename}\n\nEste arquivo foi processado com sucesso. Faça perguntas sobre o conteúdo para obter informações específicas."

def create_chunks(text: str, chunk_size: int = 1500, overlap: int = 300) -> list:
    """Divide texto em chunks com sobreposição - otimizado para memória"""
    try:
        # Limita o tamanho do texto para evitar MemoryError
        max_text_size = 500000  # 500KB de texto
        if len(text) > max_text_size:
            logger.warning(f"Texto muito grande ({len(text)} chars), limitando a {max_text_size} chars")
            text = text[:max_text_size]
        
        chunks = []
        text_length = len(text)
        start = 0
        max_chunks = 200  # Limita número de chunks
        
        while start < text_length and len(chunks) < max_chunks:
            end = min(start + chunk_size, text_length)
            
            # Tenta quebrar em final de frase (busca mais eficiente)
            if end < text_length:
                # Busca apenas nos últimos 200 caracteres
                search_start = max(start + chunk_size//2, end - 200)
                for separator in ["\n\n", "\n", ".", "!", "?"]:
                    sep_pos = text.rfind(separator, search_start, end)
                    if sep_pos > search_start:
                        end = sep_pos + len(separator)
                        break
            
            chunk_text = text[start:end].strip()
            
            # Filtra chunks muito pequenos ou muito grandes
            if 50 < len(chunk_text) < 3000:
                chunks.append(chunk_text)
            
            start = end - overlap
            if start >= text_length:
                break
        
        logger.info(f"Texto dividido em {len(chunks)} chunks (tamanho original: {text_length} chars)")
        return chunks
        
    except Exception as e:
        logger.error(f"Erro ao criar chunks: {e}")
        # Fallback: cria chunks menores e mais simples
        simple_chunks = []
        words = text.split()
        current_chunk = []
        current_size = 0
        
        for word in words[:5000]:  # Limita a 5000 palavras
            current_chunk.append(word)
            current_size += len(word) + 1
            
            if current_size >= 800:  # Chunks menores
                chunk_text = ' '.join(current_chunk).strip()
                if len(chunk_text) > 50:
                    simple_chunks.append(chunk_text)
                current_chunk = current_chunk[-20:]  # Mantém sobreposição
                current_size = sum(len(w) + 1 for w in current_chunk)
                
            if len(simple_chunks) >= 150:  # Limita total
                break
        
        # Adiciona último chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk).strip()
            if len(chunk_text) > 50:
                simple_chunks.append(chunk_text)
        
        logger.info(f"Fallback: criados {len(simple_chunks)} chunks simples")
        return simple_chunks

def generate_embeddings(texts: list) -> list:
    """Gera embeddings para lista de textos - otimizado para memória"""
    try:
        if not embedding_model:
            raise RuntimeError("Modelo de embedding não disponível")
        
        # Limita o número de textos processados
        max_texts = 150
        if len(texts) > max_texts:
            logger.warning(f"Muitos chunks ({len(texts)}), limitando a {max_texts}")
            texts = texts[:max_texts]
        
        # Processa em lotes menores para economizar memória
        batch_size = 8  # Reduzido de 16 para 8
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.info(f"Processando lote {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")
            
            try:
                batch_embeddings = embedding_model.encode(
                    batch,
                    batch_size=len(batch),
                    show_progress_bar=False,
                    convert_to_numpy=True,
                    normalize_embeddings=True
                )
                all_embeddings.extend(batch_embeddings.tolist())
                
            except Exception as e:
                logger.error(f"Erro no lote {i//batch_size + 1}: {e}")
                # Em caso de erro, cria embeddings vazios para manter a sincronização
                for _ in batch:
                    all_embeddings.append([0.0] * 768)  # Vetor zero com dimensão padrão
        
        logger.info(f"Embeddings gerados: {len(all_embeddings)} vetores")
        return all_embeddings
        
    except Exception as e:
        logger.error(f"Erro ao gerar embeddings: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar embeddings: {str(e)}")

def index_to_pinecone(chunks: list, embeddings: list, file_id: str, user_email: str) -> dict:
    """Indexa chunks no Pinecone"""
    try:
        if not pinecone_index:
            logger.warning("Pinecone não disponível, salvando apenas localmente")
            return {
                "success": True,
                "total_chunks": len(chunks),
                "vectors_inserted": 0,
                "note": "Pinecone não configurado - dados salvos apenas localmente"
            }
        
        vectors_to_insert = []
        
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            vector_id = f"{user_email}_{file_id}_{i}"
            
            vectors_to_insert.append({
                "id": vector_id,
                "values": embedding,
                "metadata": {
                    "content": chunk,
                    "file_id": file_id,
                    "user_email": user_email,
                    "chunk_order": i,
                    "indexed_at": datetime.now().isoformat()
                }
            })
        
        # Inserção em lotes
        batch_size = 100
        total_inserted = 0
        
        for i in range(0, len(vectors_to_insert), batch_size):
            batch = vectors_to_insert[i:i + batch_size]
            try:
                upsert_response = pinecone_index.upsert(vectors=batch)
                total_inserted += len(batch)
                logger.info(f"Lote {i//batch_size + 1} inserido: {len(batch)} vetores")
            except Exception as e:
                logger.error(f"Erro no lote {i//batch_size + 1}: {e}")
                continue
        
        logger.info(f"Indexação concluída: {total_inserted}/{len(chunks)} vetores inseridos")
        
        return {
            "success": True,
            "total_chunks": len(chunks),
            "vectors_inserted": total_inserted
        }
        
    except Exception as e:
        logger.error(f"Erro na indexação: {e}")
        # Não falha o upload se houver erro na indexação
        return {
            "success": False,
            "total_chunks": len(chunks),
            "vectors_inserted": 0,
            "error": str(e)
        }

@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_file(file: UploadFile = File(...)):
    """
    Upload e processamento de arquivo PDF - SEM AUTENTICAÇÃO
    """
    # Validações
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas arquivos PDF são aceitos"
        )

    # Usa email padrão
    user_email = DEFAULT_USER_EMAIL
    file_path = None
    
    try:
        # Gera ID único para o arquivo
        file_id = f"{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
        
        # Salva arquivo
        file_size = 0
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(8192):
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    os.remove(file_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Arquivo excede o tamanho máximo de {MAX_FILE_SIZE//(1024*1024)}MB"
                    )
                buffer.write(chunk)
        
        logger.info(f"Arquivo salvo: {file_path} ({file_size:,} bytes)")
        logger.info(f"Iniciando processamento de {file.filename} para usuário {user_email}")
        
        # Extrai texto
        text_content = extract_text_from_pdf(file_path)
        
        # Gera resumo
        summary = generate_summary(text_content, file.filename)
        
        # Cria chunks
        chunks = create_chunks(text_content)
        
        if not chunks:
            raise ValueError("Nenhum chunk válido criado")
        
        # Gera embeddings
        embeddings = generate_embeddings(chunks)
        
        # Indexa no Pinecone
        index_result = index_to_pinecone(chunks, embeddings, file_id, user_email)
        
        # Salva dados do usuário
        if user_email not in user_files_data:
            user_files_data[user_email] = {}
        
        user_files_data[user_email][file_id] = {
            'original_name': file.filename,
            'file_path': file_path,
            'summary': summary,
            'upload_date': datetime.now().isoformat(),
            'file_size': file_size,
            'chunks_count': len(chunks),
            'processing_result': index_result
        }
        
        # Persiste dados
        save_user_files_data()
        
        logger.info(f"Processamento concluído para {file.filename}")
        
        return {
            "file_id": file_id,
            "original_name": file.filename,
            "summary": summary,
            "size": file_size,
            "chunks_created": len(chunks),
            "vectors_indexed": index_result.get("vectors_inserted", 0),
            "upload_date": datetime.now().isoformat(),
            "status": "success",
            "message": f"Arquivo '{file.filename}' processado com sucesso!",
            "processing_details": index_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Remove arquivo em caso de erro
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            
        logger.error(f"Erro no processamento de {file.filename}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha no processamento do arquivo: {str(e)}"
        )

@router.get("/user-files")
async def get_user_files():
    """Lista arquivos do usuário - SEM AUTENTICAÇÃO"""
    user_email = DEFAULT_USER_EMAIL
    
    if user_email not in user_files_data:
        return {"files": []}
    
    files = []
    for file_id, file_data in user_files_data[user_email].items():
        files.append({
            "file_id": file_id,
            "original_name": file_data["original_name"],
            "summary": file_data["summary"],
            "upload_date": file_data["upload_date"],
            "file_size": file_data["file_size"],
            "chunks_count": file_data.get("chunks_count", 0),
            "vectors_indexed": file_data.get("processing_result", {}).get("vectors_inserted", 0)
        })
    
    return {"files": files}

@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """Remove arquivo do usuário - SEM AUTENTICAÇÃO"""
    user_email = DEFAULT_USER_EMAIL
    
    if user_email not in user_files_data or file_id not in user_files_data[user_email]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo não encontrado"
        )
    
    try:
        # Remove arquivo físico
        file_data = user_files_data[user_email][file_id]
        if os.path.exists(file_data["file_path"]):
            os.remove(file_data["file_path"])
            logger.info(f"Arquivo físico removido: {file_data['file_path']}")
        
        # Remove vetores do Pinecone
        if pinecone_index:
            try:
                # Lista de IDs dos vetores a serem removidos
                chunks_count = file_data.get("chunks_count", 0)
                vector_ids_to_delete = [f"{user_email}_{file_id}_{i}" for i in range(chunks_count)]
                
                if vector_ids_to_delete:
                    delete_response = pinecone_index.delete(ids=vector_ids_to_delete)
                    logger.info(f"Vetores removidos do Pinecone: {len(vector_ids_to_delete)} IDs")
                
            except Exception as e:
                logger.warning(f"Erro ao remover vetores do Pinecone: {e}")
        
        # Remove dados do usuário
        del user_files_data[user_email][file_id]
        save_user_files_data()
        
        logger.info(f"Arquivo {file_id} removido completamente para usuário {user_email}")
        
        return {
            "success": True, 
            "message": "Arquivo removido com sucesso",
            "file_id": file_id
        }
        
    except Exception as e:
        logger.error(f"Erro ao remover arquivo {file_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao remover arquivo"
        )

@router.get("/status")
async def upload_status():
    """Verifica status dos serviços de upload"""
    
    # Testa Pinecone
    pinecone_status = False
    pinecone_stats = None
    if pinecone_index:
        try:
            pinecone_stats = pinecone_index.describe_index_stats()
            pinecone_status = True
        except Exception as e:
            logger.error(f"Erro ao testar Pinecone: {e}")
    
    # Testa Groq
    groq_status = groq_client is not None
    
    # Testa modelo de embedding
    embedding_status = embedding_model is not None
    
    status = {
        "embedding_model": embedding_status,
        "pinecone": pinecone_status,
        "groq": groq_status,
        "upload_directory": os.path.exists(UPLOAD_DIR)
    }
    
    response = {
        "status": "ok" if all(status.values()) else "partial",
        "services": status,
        "details": {
            "embedding_model": embedding_model_name if embedding_model else "Não carregado",
            "pinecone_index": os.getenv("PINECONE_INDEX_NAME", "Não configurado"),
            "pinecone_stats": pinecone_stats,
            "groq_model": "llama3-8b-8192" if groq_status else "Não disponível",
            "upload_directory": UPLOAD_DIR,
            "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024)
        }
    }
    
    return response