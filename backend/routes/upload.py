from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
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
from pinecone import Pinecone
from routes.login import get_current_active_user

# Configuração
load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter()

# Configurações
UPLOAD_DIR = "user_files"
USER_DATA_FILE = "user_files_data.json"
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Inicialização dos serviços
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Modelo de embedding
try:
    embedding_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-mpnet-base-v2')
    logger.info("Modelo de embedding carregado com sucesso")
except Exception as e:
    logger.error(f"Erro ao carregar modelo de embedding: {e}")
    embedding_model = None

# Pinecone
try:
    pinecone_client = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    pinecone_index = pinecone_client.Index(os.getenv("PINECONE_INDEX_NAME"))
    logger.info("Pinecone inicializado com sucesso")
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
    """Extrai texto do PDF"""
    try:
        reader = PdfReader(file_path)
        text = ""
        
        for page_num, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text and page_text.strip():
                    text += f"\n\n--- Página {page_num + 1} ---\n{page_text.strip()}\n"
            except Exception as e:
                logger.warning(f"Erro na página {page_num + 1}: {e}")
                continue
        
        if not text.strip():
            raise ValueError("Nenhum texto foi extraído do PDF")
        
        logger.info(f"Texto extraído: {len(text):,} caracteres")
        return text
        
    except Exception as e:
        logger.error(f"Erro ao extrair texto: {e}")
        raise HTTPException(status_code=400, detail=f"Erro ao processar PDF: {str(e)}")

def generate_summary(text: str, filename: str) -> str:
    """Gera resumo do documento usando Groq"""
    try:
        if not groq_client:
            return f"Resumo não disponível para {filename}"
        
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

def create_chunks(text: str, chunk_size: int = 2000, overlap: int = 400) -> list:
    """Divide texto em chunks com sobreposição"""
    chunks = []
    text_length = len(text)
    start = 0
    
    while start < text_length:
        end = min(start + chunk_size, text_length)
        
        # Tenta quebrar em final de frase
        if end < text_length:
            for separator in ["\n\n", "\n", ".", "!", "?"]:
                sep_pos = text.rfind(separator, max(start + chunk_size//2, start), end)
                if sep_pos > start + chunk_size//2:
                    end = sep_pos + len(separator)
                    break
        
        chunk_text = text[start:end].strip()
        
        if len(chunk_text) > 50:
            chunks.append(chunk_text)
        
        start = end - overlap
        if start >= text_length:
            break
    
    return chunks

def generate_embeddings(texts: list) -> list:
    """Gera embeddings para lista de textos"""
    try:
        if not embedding_model:
            raise RuntimeError("Modelo de embedding não disponível")
        
        embeddings = embedding_model.encode(
            texts,
            batch_size=16,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        
        return embeddings.tolist()
        
    except Exception as e:
        logger.error(f"Erro ao gerar embeddings: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao gerar embeddings: {str(e)}")

def index_to_pinecone(chunks: list, embeddings: list, file_id: str, user_email: str) -> dict:
    """Indexa chunks no Pinecone"""
    try:
        if not pinecone_index:
            raise RuntimeError("Pinecone não disponível")
        
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
                pinecone_index.upsert(vectors=batch)
                total_inserted += len(batch)
            except Exception as e:
                logger.error(f"Erro no lote: {e}")
                continue
        
        return {
            "success": True,
            "total_chunks": len(chunks),
            "vectors_inserted": total_inserted
        }
        
    except Exception as e:
        logger.error(f"Erro na indexação: {e}")
        raise HTTPException(status_code=500, detail=f"Erro na indexação: {str(e)}")

@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user)
):
    """
    Upload e processamento de arquivo PDF
    """
    # Validações
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas arquivos PDF são aceitos"
        )

    user_email = current_user["email"]
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
        
        return {
            "file_id": file_id,
            "original_name": file.filename,
            "summary": summary,
            "size": file_size,
            "chunks_created": len(chunks),
            "upload_date": datetime.now().isoformat(),
            "status": "success",
            "message": f"Arquivo '{file.filename}' processado com sucesso!"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Remove arquivo em caso de erro
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            
        logger.error(f"Erro no processamento: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha no processamento do arquivo: {str(e)}"
        )

@router.get("/user-files")
async def get_user_files(current_user: dict = Depends(get_current_active_user)):
    """Lista arquivos do usuário"""
    user_email = current_user["email"]
    
    if user_email not in user_files_data:
        return {"files": []}
    
    files = []
    for file_id, file_data in user_files_data[user_email].items():
        files.append({
            "file_id": file_id,
            "original_name": file_data["original_name"],
            "summary": file_data["summary"],
            "upload_date": file_data["upload_date"],
            "file_size": file_data["file_size"]
        })
    
    return {"files": files}

@router.delete("/{file_id}")
async def delete_file(file_id: str, current_user: dict = Depends(get_current_active_user)):
    """Remove arquivo do usuário"""
    user_email = current_user["email"]
    
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
        
        # Remove dados
        del user_files_data[user_email][file_id]
        save_user_files_data()
        
        # TODO: Remover vetores do Pinecone (implementar conforme necessário)
        
        return {"success": True, "message": "Arquivo removido com sucesso"}
        
    except Exception as e:
        logger.error(f"Erro ao remover arquivo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao remover arquivo"
        )