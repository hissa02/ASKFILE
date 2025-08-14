from fastapi import APIRouter, UploadFile, File, HTTPException, status
import os
import uuid
import json
from datetime import datetime
import logging
from dotenv import load_dotenv
from pypdf import PdfReader
from groq import Groq

# Configuração
load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter()

# Configurações
UPLOAD_DIR = "user_files"
USER_DATA_FILE = "user_files_data.json"

# Garante que o diretório existe
try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    logger.info(f"✅ Diretório de upload: {os.path.abspath(UPLOAD_DIR)}")
except Exception as e:
    logger.error(f"❌ Erro ao criar diretório: {e}")

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB para ser mais leve

# Email padrão
DEFAULT_USER_EMAIL = "usuario@askfile.com"

# Serviços
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Armazenamento em memória
user_files_data = {}

def load_user_files_data():
    """Carrega dados dos arquivos"""
    global user_files_data
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                user_files_data = json.load(f)
            logger.info(f"Dados carregados: {len(user_files_data)} usuários")
    except Exception as e:
        logger.error(f"Erro ao carregar dados: {e}")
        user_files_data = {}

def save_user_files_data():
    """Salva dados dos arquivos"""
    try:
        with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_files_data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Dados salvos: {len(user_files_data)} usuários")
    except Exception as e:
        logger.error(f"Erro ao salvar dados: {e}")

# Carrega dados
load_user_files_data()

def extract_text_from_pdf(file_path: str) -> str:
    """Extrai texto do PDF"""
    try:
        reader = PdfReader(file_path)
        text_parts = []
        max_pages = 30  # Limita páginas
        
        total_pages = min(len(reader.pages), max_pages)
        
        for page_num in range(total_pages):
            try:
                page = reader.pages[page_num]
                page_text = page.extract_text()
                
                if page_text and page_text.strip():
                    page_text = page_text.strip()
                    if len(page_text) > 4000:  # 4KB por página
                        page_text = page_text[:4000] + "..."
                    
                    text_parts.append(f"\n--- Página {page_num + 1} ---\n{page_text}")
                    
            except Exception as e:
                logger.warning(f"Erro na página {page_num + 1}: {e}")
                continue
        
        if not text_parts:
            raise ValueError("Nenhum texto extraído do PDF")
        
        full_text = '\n\n'.join(text_parts)
        max_total = 150000  # 150KB total
        
        if len(full_text) > max_total:
            logger.warning(f"Texto truncado de {len(full_text)} para {max_total} chars")
            full_text = full_text[:max_total] + "\n\n[Documento truncado]"
        
        logger.info(f"✅ Texto extraído: {len(full_text):,} caracteres de {total_pages} páginas")
        return full_text
        
    except Exception as e:
        logger.error(f"❌ Erro ao extrair texto: {e}")
        raise HTTPException(status_code=400, detail=f"Erro ao processar PDF: {str(e)}")

def generate_summary(text: str, filename: str) -> str:
    """Gera resumo usando Groq"""
    try:
        if not groq_client:
            return f"📄 {filename}\n\nArquivo processado com {len(text)} caracteres. Faça perguntas sobre o conteúdo."
        
        # Usa apenas parte do texto para o resumo
        text_sample = text[:6000] if len(text) > 6000 else text
        
        prompt = f"""Analise este documento PDF e crie um resumo em português:

ARQUIVO: {filename}

CONTEÚDO:
{text_sample}

Crie um resumo de 2-3 parágrafos incluindo:
1. Tipo de documento e objetivo
2. Principais tópicos abordados  
3. Pontos importantes ou conclusões

Seja claro e objetivo."""

        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3
        )
        
        summary = response.choices[0].message.content
        
        if not summary or len(summary.strip()) < 30:
            return f"📄 {filename}\n\nArquivo processado com {len(text)} caracteres. Faça perguntas sobre o conteúdo."
        
        logger.info(f"✅ Resumo gerado: {len(summary)} caracteres")
        return summary
        
    except Exception as e:
        logger.error(f"❌ Erro ao gerar resumo: {e}")
        return f"📄 {filename}\n\nArquivo processado. Faça perguntas sobre o conteúdo."

def create_text_chunks(text: str, chunk_size: int = 1200, overlap: int = 200) -> list:
    """Cria chunks de texto inteligentes"""
    try:
        chunks = []
        text_length = len(text)
        start = 0
        max_chunks = 100  # Limita chunks
        
        while start < text_length and len(chunks) < max_chunks:
            end = min(start + chunk_size, text_length)
            
            # Busca quebra natural
            if end < text_length:
                for separator in ["\n\n", "\n", ". ", "! ", "? "]:
                    sep_pos = text.rfind(separator, start + chunk_size//2, end)
                    if sep_pos > start + chunk_size//2:
                        end = sep_pos + len(separator)
                        break
            
            chunk_text = text[start:end].strip()
            
            # Filtra chunks válidos
            if 80 < len(chunk_text) < 2000:
                chunks.append(chunk_text)
            
            start = end - overlap
            if start >= text_length:
                break
        
        logger.info(f"✅ Criados {len(chunks)} chunks")
        return chunks
        
    except Exception as e:
        logger.error(f"❌ Erro ao criar chunks: {e}")
        # Fallback simples
        simple_chunks = []
        words = text.split()
        current_chunk = []
        
        for word in words[:3000]:  # Limita palavras
            current_chunk.append(word)
            if len(' '.join(current_chunk)) > 800:
                chunk_text = ' '.join(current_chunk)
                if len(chunk_text) > 80:
                    simple_chunks.append(chunk_text)
                current_chunk = current_chunk[-10:]  # Mantém overlap
                
            if len(simple_chunks) >= 80:
                break
        
        # Último chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            if len(chunk_text) > 80:
                simple_chunks.append(chunk_text)
        
        logger.info(f"✅ Fallback: {len(simple_chunks)} chunks simples")
        return simple_chunks

@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_file(file: UploadFile = File(...)):
    """
    Upload e processamento de PDF
    """
    # Validações
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas arquivos PDF são aceitos"
        )

    user_email = DEFAULT_USER_EMAIL
    file_path = None
    
    try:
        # ID único
        file_id = f"{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
        
        # Salva arquivo com verificação adicional
        file_size = 0
        try:
            with open(file_path, "wb") as buffer:
                while chunk := await file.read(8192):
                    file_size += len(chunk)
                    if file_size > MAX_FILE_SIZE:
                        # Remove arquivo se muito grande
                        try:
                            os.remove(file_path)
                        except:
                            pass
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"Arquivo muito grande. Máximo: {MAX_FILE_SIZE//(1024*1024)}MB"
                        )
                    buffer.write(chunk)
                    
            logger.info(f"✅ Arquivo salvo: {file_path} ({file_size:,} bytes)")
            
            # Verifica se o arquivo foi realmente criado
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Arquivo não foi criado: {file_path}")
                
        except Exception as save_error:
            logger.error(f"❌ Erro ao salvar arquivo: {save_error}")
            # Tenta remover arquivo parcial
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao salvar arquivo: {str(save_error)}"
            )
        
        # Processa PDF
        text_content = extract_text_from_pdf(file_path)
        summary = generate_summary(text_content, file.filename)
        chunks = create_text_chunks(text_content)
        
        if not chunks:
            raise ValueError("Nenhum chunk criado")
        
        # Salva chunks no chat.py
        try:
            from routes.chat import save_text_chunks
            save_text_chunks(file_id, chunks, user_email)
            logger.info(f"✅ Chunks salvos no sistema de chat")
        except Exception as e:
            logger.warning(f"⚠️ Erro ao salvar chunks: {e}")
        
        # Salva dados do arquivo
        if user_email not in user_files_data:
            user_files_data[user_email] = {}
        
        user_files_data[user_email][file_id] = {
            'original_name': file.filename,
            'file_path': file_path,
            'summary': summary,
            'upload_date': datetime.now().isoformat(),
            'file_size': file_size,
            'chunks_count': len(chunks),
            'text_length': len(text_content)
        }
        
        save_user_files_data()
        
        logger.info(f"🎉 Processamento concluído: {file.filename}")
        
        return {
            "file_id": file_id,
            "original_name": file.filename,
            "summary": summary,
            "size": file_size,
            "chunks_created": len(chunks),
            "upload_date": datetime.now().isoformat(),
            "status": "success",
            "message": f"✅ Arquivo '{file.filename}' processado com sucesso!"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Remove arquivo em caso de erro
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            
        logger.error(f"❌ Erro no processamento: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha no processamento: {str(e)}"
        )

@router.get("/user-files")
async def get_user_files():
    """Lista arquivos do usuário"""
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
            "chunks_count": file_data.get("chunks_count", 0)
        })
    
    return {"files": files}

@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """Remove arquivo"""
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
            logger.info(f"🗑️ Arquivo físico removido")
        
        # Remove dados
        del user_files_data[user_email][file_id]
        save_user_files_data()
        
        logger.info(f"✅ Arquivo {file_id} removido")
        
        return {
            "success": True, 
            "message": "Arquivo removido com sucesso",
            "file_id": file_id
        }
        
    except Exception as e:
        logger.error(f"❌ Erro ao remover arquivo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao remover arquivo"
        )

@router.get("/status")
async def upload_status():
    """Status dos serviços"""
    
    groq_status = groq_client is not None
    
    response = {
        "status": "ok" if groq_status else "partial",
        "services": {
            "groq": groq_status,
            "pdf_processing": True,
            "text_chunking": True,
            "upload_directory": os.path.exists(UPLOAD_DIR)
        },
        "details": {
            "groq_model": "llama3-8b-8192" if groq_status else "Não disponível",
            "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
            "upload_directory": UPLOAD_DIR
        }
    }
    
    return response