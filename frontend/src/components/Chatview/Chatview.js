import React, { useRef } from 'react';
import {
  MessageSquare,
  History,
  LogOut,
  Upload,
  Send,
  Copy,
  FileText,
  AlertCircle,
  CheckCircle
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
  uploadedFile,
  fileProcessing
}) => {
  const fileInputRef = useRef(null);

  // Função para abrir o seletor de arquivos
  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  // Função para processar arquivo selecionado
  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      if (file.type !== 'application/pdf') {
        alert('⚠️ Apenas arquivos PDF são aceitos!\n\nObservação: PDFs com imagens não são processados. Apenas texto é analisado.');
        return;
      }
      handleFileUpload(file);
    }
    // Limpa o input para permitir re-upload do mesmo arquivo
    event.target.value = '';
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
              <p className="header-subtitle">Faça perguntas ao seu PDF</p>
            </div>
          </div>

          <div className="header-right">
            <button
              onClick={() => setCurrentView('history')}
              className="header-button"
              title="Ver Histórico"
            >
              <History size={20} />
            </button>

            <div className="user-info">
              <img 
                src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(user?.name || user?.email || 'User')}&backgroundColor=0891b2&radius=50`}
                alt="Avatar do usuário" 
                className="user-avatar"
                onError={(e) => {
                  e.target.src = `https://api.dicebear.com/7.x/personas/svg?seed=${encodeURIComponent(user?.name || user?.email || 'User')}&backgroundColor=0891b2`;
                }}
              />
              <div className="user-details">
                <div className="user-name">
                  {user?.name || user?.username || user?.email?.split('@')[0] || 'Usuário'}
                </div>
                <div className="user-role">
                  {uploadedFile ? 'Arquivo carregado' : 'Nenhum arquivo'}
                </div>
              </div>
              <button
                onClick={handleLogout}
                className="header-button"
                title="Sair"
              >
                <LogOut size={20} />
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
                        Faça o upload do seu arquivo
                      </>
                    )}
                  </button>
                  
                  <div className="upload-notice">
                    <AlertCircle size={16} className="notice-icon" />
                    <p>Apenas arquivos PDF são aceitos. PDFs com imagens não são processados - apenas texto é analisado.</p>
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
                    <h3>Arquivo processado com sucesso!</h3>
                    <p>{uploadedFile.name}</p>
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

                <button
                  onClick={handleUploadClick}
                  className="change-file-button"
                  disabled={fileProcessing}
                >
                  <Upload size={16} />
                  Trocar arquivo
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
                    <h4>Fontes no documento:</h4>
                    <ul>
                      {message.sources.map((source, index) => (
                        <li key={index} className="source-item">
                          <FileText size={14} className="source-icon" />
                          <span className="source-content">
                            "{source.content?.substring(0, 150)}..."
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
                      title="Copiar texto"
                    >
                      <Copy size={16} />
                    </button>
                  )}
                  <span className="message-timestamp">{message.timestamp}</span>
                </div>

                {message.sender === 'bot' && (
                  <div className="message-disclaimer">
                    <span>O AskFile pode cometer erros. Confira sempre as respostas.</span>
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
                <p>Analisando seu arquivo...</p>
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
            <FileText size={14} />
            <span>Consultando: {uploadedFile.name}</span>
            <button 
              onClick={handleUploadClick}
              className="change-file-btn"
              disabled={fileProcessing}
              title="Trocar arquivo"
            >
              {fileProcessing ? 'Processando...' : 'Trocar'}
            </button>
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
              placeholder={uploadedFile ? "Digite sua pergunta sobre o arquivo..." : "Primeiro, faça o upload de um arquivo PDF"}
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
              ? `Faça perguntas sobre: ${uploadedFile.name}` 
              : 'Faça upload de um PDF para começar'
            }
          </span>
        </div>

        {/* Input oculto para upload */}
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