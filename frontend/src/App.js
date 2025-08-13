import React, { useState, useCallback, useEffect, useMemo } from 'react';
import LoginView from './components/LoginView/LoginView';
import ChatView from './components/ChatView/ChatView';
import HistoryView from './components/HistoryView/HistoryView';
import './App.css';

const AskFileSystem = () => {
  // === ESTADOS PRINCIPAIS DA APLICAÇÃO ===
  const [user, setUser] = useState(null); 
  const [currentView, setCurrentView] = useState('login'); 
  const [chatMessages, setChatMessages] = useState([]); 
  const [currentMessage, setCurrentMessage] = useState(''); 
  const [isLoading, setIsLoading] = useState(false); 
  const [userHistory, setUserHistory] = useState([]); 
  const [suggestions, setSuggestions] = useState([]); 
  const [uploadedFile, setUploadedFile] = useState(null); 
  const [fileProcessing, setFileProcessing] = useState(false);

  // === CONFIGURAÇÕES ===
  const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

  // === SUGESTÕES INICIAIS ===
  const quickSuggestions = useMemo(() => [
    "Resuma os principais pontos do documento",
    "Quais são as informações mais importantes?",
    "Explique o contexto geral do arquivo",
    "Há alguma conclusão ou resultado destacado?",
    "Quais dados numéricos são mencionados?"
  ], []);

  // === EFFECT PARA CARREGAR USUÁRIO ===
  useEffect(() => {
    const token = localStorage.getItem('token');
    const savedUser = localStorage.getItem('user');
    
    if (token && savedUser) {
      try {
        const userData = JSON.parse(savedUser);
        setUser(userData);
        setCurrentView('chat');
      } catch (error) {
        console.error('Erro ao carregar usuário salvo:', error);
        localStorage.removeItem('token');
        localStorage.removeItem('user');
      }
    }
  }, []);

  // === FUNÇÕES DE AUTENTICAÇÃO ===
  const onLoginSuccess = useCallback((userData, token) => {
    console.log('Login Success - User:', userData, 'Token:', token);
    
    setUser(userData);
    setCurrentView('chat');
    
    if (token) {
      localStorage.setItem('token', token);
    }
    if (userData) {
      localStorage.setItem('user', JSON.stringify(userData));
    }
  }, []);

  const handleLogout = useCallback(() => {
    setUser(null);
    setChatMessages([]);
    setUploadedFile(null);
    setCurrentView('login');
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    alert('Você foi desconectado.');
  }, []);

  // === FUNÇÃO PARA MUDANÇA DE VIEW ===
  const handleViewChange = useCallback((newView) => {
    console.log('Mudando para view:', newView);
    setCurrentView(newView);
  }, []);

  // === FUNÇÕES DO CHAT ===
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

  const handleSendMessage = useCallback(async () => {
    if (!currentMessage.trim() || isLoading) return;

    // Verifica se há arquivo carregado
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
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ 
          question: questionToSend,
          file_id: uploadedFile.id 
        }),
      });

      if (!response.ok) {
        if (response.status === 401) {
          alert('Sessão expirada. Por favor, faça login novamente.');
          handleLogout();
          return;
        }
        throw new Error(`HTTP error! status: ${response.status}`);
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
          text: `Desculpe, não consegui obter uma resposta. Por favor, tente novamente. (Erro: ${error.message})`,
          sender: 'bot',
          timestamp: new Date().toLocaleTimeString(),
          isError: true,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [currentMessage, isLoading, chatMessages.length, API_BASE_URL, handleLogout, uploadedFile]);

  const handleKeyDown = useCallback((event) => {
    if (event.key === 'Enter' && !isLoading) {
      handleSendMessage();
    }
  }, [handleSendMessage, isLoading]);

  const copyToClipboard = useCallback((text) => {
    navigator.clipboard.writeText(text).then(() => {
      alert('Texto copiado para a área de transferência!');
    }).catch(err => {
      console.error('Erro ao copiar texto: ', err);
    });
  }, []);

  // === FUNÇÃO DE UPLOAD ===
  const handleFileUpload = useCallback(async (file) => {
    if (!file) {
      alert("Nenhum arquivo selecionado.");
      return;
    }

    if (!file.type === 'application/pdf') {
      alert("Apenas arquivos PDF são aceitos.");
      return;
    }

    setFileProcessing(true);
    
    try {
      const formData = new FormData();
      formData.append('file', file);

      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData,
      });

      const data = await response.json();
      
      if (response.ok) {
        setUploadedFile({
          id: data.file_id,
          name: file.name,
          summary: data.summary,
          uploadDate: new Date().toISOString()
        });
        
        // Limpa mensagens antigas ao carregar novo arquivo
        setChatMessages([]);
        
        alert(`Arquivo "${file.name}" processado com sucesso!`);
      } else {
        throw new Error(data.detail || `Erro ao processar arquivo: ${response.statusText}`);
      }
    } catch (error) {
      console.error('Erro no upload:', error);
      alert(`Falha ao processar arquivo: ${error.message}`);
    } finally {
      setFileProcessing(false);
    }
  }, [API_BASE_URL]);

  // === FUNÇÕES DO HISTÓRICO ===
  const fetchUserHistory = useCallback(async () => {
    if (!user) return;
    setIsLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/history`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setUserHistory(data.history);
    } catch (error) {
      console.error('Erro ao buscar histórico:', error);
      setUserHistory([]);
    } finally {
      setIsLoading(false);
    }
  }, [user, API_BASE_URL]);

  useEffect(() => {
    if (user && currentView === 'history') {
      fetchUserHistory();
    }
  }, [user, currentView, fetchUserHistory]);

  // === PROPS COMPARTILHADAS ===
  const sharedProps = {
    user,
    setUser,
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
    uploadedFile,
    setUploadedFile,
    fileProcessing,
    fetchUserHistory
  };

  const loginProps = {
    API_BASE_URL,
    onLoginSuccess,
    isLoading,
    setIsLoading
  };

  // === RENDERIZAÇÃO ===
  if (!user) {
    return <LoginView {...loginProps} />;
  }

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