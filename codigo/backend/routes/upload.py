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
    logger.info(f"Diretório de upload: {os.path.abspath(UPLOAD_DIR)}")
except Exception as e:
    logger.error(f"Erro ao criar diretório: {e}")

MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB

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
    """Extrai texto do PDF preservando estrutura para análise"""
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
                    # Preserva estrutura original mais cuidadosamente
                    page_text = page_text.strip()
                    
                    # Normaliza quebras mas preserva informações importantes
                    page_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', page_text)
                    page_text = re.sub(r'[ \t]+', ' ', page_text)
                    
                    # Marca campos importantes para evitar confusão
                    page_text = re.sub(r'Nome:\s*([A-ZÁÇÕ\s]+)', r'NOME_PRINCIPAL: \1', page_text)
                    page_text = re.sub(r'Nome do Pai:\s*([A-Za-záçõ\s]+)', r'NOME_DO_PAI: \1', page_text)
                    page_text = re.sub(r'Nome da Mãe:\s*([A-Za-záçõ\s]+)', r'NOME_DA_MAE: \1', page_text)
                    page_text = re.sub(r'Matrícula:\s*(\d+)', r'MATRICULA_NUMERO: \1', page_text)
                    page_text = re.sub(r'Data de Nascimento:\s*([0-9/]+)', r'DATA_NASCIMENTO: \1', page_text)
                    page_text = re.sub(r'Curso:\s*([A-ZÁÇÕ\s\-]+)', r'CURSO_NOME: \1', page_text)
                    
                    if len(page_text) > 8000:
                        page_text = page_text[:8000] + "..."
                    
                    text_parts.append(f"\n=== PAGINA {page_num + 1} ===\n{page_text}")
                    
            except Exception as e:
                logger.warning(f"Erro na página {page_num + 1}: {e}")
                continue
        
        if not text_parts:
            raise ValueError("Nenhum texto extraído do PDF")
        
        full_text = '\n\n'.join(text_parts)
        max_total = 250000
        
        if len(full_text) > max_total:
            logger.warning(f"Texto truncado de {len(full_text)} para {max_total} chars")
            full_text = full_text[:max_total] + "\n\n[Documento truncado]"
        
        logger.info(f"Texto estruturado extraído: {len(full_text):,} caracteres de {total_pages} páginas")
        return full_text
        
    except Exception as e:
        logger.error(f"Erro ao extrair texto: {e}")
        raise HTTPException(status_code=400, detail=f"Erro ao processar PDF: {str(e)}")

def generate_summary(text: str, filename: str) -> str:
    """Gera resumo usando Groq"""
    try:
        if not groq_client:
            return f"{filename}\n\nArquivo processado com {len(text)} caracteres. Faça perguntas sobre o conteúdo."
        
        text_sample = text[:10000] if len(text) > 10000 else text
        
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
            max_tokens=700,
            temperature=0.3
        )
        
        summary = response.choices[0].message.content
        
        if not summary or len(summary.strip()) < 50:
            return f"{filename}\n\nArquivo processado com {len(text)} caracteres. Faça perguntas sobre o conteúdo."
        
        logger.info(f"Resumo gerado: {len(summary)} caracteres")
        return summary
        
    except Exception as e:
        logger.error(f"Erro ao gerar resumo: {e}")
        return f"{filename}\n\nArquivo processado. Faça perguntas sobre o conteúdo."

def create_text_chunks_with_context(text: str, chunk_size: int = 1000, overlap: int = 150) -> list:
    """
    Cria chunks preservando contexto estrutural das informações
    """
    try:
        chunks = []
        max_chunks = 200
        
        # Divide por páginas para manter contexto
        pages = re.split(r'\n=== PAGINA \d+ ===\n', text)
        processed_chunks = []
        
        for page_idx, page_content in enumerate(pages):
            if not page_content.strip():
                continue
                
            page_content = page_content.strip()
            
            # Identifica blocos de informações relacionadas
            structural_blocks = []
            
            # Bloco de dados pessoais/identificação
            personal_data_match = re.search(
                r'(NOME_PRINCIPAL:.*?(?=CURSO_NOME:|Componentes|$))', 
                page_content, 
                re.DOTALL | re.IGNORECASE
            )
            if personal_data_match:
                personal_block = personal_data_match.group(1)
                structural_blocks.append(("IDENTIFICACAO", personal_block))
            
            # Outros blocos estruturais genéricos (tabelas, listas, etc)
            # Detecta blocos com estrutura similar (linhas com padrões)
            table_blocks = re.findall(
                r'(\d{4}[^\n]*\n(?:[^\n]*\n){0,3})',
                page_content
            )
            for i, table in enumerate(table_blocks):
                if len(table.strip()) > 30:
                    structural_blocks.append((f"TABELA_{i}", table.strip()))
            
            # Processa blocos estruturais
            for block_type, block_content in structural_blocks:
                if len(block_content) > 50:
                    # Adiciona contexto ao chunk
                    contextualized_chunk = f"[SECAO: {block_type}]\n{block_content}"
                    
                    # Se muito grande, divide mantendo contexto
                    if len(contextualized_chunk) > chunk_size:
                        lines = contextualized_chunk.split('\n')
                        current_chunk = [f"[SECAO: {block_type}]"]
                        current_length = len(current_chunk[0])
                        
                        for line in lines[1:]:
                            if current_length + len(line) > chunk_size - 100:
                                if len(current_chunk) > 1:
                                    processed_chunks.append('\n'.join(current_chunk))
                                current_chunk = [f"[SECAO: {block_type}_CONT]", line]
                                current_length = len(current_chunk[0]) + len(line)
                            else:
                                current_chunk.append(line)
                                current_length += len(line)
                        
                        if len(current_chunk) > 1:
                            processed_chunks.append('\n'.join(current_chunk))
                    else:
                        processed_chunks.append(contextualized_chunk)
            
            # Processa texto restante
            remaining_text = page_content
            for _, block_content in structural_blocks:
                remaining_text = remaining_text.replace(block_content, '')
            
            remaining_text = re.sub(r'\n\s*\n', '\n', remaining_text.strip())
            
            if len(remaining_text) > 100:
                remaining_start = 0
                while remaining_start < len(remaining_text) and len(processed_chunks) < max_chunks:
                    end = min(remaining_start + chunk_size, len(remaining_text))
                    
                    # Busca quebra natural
                    if end < len(remaining_text):
                        for separator in ['\n\n', '\n', '. ', '! ', '? ']:
                            sep_pos = remaining_text.rfind(separator, remaining_start + chunk_size//2, end)
                            if sep_pos > remaining_start + 100:
                                end = sep_pos + len(separator)
                                break
                    
                    chunk_text = remaining_text[remaining_start:end].strip()
                    
                    if len(chunk_text) > 80:
                        contextualized_chunk = f"[SECAO: PAGINA_{page_idx + 1}]\n{chunk_text}"
                        processed_chunks.append(contextualized_chunk)
                    
                    remaining_start = max(end - overlap, remaining_start + chunk_size//2)
        
        # Fallback se poucos chunks
        if len(processed_chunks) < 5:
            logger.warning("Poucos chunks estruturais, usando fallback")
            
            sentences = re.split(r'[.!?]+\s+', text)
            current_chunk = []
            current_length = 0
            
            for sentence in sentences[:5000]:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                if current_length + len(sentence) > 900 and current_chunk:
                    chunk_text = '. '.join(current_chunk) + '.'
                    if len(chunk_text) > 100:
                        contextualized = f"[SECAO: CONTEUDO_GERAL]\n{chunk_text}"
                        processed_chunks.append(contextualized)
                    
                    current_chunk = current_chunk[-2:] if len(current_chunk) > 2 else []
                    current_length = sum(len(s) for s in current_chunk)
                
                current_chunk.append(sentence)
                current_length += len(sentence)
                
                if len(processed_chunks) >= 150:
                    break
            
            if current_chunk:
                chunk_text = '. '.join(current_chunk) + '.'
                if len(chunk_text) > 100:
                    contextualized = f"[SECAO: CONTEUDO_FINAL]\n{chunk_text}"
                    processed_chunks.append(contextualized)
        
        # Verificação final
        final_chunks = []
        for chunk in processed_chunks:
            if len(chunk) >= 100:
                chunk = re.sub(r' +', ' ', chunk)
                chunk = re.sub(r'\n ', '\n', chunk)
                final_chunks.append(chunk.strip())
        
        logger.info(f"Criados {len(final_chunks)} chunks com contexto")
        
        if final_chunks:
            chunks_with_context = sum(1 for chunk in final_chunks if '[SECAO:' in chunk)
            chunks_with_names = sum(1 for chunk in final_chunks if 'NOME_PRINCIPAL' in chunk)
            
            logger.info(f"Qualidade contextual - Com contexto: {chunks_with_context}, Com nomes: {chunks_with_names}")
        
        return final_chunks
        
    except Exception as e:
        logger.error(f"Erro ao criar chunks contextuais: {e}")
        
        # Fallback de emergência
        words = text.split()[:3000]
        emergency_chunks = []
        current_chunk = []
        
        for word in words:
            current_chunk.append(word)
            if len(' '.join(current_chunk)) > 800:
                chunk_text = ' '.join(current_chunk)
                if len(chunk_text) > 100:
                    contextualized = f"[SECAO: EMERGENCIA]\n{chunk_text}"
                    emergency_chunks.append(contextualized)
                current_chunk = current_chunk[-10:]
                
            if len(emergency_chunks) >= 100:
                break
        
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            if len(chunk_text) > 100:
                contextualized = f"[SECAO: EMERGENCIA_FINAL]\n{chunk_text}"
                emergency_chunks.append(contextualized)
        
        logger.info(f"Fallback de emergência contextual: {len(emergency_chunks)} chunks")
        return emergency_chunks

@router.post("/", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    user_email: Optional[str] = Form(default=DEFAULT_USER_EMAIL)
):
    """
    Upload e processamento de PDF com chunks contextuais
    """
    # Validações
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas arquivos PDF são aceitos"
        )

    current_user_email = user_email or DEFAULT_USER_EMAIL
    
    file_path = None
    
    try:
        # ID único
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
                            detail=f"Arquivo muito grande. Máximo: {MAX_FILE_SIZE//(1024*1024)}MB"
                        )
                    buffer.write(chunk)
                    
            logger.info(f"Arquivo salvo: {file_path} ({file_size:,} bytes) - Usuário: {current_user_email}")
            
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Arquivo não foi criado: {file_path}")
                
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
        
        # Processa PDF com contexto estrutural
        logger.info(f"Iniciando processamento contextual do PDF...")
        text_content = extract_text_from_pdf(file_path)
        
        logger.info(f"Gerando resumo...")
        summary = generate_summary(text_content, file.filename)
        
        logger.info(f"Criando chunks contextuais...")
        chunks = create_text_chunks_with_context(text_content)
        
        if not chunks:
            raise ValueError("Nenhum chunk criado - arquivo pode estar vazio ou corrompido")
        
        # Salva chunks no chat.py
        try:
            from routes.chat import save_text_chunks
            save_success = save_text_chunks(file_id, chunks, current_user_email)
            if save_success:
                logger.info(f"Chunks contextuais salvos no sistema de chat para usuário: {current_user_email}")
            else:
                logger.warning(f"Falha ao salvar chunks no sistema de chat")
        except Exception as e:
            logger.error(f"Erro ao salvar chunks: {e}")
        
        # Remove arquivo físico após processamento
        try:
            os.remove(file_path)
            logger.info(f"Arquivo físico removido: {file_path}")
            file_removed = True
        except Exception as e:
            logger.warning(f"Não foi possível remover arquivo: {e}")
            file_removed = False
        
        # Salva dados do arquivo usando user_email como chave
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
                'pages_processed': text_content.count('=== PAGINA'),
                'avg_chunk_size': sum(len(chunk) for chunk in chunks) // len(chunks) if chunks else 0,
                'min_chunk_size': min(len(chunk) for chunk in chunks) if chunks else 0,
                'max_chunk_size': max(len(chunk) for chunk in chunks) if chunks else 0,
                'chunks_with_numbers': sum(1 for chunk in chunks if re.search(r'\d+', chunk)),
                'processing_contextual': True
            }
        }
        
        save_user_files_data()
        
        logger.info(f"Processamento contextual concluído: {file.filename} para usuário: {current_user_email}")
        
        return {
            "file_id": file_id,
            "original_name": file.filename,
            "summary": summary,
            "size": file_size,
            "chunks_created": len(chunks),
            "upload_date": datetime.now().isoformat(),
            "status": "success",
            "message": f"Arquivo '{file.filename}' processado com contexto estrutural!",
            "file_removed": file_removed,
            "user_email": current_user_email,
            "processing_stats": {
                "pages_processed": text_content.count('=== PAGINA'),
                "text_length": len(text_content),
                "avg_chunk_size": sum(len(chunk) for chunk in chunks) // len(chunks) if chunks else 0,
                "chunks_with_numbers": sum(1 for chunk in chunks if re.search(r'\d+', chunk)),
                "processing_contextual": True,
                "quality_indicators": {
                    "chunks_with_content": len([c for c in chunks if len(c) > 200]),
                    "chunks_with_structure": len([c for c in chunks if ':' in c or '(' in c]),
                    "text_coverage": round((len(''.join(chunks)) / len(text_content)) * 100, 1)
                }
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
            
        logger.error(f"Erro no processamento contextual: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha no processamento contextual: {str(e)}"
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
            "processing_stats": file_data.get("processing_stats", {}),
            "processing_contextual": file_data.get("processing_stats", {}).get("processing_contextual", False)
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
            logger.info(f"Arquivo físico removido")
        
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
        
        logger.info(f"Arquivo {file_id} removido completamente para usuário: {current_user_email}")
        
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
    """Status dos serviços com informações detalhadas"""
    
    groq_status = groq_client is not None
    
    # Estatísticas dos arquivos
    total_files = 0
    total_chunks = 0
    contextual_files = 0
    for user_data in user_files_data.values():
        total_files += len(user_data)
        for file_data in user_data.values():
            total_chunks += file_data.get("chunks_count", 0)
            if file_data.get("processing_stats", {}).get("processing_contextual", False):
                contextual_files += 1
    
    response = {
        "status": "ok" if groq_status else "partial",
        "services": {
            "groq": groq_status,
            "pdf_processing": True,
            "text_chunking": True,
            "upload_directory": os.path.exists(UPLOAD_DIR),
            "session_isolation": True,
            "contextual_processing": True
        },
        "details": {
            "groq_model": "llama3-8b-8192" if groq_status else "Não disponível",
            "max_file_size_mb": MAX_FILE_SIZE // (1024 * 1024),
            "upload_directory": UPLOAD_DIR,
            "total_files_processed": total_files,
            "total_chunks_created": total_chunks,
            "total_users": len(user_files_data),
            "contextual_files": contextual_files,
            "contextualization_rate": round((contextual_files / max(total_files, 1)) * 100, 1),
            "improvements": [
                "chunks_contextuais_inteligentes",
                "processamento_estrutural_preservado", 
                "identificacao_automatica_campos",
                "remocao_automatica_arquivos",
                "estatisticas_detalhadas",
                "tratamento_robusto_erros",
                "isolamento_por_sessao",
                "quebras_naturais_texto",
                "overlap_inteligente",
                "qualidade_conteudo_melhorada"
            ]
        }
    }
    
    return response