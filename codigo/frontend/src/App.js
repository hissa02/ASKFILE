import React, { useState, useCallback, useMemo } from 'react';
import ChatView from './components/ChatView/ChatView';
import HistoryView from './components/HistoryView/HistoryView';
import './App.css';

const AskFileSystem = () => {
  // === FUNÇÃO PARA GERAR ID ÚNICO ===
  const generateSessionId = useCallback(() => {
    return 'user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  }, []);

  // === ESTADOS PRINCIPAIS ===
  const [currentView, setCurrentView] = useState('chat');
  const [chatMessages, setChatMessages] = useState([]);
  const [currentMessage, setCurrentMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [userHistory, setUserHistory] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [fileProcessing, setFileProcessing] = useState(false);
  
  // === NOVO: ID ÚNICO POR USUÁRIO/SESSÃO ===
  const [userSessionId] = useState(() => {
    // Verifica se já existe um ID salvo no localStorage
    let sessionId = localStorage.getItem('askfile_session_id');
    if (!sessionId) {
      sessionId = generateSessionId();
      localStorage.setItem('askfile_session_id', sessionId);
    }
    return sessionId;
  });

  // === CONFIGURAÇÕES ===
  const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://askfile.onrender.com';

  // === USUÁRIO FICTÍCIO COM ID ÚNICO ===
  const defaultUser = useMemo(() => ({
    id: userSessionId,
    name: "Usuário AskFile",
    email: `${userSessionId}@askfile.com`  // Email único baseado no session ID
  }), [userSessionId]);

  // === SUGESTÕES INICIAIS ===
  const quickSuggestions = useMemo(() => [
    "Resuma os principais pontos do documento",
    "Quais são as informações mais importantes?",
    "Explique o contexto geral do arquivo",
    "Há alguma conclusão ou resultado destacado?",
    "Quais dados numéricos são mencionados?"
  ], []);

  // === TROCA DE VIEW ===
  const handleViewChange = useCallback((newView) => {
    console.log('Mudando para view:', newView);
    setCurrentView(newView);
  }, []);

  // === DIGITAÇÃO ===
  const handleInputChange = useCallback((event) => {
    setCurrentMessage(event.target.value);
    if (event.target.value === '') {
      setSuggestions([]);
    } else {
      const filteredSuggestions = quickSuggestions.filter(s =>
        s.toLowerCase().includes(event.target.value.toLowerCase())
      );
      setSuggestions(filteredSuggestions);
    }
  }, [quickSuggestions]);

  // === ENVIO DE MENSAGEM ===
  const handleSendMessage = useCallback(async () => {
    if (!currentMessage.trim() || isLoading) return;

    if (!uploadedFile) {
      alert('Por favor, faça o upload de um arquivo PDF antes de fazer perguntas.');
      return;
    }

    setIsLoading(true);
    setSuggestions([]);

    const newUserMessage = {
      id: chatMessages.length + 1,
      text: currentMessage,
      sender: 'user',
      timestamp: new Date().toLocaleTimeString(),
      sources: []
    };

    setChatMessages((prevMessages) => [...prevMessages, newUserMessage]);
    const questionToSend = currentMessage;
    setCurrentMessage('');

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: questionToSend,
          file_id: uploadedFile.id,
          user_email: defaultUser.email  // MODIFICADO: Usa o email único
        }),
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const data = await response.json();
      console.log("Resposta da API:", data);

      const botMessage = {
        id: chatMessages.length + 2,
        text: data.answer,
        sender: 'bot',
        timestamp: new Date().toLocaleTimeString(),
        sources: data.sources || []
      };

      setChatMessages((prevMessages) => [...prevMessages, botMessage]);

    } catch (error) {
      console.error('Erro ao enviar mensagem:', error);
      setChatMessages((prevMessages) => [
        ...prevMessages,
        {
          id: prevMessages.length + 2,
          text: `Desculpe, não consegui obter uma resposta. (Erro: ${error.message})`,
          sender: 'bot',
          timestamp: new Date().toLocaleTimeString(),
          isError: true,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [currentMessage, isLoading, chatMessages.length, API_BASE_URL, uploadedFile, defaultUser.email]);

  // === ENTER PARA ENVIAR ===
  const handleKeyDown = useCallback((event) => {
    if (event.key === 'Enter' && !isLoading) {
      handleSendMessage();
    }
  }, [handleSendMessage, isLoading]);

  // === COPIAR TEXTO ===
  const copyToClipboard = useCallback((text) => {
    navigator.clipboard.writeText(text).then(() => {
      alert('Texto copiado para a área de transferência!');
    }).catch(err => console.error('Erro ao copiar texto: ', err));
  }, []);

  // === UPLOAD MODIFICADO ===
  const handleFileUpload = useCallback(async (file) => {
    if (!file) {
      alert("Nenhum arquivo selecionado.");
      return;
    }

    if (file.type !== 'application/pdf') {
      alert("Apenas arquivos PDF são aceitos.");
      return;
    }

    // Limpar dados anteriores antes do upload
    setUploadedFile(null);
    setChatMessages([]);
    setCurrentMessage('');
    setSuggestions([]);

    setFileProcessing(true);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('user_email', defaultUser.email);  // NOVO: Adiciona o email único

      const response = await fetch(`${API_BASE_URL}/api/upload`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (response.ok) {
        setUploadedFile({
          id: data.file_id,
          name: file.name,
          summary: data.summary,
          uploadDate: new Date().toISOString(),
          isTemporary: data.file_removed || false
        });

        alert(`Arquivo "${file.name}" processado com sucesso!`);
        console.log('Novo arquivo carregado para sessão:', userSessionId);
      } else {
        throw new Error(data.detail || `Erro ao processar arquivo: ${response.statusText}`);
      }
    } catch (error) {
      console.error('Erro no upload:', error);
      alert(`Falha ao processar arquivo: ${error.message}`);
      setUploadedFile(null);
      setChatMessages([]);
    } finally {
      setFileProcessing(false);
    }
  }, [API_BASE_URL, defaultUser.email, userSessionId]);

  // === TROCAR ARQUIVO ===
  const handleChangeFile = useCallback(() => {
    const confirmChange = window.confirm(
      'Tem certeza que deseja trocar o arquivo?\n\n' +
      'Isso irá:\n' +
      '• Remover o arquivo atual\n' +
      '• Limpar todas as mensagens do chat\n' +
      '• Permitir o upload de um novo arquivo'
    );

    if (confirmChange) {
      setUploadedFile(null);
      setChatMessages([]);
      setCurrentMessage('');
      setSuggestions([]);

      const fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.accept = '.pdf';
      fileInput.onchange = (event) => {
        const file = event.target.files[0];
        if (file) {
          handleFileUpload(file);
        }
      };
      fileInput.click();
    }
  }, [handleFileUpload]);

  // === HISTÓRICO ===
  const fetchUserHistory = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/history?user_email=${defaultUser.email}`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      setUserHistory(data.history || []);
    } catch (error) {
      console.error('Erro ao buscar histórico:', error);
      setUserHistory([]);
    } finally {
      setIsLoading(false);
    }
  }, [API_BASE_URL, defaultUser.email]);

  // === LOGOUT/LIMPAR DADOS ===
  const handleLogout = useCallback(async () => {
    const confirmClear = window.confirm(
      'Isso irá limpar todos os dados desta sessão:\n\n' +
      '• Histórico de conversas\n' +
      '• Arquivo carregado\n' +
      '• Mensagens do chat\n\n' +
      'Deseja continuar?'
    );

    if (confirmClear) {
      try {
        // Limpa histórico no servidor
        await fetch(`${API_BASE_URL}/api/history?user_email=${defaultUser.email}`, { method: 'DELETE' });
      } catch (error) {
        console.error('Erro ao limpar histórico no servidor:', error);
      }

      // Limpa dados locais
      setChatMessages([]);
      setUploadedFile(null);
      setUserHistory([]);
      setCurrentMessage('');
      setSuggestions([]);

      alert('Dados da sessão limpos com sucesso.');
    }
  }, [API_BASE_URL, defaultUser.email]);

  // === NOVA SESSÃO ===
  const handleNewSession = useCallback(() => {
    const confirmNew = window.confirm(
      'Isso irá criar uma nova sessão completamente isolada:\n\n' +
      '• Nova identidade de usuário\n' +
      '• Histórico independente\n' +
      '• Dados não compartilhados\n\n' +
      'Deseja continuar?'
    );

    if (confirmNew) {
      // Remove session ID atual
      localStorage.removeItem('askfile_session_id');
      
      // Recarrega a página para gerar nova sessão
      window.location.reload();
    }
  }, []);

  // === PROPS COMPARTILHADAS ===
  const sharedProps = {
    user: defaultUser,
    currentView,
    setCurrentView: handleViewChange,
    chatMessages,
    setChatMessages,
    currentMessage,
    setCurrentMessage,
    isLoading,
    setIsLoading,
    userHistory,
    setUserHistory,
    suggestions,
    setSuggestions,
    quickSuggestions,
    handleLogout,
    handleNewSession,  // NOVO: Nova função
    handleInputChange,
    handleSendMessage,
    handleKeyDown,
    copyToClipboard,
    API_BASE_URL,
    handleFileUpload,
    handleChangeFile,
    uploadedFile,
    setUploadedFile,
    fileProcessing,
    fetchUserHistory,
    sessionId: userSessionId  // NOVO: passa o session ID
  };

  // === RENDERIZAÇÃO ===
  switch (currentView) {
    case 'chat':
      return <ChatView {...sharedProps} />;
    case 'history':
      return <HistoryView {...sharedProps} />;
    default:
      return <ChatView {...sharedProps} />;
  }
};

export default AskFileSystem;