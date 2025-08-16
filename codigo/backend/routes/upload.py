from fastapi import APIRouter, UploadFile, File, HTTPException, status, Form
from typing import Optional
import os
import uuid
import json
from datetime import datetime
import logging
from dotenv import load_dotenv
from pypdf import PdfReader
from groq import Groq
import re

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = "user_files"
USER_DATA_FILE = "user_files_data.json"

try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    logger.info(f"Diretorio de upload: {os.path.abspath(UPLOAD_DIR)}")
except Exception as e:
    logger.error(f"Erro ao criar diretorio: {e}")

MAX_FILE_SIZE = 25 * 1024 * 1024

DEFAULT_USER_EMAIL = "usuario@askfile.com"

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

user_files_data = {}

def load_user_files_data():
    """Carrega dados dos arquivos"""
    global user_files_data
    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                user_files_data = json.load(f)
            logger.info(f"Dados carregados: {len(user_files_data)} usuarios")
    except Exception as e:
        logger.error(f"Erro ao carregar dados: {e}")
        user_files_data = {}

def save_user_files_data():
    """Salva dados dos arquivos"""
    try:
        with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_files_data, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"Dados salvos: {len(user_files_data)} usuarios")
    except Exception as e:
        logger.error(f"Erro ao salvar dados: {e}")

load_user_files_data()

def clean_text(text: str) -> str:
    """Limpa e normaliza o texto extraido"""
    if not text:
        return ""
    
    # Remove quebras de linha excessivas
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    
    # Normaliza espacos
    text = re.sub(r' +', ' ', text)
    
    # Remove espacos no inicio e fim
    text = text.strip()
    
    # Corrige encoding issues comuns
    text = text.replace('â€™', "'")
    text = text.replace('â€œ', '"')
    text = text.replace('â€', '"')
    text = text.replace('Ã©', 'é')
    text = text.replace('Ã¡', 'á')
    text = text.replace('Ã§', 'ç')
    text = text.replace('Ã£', 'ã')
    text = text.replace('Ãº', 'ú')
    text = text.replace('Ã­', 'í')
    text = text.replace('Ã³', 'ó')
    
    return text

def extract_text_from_pdf(file_path: str) -> str:
    """Extrai texto do PDF com tratamento melhorado"""
    try:
        reader = PdfReader(file_path)
        text_parts = []
        max_pages = 50
        
        total_pages = min(len(reader.pages), max_pages)
        
        for page_num in range(total_pages):
            try:
                page = reader.pages[page_num]
                page_text = page.extract_text()
                
                if page_text and page_text.strip():
                    # Limpa o texto da pagina
                    page_text = clean_text(page_text)
                    
                    if len(page_text) > 6000:
                        page_text = page_text[:6000] + "..."
                    
                    text_parts.append(f"\n=== Pagina {page_num + 1} ===\n{page_text}")
                    
            except Exception as e:
                logger.warning(f"Erro na pagina {page_num + 1}: {e}")
                continue
        
        if not text_parts:
            raise ValueError("Nenhum texto extraido do PDF")
        
        full_text = '\n\n'.join(text_parts)
        max_total = 200000
        
        if len(full_text) > max_total:
            logger.warning(f"Texto truncado de {len(full_text)} para {max_total} chars")
            full_text = full_text[:max_total] + "\n\n[Documento truncado]"
        
        logger.info(f"Texto extraido: {len(full_text):,} caracteres de {total_pages} paginas")
        return full_text
        
    except Exception as e:
        logger.error(f"Erro ao extrair texto: {e}")
        raise HTTPException(status_code=400, detail=f"Erro ao processar PDF: {str(e)}")

def generate_summary(text: str, filename: str) -> str:
    """Gera resumo usando Groq com prompt melhorado"""
    try:
        if not groq_client:
            return f"Arquivo {filename} processado com {len(text)} caracteres. Faca perguntas sobre o conteudo."
        
        # Detecta tipo de documento
        text_lower = text.lower()
        doc_type = "geral"
        
        if any(word in text_lower for word in ['nota', 'disciplina', 'aprovado', 'reprovado', 'credito']):
            doc_type = "academico"
        elif any(word in text_lower for word in ['valor', 'pagamento', 'fatura', 'debito']):
            doc_type = "financeiro"
        elif any(word in text_lower for word in ['processo', 'lei', 'artigo', 'tribunal']):
            doc_type = "juridico"
        elif any(word in text_lower for word in ['paciente', 'exame', 'medicamento']):
            doc_type = "medico"
        
        text_sample = text[:8000] if len(text) > 8000 else text
        
        prompt = f"""Analise este documento PDF e crie um resumo detalhado em portugues:

ARQUIVO: {filename}
TIPO DETECTADO: {doc_type}

CONTEUDO:
{text_sample}

Crie um resumo de 3-4 paragrafos incluindo:
1. Tipo de documento e seu objetivo principal
2. Principais topicos e secoes abordados
3. Dados importantes, numeros ou fatos relevantes (seja muito especifico com valores e datas)
4. Conclusoes ou pontos principais destacados

Para documentos academicos, mencione disciplinas, notas, situacoes academicas.
Para documentos financeiros, mencione valores, datas, status de pagamentos.
Seja especifico e mencione informacoes que podem ser uteis para consultas futuras.
Use linguagem clara e objetiva."""

        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.3
        )
        
        summary = response.choices[0].message.content
        
        if not summary or len(summary.strip()) < 50:
            return f"Arquivo {filename} processado com {len(text)} caracteres. Faca perguntas sobre o conteudo."
        
        logger.info(f"Resumo gerado: {len(summary)} caracteres")
        return summary
        
    except Exception as e:
        logger.error(f"Erro ao gerar resumo: {e}")
        return f"Arquivo {filename} processado. Faca perguntas sobre o conteudo."

def create_text_chunks(text: str, chunk_size: int = 1000, overlap: int = 150) -> list:
    """Cria chunks de texto otimizados"""
    try:
        chunks = []
        max_chunks = 150
        
        # Pre-processamento: identifica secoes
        sections = re.split(r'\n=== Pagina \d+ ===\n', text)
        processed_chunks = []
        
        for section in sections:
            if not section.strip():
                continue
                
            section = section.strip()
            section_start = 0
            
            while section_start < len(section) and len(processed_chunks) < max_chunks:
                end = min(section_start + chunk_size, len(section))
                
                # Busca quebra natural
                if end < len(section):
                    for separator in ["\n\n", "\n", ". ", "! ", "? ", ": ", "; ", ", "]:
                        sep_pos = section.rfind(separator, section_start + chunk_size//2, end)
                        if sep_pos > section_start + chunk_size//3:
                            end = sep_pos + len(separator)
                            break
                
                chunk_text = section[section_start:end].strip()
                
                # Filtra chunks validos
                if 100 <= len(chunk_text) <= 2500:
                    # Remove chunks duplicados
                    if not any(chunk_text in existing for existing in processed_chunks[-3:]):
                        processed_chunks.append(chunk_text)
                
                # Calcula proximo inicio com overlap
                section_start = max(end - overlap, section_start + chunk_size//2)
                
                if section_start >= len(section):
                    break
        
        # Fallback se poucos chunks
        if len(processed_chunks) < 5:
            logger.warning("Poucos chunks gerados, usando fallback")
            
            words = text.split()
            current_chunk = []
            
            for word in words[:5000]:
                current_chunk.append(word)
                
                if len(' '.join(current_chunk)) > 900:
                    chunk_text = ' '.join(current_chunk)
                    if len(chunk_text) > 100:
                        processed_chunks.append(chunk_text)
                    current_chunk = current_chunk[-15:]
                    
                if len(processed_chunks) >= 120:
                    break
            
            # Adiciona ultimo chunk
            if current_chunk and len(' '.join(current_chunk)) > 100:
                processed_chunks.append(' '.join(current_chunk))
        
        logger.info(f"Criados {len(processed_chunks)} chunks otimizados")
        
        # Log de estatisticas
        if processed_chunks:
            avg_length = sum(len(chunk) for chunk in processed_chunks) / len(processed_chunks)
            min_length = min(len(chunk) for chunk in processed_chunks)
            max_length = max(len(chunk) for chunk in processed_chunks)
            logger.info(f"Chunks - Media: {avg_length:.0f}, Min: {min_length}, Max: {max_length}")
        
        return processed_chunks
        
    except Exception as e:
        logger.error(f"Erro ao criar chunks: {e}")
        
        # Fallback de emergencia
        words = text.split()[:3000]
        emergency_chunks = []
        current_chunk = []
        
        for word in words:
            current_chunk.append(word)
            if len(' '.join(current_chunk)) > 800:
                chunk_text = ' '.join(current_chunk)
                if len(chunk_text) > 80:
                    emergency_chunks.append(chunk_text)
                current_chunk = current_chunk[-10:]
                
            if len(emergency_chunks) >= 100:
                break
        
        # Ultimo chunk de emergencia
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            if len(chunk_text) > 80:
                emergency_chunks.append(chunk_text)
        
        logger.info(f"Fallback de emergencia: {len(emergency_chunks)} chunks")
        return emergency_chunks

@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    user_email: Optional[str] = Form(default=DEFAULT_USER_EMAIL)
):
    """Upload e processamento de PDF melhorado"""
    # Validacoes
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas arquivos PDF sao aceitos"
        )

    current_user_email = user_email or DEFAULT_USER_EMAIL
    
    file_path = None
    
    try:
        # ID unico
        file_id = f"{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
        
        # Salva arquivo
        file_size = 0
        try:
            with open(file_path, "wb") as buffer:
                while chunk := await file.read(8192):
                    file_size += len(chunk)
                    if file_size > MAX_FILE_SIZE:
                        try:
                            os.remove(file_path)
                        except:
                            pass
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"Arquivo muito grande. Maximo: {MAX_FILE_SIZE//(1024*1024)}MB"
                        )
                    buffer.write(chunk)
                    
            logger.info(f"Arquivo salvo: {file_path} ({file_size:,} bytes) - Usuario: {current_user_email}")
            
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Arquivo nao foi criado: {file_path}")
                
        except Exception as save_error:
            logger.error(f"Erro ao salvar arquivo: {save_error}")
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
        logger.info(f"Iniciando processamento do PDF...")
        text_content = extract_text_from_pdf(file_path)
        
        logger.info(f"Gerando resumo...")
        summary = generate_summary(text_content, file.filename)
        
        logger.info(f"Criando chunks...")
        chunks = create_text_chunks(text_content)
        
        if not chunks:
            raise ValueError("Nenhum chunk criado - arquivo pode estar vazio ou corrompido")
        
        # Salva chunks no chat.py
        try:
            from routes.chat import save_text_chunks
            save_success = save_text_chunks(file_id, chunks, current_user_email)
            if save_success:
                logger.info(f"Chunks salvos no sistema de chat para usuario: {current_user_email}")
            else:
                logger.warning(f"Falha ao salvar chunks no sistema de chat")
        except Exception as e:
            logger.error(f"Erro ao salvar chunks: {e}")
        
        # Remove arquivo fisico apos processamento
        try:
            os.remove(file_path)
            logger.info(f"Arquivo fisico removido: {file_path}")
            file_removed = True
        except Exception as e:
            logger.warning(f"Nao foi possivel remover arquivo: {e}")
            file_removed = False
        
        # Salva dados do arquivo
        if current_user_email not in user_files_data:
            user_files_data[current_user_email] = {}
        
        user_files_data[current_user_email][file_id] = {
            'original_name': file.filename,
            'file_path': file_path if not file_removed else None,
            'summary': summary,
            'upload_date': datetime.now().isoformat(),
            'file_size': file_size,
            'chunks_count': len(chunks),
            'text_length': len(text_content),
            'file_removed': file_removed,
            'processing_stats': {
                'pages_processed': text_content.count('=== Pagina'),
                'avg_chunk_size': sum(len(chunk) for chunk in chunks) // len(chunks) if chunks else 0,
                'min_chunk_size': min(len(chunk) for chunk in chunks) if chunks else 0,
                'max_chunk_size': max(len(chunk) for chunk in chunks) if chunks else 0
            }
        }
        
        save_user_files_data()
        
        logger.info(f"Processamento concluido: {file.filename} para usuario: {current_user_email}")
        
        return {
            "file_id": file_id,
            "original_name": file.filename,
            "summary": summary,
            "size": file_size,
            "chunks_created": len(chunks),
            "upload_date": datetime.now().isoformat(),
            "status": "success",
            "message": f"Arquivo '{file.filename}' processado com sucesso!",
            "file_removed": file_removed,
            "user_email": current_user_email,
            "processing_stats": {
                "pages_processed": text_content.count('=== Pagina'),
                "text_length": len(text_content),
                "avg_chunk_size": sum(len(chunk) for chunk in chunks) // len(chunks) if chunks else 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # Remove arquivo em caso de erro
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
            
        logger.error(f"Erro no processamento: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha no processamento: {str(e)}"
        )

@router.get("/user-files")
async def get_user_files(user_email: Optional[str] = DEFAULT_USER_EMAIL):
    """Lista arquivos do usuario"""
    
    current_user_email = user_email or DEFAULT_USER_EMAIL
    
    if current_user_email not in user_files_data:
        return {"files": [], "user_email": current_user_email}
    
    files = []
    for file_id, file_data in user_files_data[current_user_email].items():
        files.append({
            "file_id": file_id,
            "original_name": file_data["original_name"],
            "summary": file_data["summary"],
            "upload_date": file_data["upload_date"],
            "file_size": file_data["file_size"],
            "chunks_count": file_data.get("chunks_count", 0),
            "file_removed": file_data.get("file_removed", False),
            "processing_stats": file_data.get("processing_stats", {})
        })
    
    return {"files": files, "user_email": current_user_email}

@router.delete("/{file_id}")
async def delete_file(file_id: str, user_email: Optional[str] = DEFAULT_USER_EMAIL):
    """Remove arquivo e seus dados"""
    
    current_user_email = user_email or DEFAULT_USER_EMAIL
    
    if current_user_email not in user_files_data or file_id not in user_files_data[current_user_email]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo nao encontrado para este usuario"
        )
    
    try:
        file_data = user_files_data[current_user_email][file_id]
        
        # Remove arquivo fisico se existir
        if file_data.get("file_path") and os.path.exists(file_data["file_path"]):
            os.remove(file_data["file_path"])
            logger.info(f"Arquivo fisico removido")
        
        # Remove chunks do sistema de chat
        try:
            from routes.chat import text_storage
            storage_key = f"{current_user_email}_{file_id}"
            if storage_key in text_storage:
                del text_storage[storage_key]
                logger.info(f"Chunks removidos do chat")
        except Exception as e:
            logger.warning(f"Erro ao remover chunks do chat: {e}")
        
        # Remove dados do arquivo
        del user_files_data[current_user_email][file_id]
        save_user_files_data()
        
        logger.info(f"Arquivo {file_id} removido completamente para usuario: {current_user_email}")
        
        return {
            "success": True, 
            "message": "Arquivo removido com sucesso",
            "file_id": file_id,
            "user_email": current_user_email
        }
        
    except Exception as e:
        logger.error(f"Erro ao remover arquivo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao remover arquivo"
        )

@router.get("/status")
async def upload_status():
    """Status dos servicos"""
    
    groq_status = groq_client is not None
    
    # Estatisticas dos arquivos
    total_files = 0
    total_chunks = 0
    for user_data in user_files_data.values():
        total_files += len(user_data)
        for file_data in user_data.values():
            total_chunks += file_data.get("chunks_count", 0)
    
    response = {
        "status": "ok" if groq_status else "partial",
        "services": {
            "groq": groq_status,
            "pdf_processing": True,
            "enhanced_text_extraction": True,
            "intelligent_chunking": True,
            "upload_directory": os.path.exists(UPLOAD_DIR),
            "session_isolation": True
        },
        "details": {
            "groq_model": "llama3-8b-8192" if groq_status else "Nao disponivel",
            "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
            "upload_directory": UPLOAD_DIR,
            "total_files_processed": total_files,
            "total_chunks_created": total_chunks,
            "total_users": len(user_files_data),
            "improvements": [
                "limpeza_texto_melhorada",
                "deteccao_tipo_documento", 
                "chunks_otimizados",
                "remocao_automatica_arquivos",
                "tratamento_encoding",
                "fallback_emergencia"
            ]
        }
    }
    
    return response