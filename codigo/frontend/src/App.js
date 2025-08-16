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
  
  // === ID ÚNICO POR USUÁRIO/SESSÃO ===
  const [userSessionId] = useState(() => {
    // Verifica se já existe um ID salvo no localStorage
    let sessionId = localStorage.getItem('askfile_session_id');
    if (!sessionId) {
      sessionId = generateSessionId();
      localStorage.setItem('askfile_session_id', sessionId);
    }
    return sessionId;
  });

  // === CONFIGURAÇÕES - URL CORRIGIDA ===
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
      console.log('Enviando requisição para:', `${API_BASE_URL}/api/chat`);
      
      const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        mode: 'cors',
        body: JSON.stringify({
          question: questionToSend,
          file_id: uploadedFile.id,
          user_email: defaultUser.email
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

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
          text: `Desculpe, não consegui obter uma resposta. Erro: ${error.message}`,
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

  // === UPLOAD MELHORADO ===
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
      console.log('Enviando upload para:', `${API_BASE_URL}/api/upload/`);
      
      const formData = new FormData();
      formData.append('file', file);
      formData.append('user_email', defaultUser.email);

      const response = await fetch(`${API_BASE_URL}/api/upload/`, {
        method: 'POST',
        mode: 'cors',
        body: formData,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      const data = await response.json();
      console.log("Resposta do upload:", data);

      if (data.file_id) {
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
        throw new Error('Resposta inválida do servidor');
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

  // === HISTÓRICO MELHORADO ===
  const fetchUserHistory = useCallback(async () => {
    setIsLoading(true);
    try {
      console.log('Buscando histórico de:', `${API_BASE_URL}/api/history`);
      
      const response = await fetch(`${API_BASE_URL}/api/history?user_email=${defaultUser.email}`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json'
        },
        mode: 'cors'
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }
      
      const data = await response.json();
      setUserHistory(data.history || []);
    } catch (error) {
      console.error('Erro ao buscar histórico:', error);
      setUserHistory([]);
    } finally {
      setIsLoading(false);
    }
  }, [API_BASE_URL, defaultUser.email]);

  // === LOGOUT/LIMPAR DADOS MELHORADO ===
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
        await fetch(`${API_BASE_URL}/api/history?user_email=${defaultUser.email}`, { 
          method: 'DELETE',
          mode: 'cors' 
        });
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
    sessionId: userSessionId
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