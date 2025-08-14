import React, { useState, useEffect } from 'react';
import { History, Clock, MessageSquare, FileText, Copy, ChevronDown, ChevronUp } from 'lucide-react';
import './HistoryView.css';
 
const HistoryView = ({
  setCurrentView,
  userHistory,
  copyToClipboard,
  fetchUserHistory,
  isLoading
}) => {
  const [expandedItems, setExpandedItems] = useState(new Set());
 
  // Busca o histórico quando o componente é montado
  useEffect(() => {
    if (fetchUserHistory) {
      fetchUserHistory();
    }
  }, [fetchUserHistory]);

  const toggleExpanded = (index) => {
    const newExpanded = new Set(expandedItems);
    if (newExpanded.has(index)) {
      newExpanded.delete(index);
    } else {
      newExpanded.add(index);
    }
    setExpandedItems(newExpanded);
  };
 
  return (
    <div className="history-container">
      {/* Cabeçalho */}
      <header className="history-header">
        <div className="history-header-content">
          <div className="history-header-left">
            <button
              onClick={() => setCurrentView('chat')}
              className="back-button"
            >
              ← Voltar ao AskFile
            </button>
            <h1 className="history-title">
              <History className="history-icon" />
              Histórico de Consultas
            </h1>
          </div>
        </div>
      </header>
 
      {/* Conteúdo */}
      <div className="history-content">
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '2rem' }}>
            <div className="spinner-dark"></div>
            <p>Carregando histórico...</p>
          </div>
        ) : !userHistory || userHistory.length === 0 ? (
          <div className="empty-history">
            <FileText className="empty-history-icon" />
            <h3 className="empty-history-title">Nenhuma consulta realizada</h3>
            <p className="empty-history-text">
              Suas perguntas e respostas sobre arquivos PDF aparecerão aqui para fácil acesso e referência.
            </p>
            <button
              onClick={() => setCurrentView('chat')}
              className="start-chat-button"
            >
              Começar primeira consulta
            </button>
          </div>
        ) : (
          <div className="history-list">
            {userHistory.map((item, index) => (
              <div key={index} className="history-item">
                {/* Cabeçalho do item */}
                <div
                  className="history-item-header"
                  onClick={() => toggleExpanded(index)}
                >
                  <div className="history-item-content">
                    <div className="history-item-meta">
                      <div className="history-item-icon user-icon">
                        <MessageSquare size={16} />
                      </div>
                      <div className="question-content">
                        <h3 className="history-item-label">Pergunta:</h3>
                        <p className="history-item-question">{item.question || 'Pergunta não disponível'}</p>
                      </div>
                    </div>
                    <div className="history-item-time">
                      <Clock size={12} className="time-icon" />
                      {item.timestamp ? new Date(item.timestamp).toLocaleString('pt-BR') : 'Data não disponível'}
                    </div>
                  </div>
                  <div className="expand-icon">
                    {expandedItems.has(index) ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                  </div>
                </div>
                
                {/* Conteúdo expandido */}
                {expandedItems.has(index) && (
                  <div className="history-item-expanded">
                    <div className="history-answer">
                      <div className="history-answer-header">
                        <div className="history-answer-icon">
                          <FileText size={16} />
                        </div>
                        <h3 className="history-answer-label">Resposta do AskFile:</h3>
                      </div>
                      
                      <div className="history-answer-text">
                        {item.answer || 'Resposta não disponível'}
                      </div>
                      
                      {/* Fontes */}
                      {item.sources && item.sources.length > 0 && (
                        <div className="history-sources">
                          <h4>Fontes consultadas no arquivo:</h4>
                          <ul>
                            {item.sources.map((source, sourceIndex) => (
                              <li key={sourceIndex} className="source-item">
                                <FileText size={12} className="source-icon" />
                                <span className="source-content">
                                  "{source.content?.substring(0, 120)}..."
                                </span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      
                      <div className="history-answer-footer">
                        <div className="answer-info">
                          <span className="answer-time">
                            Respondido em {item.timestamp ? new Date(item.timestamp).toLocaleString('pt-BR') : 'Data não disponível'}
                          </span>
                        </div>
                        
                        <button
                          onClick={() => copyToClipboard(item.answer || '')}
                          className="copy-button"
                        >
                          <Copy className="copy-icon" />
                          Copiar resposta
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
 
export default HistoryView;