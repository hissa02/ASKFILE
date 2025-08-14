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
    logger.info(f" Diretório de upload: {os.path.abspath(UPLOAD_DIR)}")
except Exception as e:
    logger.error(f" Erro ao criar diretório: {e}")

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
    """Extrai texto do PDF com melhor tratamento"""
    try:
        reader = PdfReader(file_path)
        text_parts = []
        max_pages = 50  # Aumenta limite de páginas
        
        total_pages = min(len(reader.pages), max_pages)
        
        for page_num in range(total_pages):
            try:
                page = reader.pages[page_num]
                page_text = page.extract_text()
                
                if page_text and page_text.strip():
                    # Limpa o texto
                    page_text = page_text.strip()
                    
                    # Remove quebras de linha excessivas
                    page_text = re.sub(r'\n\s*\n', '\n\n', page_text)
                    
                    # Remove espaços múltiplos
                    page_text = re.sub(r' +', ' ', page_text)
                    
                    # Limita tamanho por página
                    if len(page_text) > 6000:  # Aumenta limite por página
                        page_text = page_text[:6000] + "..."
                    
                    text_parts.append(f"\n=== Página {page_num + 1} ===\n{page_text}")
                    
            except Exception as e:
                logger.warning(f"Erro na página {page_num + 1}: {e}")
                continue
        
        if not text_parts:
            raise ValueError("Nenhum texto extraído do PDF")
        
        full_text = '\n\n'.join(text_parts)
        max_total = 200000  # Aumenta limite total para 200KB
        
        if len(full_text) > max_total:
            logger.warning(f"Texto truncado de {len(full_text)} para {max_total} chars")
            full_text = full_text[:max_total] + "\n\n[Documento truncado]"
        
        logger.info(f" Texto extraído: {len(full_text):,} caracteres de {total_pages} páginas")
        return full_text
        
    except Exception as e:
        logger.error(f" Erro ao extrair texto: {e}")
        raise HTTPException(status_code=400, detail=f"Erro ao processar PDF: {str(e)}")

def generate_summary(text: str, filename: str) -> str:
    """Gera resumo usando Groq"""
    try:
        if not groq_client:
            return f" {filename}\n\nArquivo processado com {len(text)} caracteres. Faça perguntas sobre o conteúdo."
        
        # Usa uma amostra maior do texto para o resumo
        text_sample = text[:8000] if len(text) > 8000 else text
        
        prompt = f"""Analise este documento PDF e crie um resumo detalhado em português:

ARQUIVO: {filename}

CONTEÚDO:
{text_sample}

Crie um resumo de 3-4 parágrafos incluindo:
1. Tipo de documento e seu objetivo principal
2. Principais tópicos e seções abordados
3. Dados importantes, números ou fatos relevantes
4. Conclusões ou pontos principais destacados

Seja específico e mencione informações que podem ser úteis para consultas futuras.
Use linguagem clara e objetiva."""

        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,  # Aumenta limite para resumo mais detalhado
            temperature=0.3
        )
        
        summary = response.choices[0].message.content
        
        if not summary or len(summary.strip()) < 50:
            return f" {filename}\n\nArquivo processado com {len(text)} caracteres. Faça perguntas sobre o conteúdo."
        
        logger.info(f" Resumo gerado: {len(summary)} caracteres")
        return summary
        
    except Exception as e:
        logger.error(f"❌ Erro ao gerar resumo: {e}")
        return f" {filename}\n\nArquivo processado. Faça perguntas sobre o conteúdo."

def create_text_chunks(text: str, chunk_size: int = 1000, overlap: int = 150) -> list:
    """Cria chunks de texto mais inteligentes e otimizados"""
    try:
        chunks = []
        text_length = len(text)
        start = 0
        max_chunks = 150  # Aumenta limite de chunks
        
        # Pre-processamento: identifica seções e parágrafos
        sections = re.split(r'\n=== Página \d+ ===\n', text)
        processed_chunks = []
        
        for section in sections:
            if not section.strip():
                continue
                
            section = section.strip()
            section_start = 0
            
            while section_start < len(section) and len(processed_chunks) < max_chunks:
                end = min(section_start + chunk_size, len(section))
                
                # Busca quebra natural para evitar cortar palavras/frases
                if end < len(section):
                    # Prioridade de quebras: parágrafo > frase > palavra
                    for separator in ["\n\n", "\n", ". ", "! ", "? ", ": ", "; ", ", "]:
                        sep_pos = section.rfind(separator, section_start + chunk_size//2, end)
                        if sep_pos > section_start + chunk_size//3:  # Garante chunk mínimo
                            end = sep_pos + len(separator)
                            break
                
                chunk_text = section[section_start:end].strip()
                
                # Filtra chunks válidos (nem muito pequenos nem muito grandes)
                if 100 <= len(chunk_text) <= 2500:
                    # Remove chunks duplicados
                    if not any(chunk_text in existing for existing in processed_chunks[-3:]):
                        processed_chunks.append(chunk_text)
                
                # Calcula próximo início com overlap
                section_start = max(end - overlap, section_start + chunk_size//2)
                
                if section_start >= len(section):
                    break
        
        # Se não conseguiu chunks bons, faz fallback simples
        if len(processed_chunks) < 5:
            logger.warning("Poucos chunks gerados, usando fallback simples")
            
            words = text.split()
            current_chunk = []
            
            for word in words[:5000]:  # Processa mais palavras
                current_chunk.append(word)
                
                if len(' '.join(current_chunk)) > 900:
                    chunk_text = ' '.join(current_chunk)
                    if len(chunk_text) > 100:
                        processed_chunks.append(chunk_text)
                    # Mantém overlap de palavras
                    current_chunk = current_chunk[-15:]
                    
                if len(processed_chunks) >= 120:
                    break
            
            # Adiciona último chunk se significativo
            if current_chunk and len(' '.join(current_chunk)) > 100:
                processed_chunks.append(' '.join(current_chunk))
        
        logger.info(f" Criados {len(processed_chunks)} chunks otimizados")
        
        # Log de estatísticas para debug
        if processed_chunks:
            avg_length = sum(len(chunk) for chunk in processed_chunks) / len(processed_chunks)
            min_length = min(len(chunk) for chunk in processed_chunks)
            max_length = max(len(chunk) for chunk in processed_chunks)
            logger.info(f"Chunks - Média: {avg_length:.0f}, Min: {min_length}, Max: {max_length}")
        
        return processed_chunks
        
    except Exception as e:
        logger.error(f" Erro ao criar chunks: {e}")
        
        # Fallback de emergência
        words = text.split()[:3000]  # Limita palavras de emergência
        emergency_chunks = []
        current_chunk = []
        
        for word in words:
            current_chunk.append(word)
            if len(' '.join(current_chunk)) > 800:
                chunk_text = ' '.join(current_chunk)
                if len(chunk_text) > 80:
                    emergency_chunks.append(chunk_text)
                current_chunk = current_chunk[-10:]  # Mantém overlap
                
            if len(emergency_chunks) >= 100:
                break
        
        # Último chunk de emergência
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            if len(chunk_text) > 80:
                emergency_chunks.append(chunk_text)
        
        logger.info(f" Fallback de emergência: {len(emergency_chunks)} chunks")
        return emergency_chunks

@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    user_email: Optional[str] = Form(default=DEFAULT_USER_EMAIL)  # MODIFICADO: Aceita user_email
):
    """
    Upload e processamento de PDF com sistema de sessões
    """
    # Validações
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas arquivos PDF são aceitos"
        )

    # MODIFICADO: Usa user_email fornecido ou padrão
    current_user_email = user_email or DEFAULT_USER_EMAIL
    
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
                    
            logger.info(f" Arquivo salvo: {file_path} ({file_size:,} bytes) - Usuário: {current_user_email}")
            
            # Verifica se o arquivo foi realmente criado
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Arquivo não foi criado: {file_path}")
                
        except Exception as save_error:
            logger.error(f" Erro ao salvar arquivo: {save_error}")
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
        
        # Processa PDF com melhorias
        logger.info(f" Iniciando processamento do PDF...")
        text_content = extract_text_from_pdf(file_path)
        
        logger.info(f" Gerando resumo...")
        summary = generate_summary(text_content, file.filename)
        
        logger.info(f" Criando chunks...")
        chunks = create_text_chunks(text_content)
        
        if not chunks:
            raise ValueError("Nenhum chunk criado - arquivo pode estar vazio ou corrompido")
        
        # Salva chunks no chat.py
        try:
            from routes.chat import save_text_chunks
            save_success = save_text_chunks(file_id, chunks, current_user_email)  # MODIFICADO: Passa user_email
            if save_success:
                logger.info(f" Chunks salvos no sistema de chat para usuário: {current_user_email}")
            else:
                logger.warning(f" Falha ao salvar chunks no sistema de chat")
        except Exception as e:
            logger.error(f" Erro ao salvar chunks: {e}")
            # Não falha o upload por causa disso, mas registra o erro
        
        # Remove arquivo físico após processamento (economia de espaço)
        try:
            os.remove(file_path)
            logger.info(f" Arquivo físico removido: {file_path}")
            file_removed = True
        except Exception as e:
            logger.warning(f" Não foi possível remover arquivo: {e}")
            file_removed = False
        
        # MODIFICADO: Salva dados do arquivo usando user_email como chave
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
                'pages_processed': text_content.count('=== Página'),
                'avg_chunk_size': sum(len(chunk) for chunk in chunks) // len(chunks) if chunks else 0,
                'min_chunk_size': min(len(chunk) for chunk in chunks) if chunks else 0,
                'max_chunk_size': max(len(chunk) for chunk in chunks) if chunks else 0
            }
        }
        
        save_user_files_data()
        
        logger.info(f" Processamento concluído: {file.filename} para usuário: {current_user_email}")
        
        return {
            "file_id": file_id,
            "original_name": file.filename,
            "summary": summary,
            "size": file_size,
            "chunks_created": len(chunks),
            "upload_date": datetime.now().isoformat(),
            "status": "success",
            "message": f"✅ Arquivo '{file.filename}' processado com sucesso!",
            "file_removed": file_removed,
            "user_email": current_user_email,  # NOVO: Retorna o user_email usado
            "processing_stats": {
                "pages_processed": text_content.count('=== Página'),
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
            
        logger.error(f" Erro no processamento: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha no processamento: {str(e)}"
        )

@router.get("/user-files")
async def get_user_files(user_email: Optional[str] = DEFAULT_USER_EMAIL):
    """Lista arquivos do usuário específico"""
    
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
    """Remove arquivo e seus dados do usuário específico"""
    
    current_user_email = user_email or DEFAULT_USER_EMAIL
    
    if current_user_email not in user_files_data or file_id not in user_files_data[current_user_email]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo não encontrado para este usuário"
        )
    
    try:
        file_data = user_files_data[current_user_email][file_id]
        
        # Remove arquivo físico se ainda existir
        if file_data.get("file_path") and os.path.exists(file_data["file_path"]):
            os.remove(file_data["file_path"])
            logger.info(f" Arquivo físico removido")
        
        # Remove chunks do sistema de chat
        try:
            from routes.chat import text_storage
            storage_key = f"{current_user_email}_{file_id}"
            if storage_key in text_storage:
                del text_storage[storage_key]
                logger.info(f" Chunks removidos do chat")
        except Exception as e:
            logger.warning(f" Erro ao remover chunks do chat: {e}")
        
        # Remove dados do arquivo
        del user_files_data[current_user_email][file_id]
        save_user_files_data()
        
        logger.info(f" Arquivo {file_id} removido completamente para usuário: {current_user_email}")
        
        return {
            "success": True, 
            "message": "Arquivo removido com sucesso",
            "file_id": file_id,
            "user_email": current_user_email
        }
        
    except Exception as e:
        logger.error(f" Erro ao remover arquivo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao remover arquivo"
        )

@router.get("/status")
async def upload_status():
    """Status dos serviços com informações detalhadas"""
    
    groq_status = groq_client is not None
    
    # Estatísticas dos arquivos
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
            "text_chunking": True,
            "upload_directory": os.path.exists(UPLOAD_DIR),
            "session_isolation": True  # NOVO: Indica suporte a sessões
        },
        "details": {
            "groq_model": "llama3-8b-8192" if groq_status else "Não disponível",
            "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
            "upload_directory": UPLOAD_DIR,
            "total_files_processed": total_files,
            "total_chunks_created": total_chunks,
            "total_users": len(user_files_data),  # NOVO: Total de usuários únicos
            "improvements": [
                "chunks_otimizados",
                "processamento_melhorado", 
                "remocao_automatica_arquivos",
                "estatisticas_detalhadas",
                "tratamento_robusto_erros",
                "isolamento_por_sessao"  # NOVO
            ]
        }
    }
    
    return response