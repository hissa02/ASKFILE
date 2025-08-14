// === CHATVIEW.JS CORRIGIDO ===

import React, { useRef } from 'react';
import {
  MessageSquare,
  History,
  Upload,
  Send,
  Copy,
  FileText,
  AlertCircle,
  CheckCircle,
  RotateCcw,
  Clock,
  Database
} from 'lucide-react';
import './ChatView.css';

const ChatView = ({
  user,
  setCurrentView,
  chatMessages,
  currentMessage,
  isLoading,
  suggestions,
  quickSuggestions,
  handleLogout,
  handleInputChange,
  handleSendMessage,
  handleKeyDown,
  copyToClipboard,
  handleFileUpload,
  handleChangeFile, // NOVA PROP ADICIONADA
  uploadedFile,
  fileProcessing,
  fetchUserHistory
}) => {
  const fileInputRef = useRef(null);

  // Função para abrir o seletor de arquivos (para primeiro upload)
  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  // Função para processar arquivo selecionado (para primeiro upload)
  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      if (file.type !== 'application/pdf') {
        alert('Apenas arquivos PDF são aceitos!\n\nRequisitos:\n• Formato: PDF\n• Tamanho máximo: 50MB\n• Conteúdo: Texto (não apenas imagens)\n\nPrivacidade: O arquivo será processado e removido do servidor automaticamente.');
        return;
      }
      handleFileUpload(file);
    }
    // Limpa o input para permitir re-upload do mesmo arquivo
    event.target.value = '';
  };

  // CORREÇÃO: Função específica para trocar arquivo
  const handleChangeFileClick = () => {
    if (handleChangeFile) {
      handleChangeFile();
    } else {
      // Fallback se a nova função não estiver disponível
      handleUploadClick();
    }
  };

  // Função para ir ao histórico
  const handleHistoryClick = () => {
    if (fetchUserHistory) {
      fetchUserHistory();
    }
    setCurrentView('history');
  };

  return (
    <div className="chat-container">
      {/* Cabeçalho */}
      <header className="chat-header">
        <div className="header-content">
          <div className="header-left">
            <div className="header-logo">
              <FileText size={24} />
            </div>
            <div className="header-text">
              <h1 className="header-title">AskFile</h1>
              <p className="header-subtitle">Consultas inteligentes em PDF</p>
            </div>
          </div>

          <div className="header-right">
            <button
              onClick={handleHistoryClick}
              className="header-button"
              title="Ver Histórico da Sessão"
            >
              <History size={20} />
            </button>

            <div className="user-info">
              <img 
                src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(user?.name || 'User')}&backgroundColor=0891b2&radius=50`}
                alt="Avatar do usuário" 
                className="user-avatar"
                onError={(e) => {
                  e.target.src = `https://api.dicebear.com/7.x/personas/svg?seed=${encodeURIComponent(user?.name || 'User')}&backgroundColor=0891b2`;
                }}
              />
              <div className="user-details">
                <div className="user-name">
                  {user?.name || 'Usuário AskFile'}
                </div>
                <div className="user-role">
                  {uploadedFile ? (
                    <span style={{color: '#10b981'}}>
                      <Database size={12} style={{display: 'inline', marginRight: '4px'}} />
                      Arquivo indexado
                    </span>
                  ) : 'Nenhum arquivo'}
                </div>
              </div>
              <button
                onClick={handleLogout}
                className="header-button"
                title="Limpar dados da sessão"
              >
                <RotateCcw size={20} />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Área principal */}
      <main className="chat-main">
        <div className="chat-messages">
          {/* Tela inicial com upload */}
          {!uploadedFile && chatMessages.length === 0 && (
            <div className="welcome-upload">
              <div className="upload-area">
                <div className="upload-content">
                  <FileText size={64} className="upload-icon" />
                  <h3>Bem-vindo ao AskFile!</h3>
                  <p>Faça upload de um PDF e comece a fazer perguntas sobre seu conteúdo</p>
                  
                  <button
                    onClick={handleUploadClick}
                    disabled={fileProcessing}
                    className="upload-button"
                  >
                    {fileProcessing ? (
                      <>
                        <div className="spinner"></div>
                        Processando arquivo...
                      </>
                    ) : (
                      <>
                        <Upload className="upload-button-icon" />
                        Fazer upload do PDF
                      </>
                    )}
                  </button>
                  
                  <div className="upload-notice">
                    <AlertCircle size={16} className="notice-icon" />
                    <p>
                      <strong>Privacidade garantida:</strong> Seu arquivo será processado e automaticamente removido do servidor. 
                      Apenas os dados necessários para as consultas são mantidos em formato indexado.
                    </p>
                  </div>
                  
                  <div className="upload-notice" style={{marginTop: '1rem', backgroundColor: '#f0f9ff', borderColor: '#0891b2'}}>
                    <AlertCircle size={16} className="notice-icon" style={{color: '#0891b2'}} />
                    <p style={{color: '#0c4a6e'}}>
                      <strong>Requisitos:</strong> Arquivos PDF com texto (máx. 50MB). PDFs apenas com imagens não são suportados.
                    </p>
                  </div>
                </div>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
            </div>
          )}

          {/* Informações do arquivo carregado */}
          {uploadedFile && chatMessages.length === 0 && (
            <div className="file-info-section">
              <div className="file-info-card">
                <div className="file-info-header">
                  <CheckCircle size={24} className="success-icon" />
                  <div>
                    <h3>Arquivo processado e indexado!</h3>
                    <p>{uploadedFile.name}</p>
                    {uploadedFile.isTemporary && (
                      <p style={{fontSize: '0.75rem', color: '#0891b2', marginTop: '0.25rem'}}>
                        <Clock size={12} style={{display: 'inline', marginRight: '4px'}} />
                        Arquivo físico removido - dados indexados para consultas
                      </p>
                    )}
                  </div>
                </div>
                
                {uploadedFile.summary && (
                  <div className="file-summary">
                    <h4>Resumo do arquivo:</h4>
                    <p>{uploadedFile.summary}</p>
                  </div>
                )}

                <div className="suggestions-section">
                  <h4>Sugestões para começar:</h4>
                  <div className="suggestion-buttons">
                    {quickSuggestions.map((suggestion, index) => (
                      <button
                        key={index}
                        onClick={() => {
                          handleInputChange({ target: { value: suggestion } });
                        }}
                        className="suggestion-button"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                </div>

                {/* CORREÇÃO: Usar a nova função para trocar arquivo */}
                <button
                  onClick={handleChangeFileClick}
                  className="change-file-button"
                  disabled={fileProcessing}
                >
                  <Upload size={16} />
                  Processar outro arquivo
                </button>
              </div>
            </div>
          )}

          {/* Mensagens do chat */}
          {chatMessages.map((message) => (
            <div key={message.id} className={`chat-message ${message.sender}`}>
              <div className="message-content">
                {message.isError && (
                  <div className="error-indicator" title="Ocorreu um erro">
                    <AlertCircle size={16} />
                  </div>
                )}
                <p>{message.text}</p>

                {/* Fontes consultadas para respostas do bot */}
                {message.sender === 'bot' && message.sources && message.sources.length > 0 && (
                  <div className="message-sources">
                    <h4>Trechos consultados no documento:</h4>
                    <ul>
                      {message.sources.map((source, index) => (
                        <li key={index} className="source-item">
                          <FileText size={14} className="source-icon" />
                          <span className="source-content">
                            "{source.content?.substring(0, 150)}..."
                            {source.filename && (
                              <span style={{display: 'block', fontSize: '0.75rem', color: '#6b7280', marginTop: '2px'}}>
                                {source.filename}
                              </span>
                            )}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="message-actions">
                  {message.sender === 'bot' && (
                    <button
                      onClick={() => copyToClipboard(message.text)}
                      className="copy-button"
                      title="Copiar resposta"
                    >
                      <Copy size={16} />
                    </button>
                  )}
                  <span className="message-timestamp">{message.timestamp}</span>
                </div>

                {message.sender === 'bot' && (
                  <div className="message-disclaimer">
                    <span>O AskFile pode cometer erros. Sempre confira as informações importantes.</span>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Indicador de carregamento */}
          {isLoading && (
            <div className="chat-message bot loading-message">
              <div className="message-content">
                <div className="spinner"></div>
                <p>Analisando o documento indexado...</p>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Área de entrada de chat */}
      <div className="chat-input-area">
        {/* Informação do arquivo atual */}
        {uploadedFile && (
          <div className="current-file-indicator">
            <Database size={14} />
            <span>Consultando dados de: {uploadedFile.name}</span>
            <div>
              {/* CORREÇÃO: Usar a nova função para trocar arquivo */}
              <button 
                onClick={handleChangeFileClick}
                className="change-file-btn"
                disabled={fileProcessing}
                title="Trocar arquivo"
              >
                {fileProcessing ? 'Processando...' : 'Trocar'}
              </button>
            </div>
          </div>
        )}

        {/* Sugestões contextuais */}
        {suggestions.length > 0 && (
          <div className="suggestions-container">
            <div className="suggestions-list">
              {suggestions.map((suggestion, index) => (
                <button
                  key={index}
                  onClick={() => {
                    handleInputChange({ target: { value: suggestion } });
                  }}
                  className="suggestion-item"
                >
                  <span className="suggestion-item-text">{suggestion}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Container do input */}
        <div className="input-container">
          <div className="input-wrapper">
            <input
              type="text"
              value={currentMessage}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder={uploadedFile ? "Digite sua pergunta sobre o documento..." : "Primeiro, faça o upload de um arquivo PDF"}
              className="chat-input"
              disabled={isLoading || !uploadedFile}
            />
          </div>

          <button
            onClick={handleSendMessage}
            disabled={isLoading || !currentMessage.trim() || !uploadedFile}
            className="send-button"
          >
            {isLoading ? (
              <div className="spinner-white"></div>
            ) : (
              <Send size={24} />
            )}
          </button>
        </div>

        {/* Dica de uso */}
        <div className="input-tip">
          <span>
            {uploadedFile 
              ? `Dados indexados de: ${uploadedFile.name} | Arquivo físico removido por segurança` 
              : 'Faça upload de um PDF para começar a fazer perguntas'
            }
          </span>
        </div>

        {/* Input oculto para upload (apenas para o primeiro upload) */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={handleFileChange}
          style={{ display: 'none' }}
        />
      </div>
    </div>
  );
};

export default ChatView;