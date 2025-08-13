import React, { useState } from 'react';
import { FileText, User } from 'lucide-react';
import GoogleLoginButton from '../GoogleLoginButton/GoogleLoginButton';
import './LoginView.css';

const LoginView = ({ 
  API_BASE_URL,
  onLoginSuccess,
  isLoading,
  setIsLoading
}) => {
  // === ESTADOS LOCAIS ===
  const [credentials, setCredentials] = useState({ 
    email: '', 
    password: '' 
  });
  const [registerData, setRegisterData] = useState({ 
    name: '', 
    email: '', 
    password: '', 
    confirmPassword: '' 
  });
  const [loginMode, setLoginMode] = useState('traditional');

  // === VALIDAÇÕES ===
  const validateEmail = (email) => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const validateLoginForm = () => {
    if (!credentials.email || !credentials.password) {
      alert('Por favor, preencha email e senha!');
      return false;
    }

    if (!validateEmail(credentials.email)) {
      alert('Por favor, insira um email válido!');
      return false;
    }

    return true;
  };

  const validateRegisterForm = () => {
    if (!registerData.name || !registerData.email || !registerData.password) {
      alert('Preencha todos os campos!');
      return false;
    }
    
    if (registerData.name.trim().length < 2) {
      alert('O nome deve ter pelo menos 2 caracteres!');
      return false;
    }
    
    if (!validateEmail(registerData.email)) {
      alert('Por favor, insira um email válido!');
      return false;
    }
    
    if (registerData.password.length < 6) {
      alert('A senha deve ter pelo menos 6 caracteres!');
      return false;
    }
    
    if (registerData.password !== registerData.confirmPassword) {
      alert('As senhas não coincidem!');
      return false;
    }

    return true;
  };

  // === LOGIN TRADICIONAL ===
  const handleLogin = async () => {
    if (!validateLoginForm()) return;

    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/login`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/x-www-form-urlencoded' 
        },
        body: new URLSearchParams({ 
          username: credentials.email, 
          password: credentials.password 
        }).toString(),
      });
      
      const data = await response.json();
      
      if (response.ok) {
        onLoginSuccess(data.user, data.access_token);
        setCredentials({ email: '', password: '' });
      } else {
        alert('Erro no login: ' + (data.detail || 'Email ou senha incorretos.'));
      }
    } catch (error) {
      console.error('Erro no login:', error);
      alert('Erro de conexão. Verifique sua internet e tente novamente.');
    } finally {
      setIsLoading(false);
    }
  };

  // === REGISTRO ===
  const handleRegister = async () => {
    if (!validateRegisterForm()) return;

    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/login/register`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json' 
        },
        body: JSON.stringify({
          name: registerData.name.trim(),
          email: registerData.email.toLowerCase(),
          password: registerData.password
        }),
      });
      
      const data = await response.json();
      
      if (response.ok) {
        alert('🎉 Cadastro realizado com sucesso!\n\nAgora você pode fazer login com suas credenciais.');
        
        setRegisterData({ 
          name: '', 
          email: '', 
          password: '', 
          confirmPassword: '' 
        });
        
        setLoginMode('traditional');
        
        setCredentials({ 
          email: registerData.email, 
          password: '' 
        });
      } else {
        const errorMessage = data.detail || 'Erro desconhecido no cadastro.';
        alert('Erro no cadastro: ' + errorMessage);
      }
    } catch (error) {
      console.error('Erro no cadastro:', error);
      alert('Erro de conexão. Verifique sua internet e tente novamente.');
    } finally {
      setIsLoading(false);
    }
  };

  // === GOOGLE LOGIN ===
  const handleGoogleSuccess = async (userData) => {
    setIsLoading(true);
    try {
      console.log('Google Login Success:', userData);
      
      const response = await fetch(`${API_BASE_URL}/api/login/google`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json' 
        },
        body: JSON.stringify(userData),
      });
      
      const data = await response.json();
      
      if (response.ok) {
        onLoginSuccess(data.user, data.access_token);
      } else {
        alert('Erro no login com Google: ' + (data.detail || 'Erro desconhecido.'));
      }
    } catch (error) {
      console.error('Erro no login com Google:', error);
      alert('Erro de conexão com Google. Tente novamente.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleError = (error) => {
    console.error('Google Login Error:', error);
    alert('Falha no login com Google. Tente novamente.');
  };

  // === HANDLERS ===
  const handleKeyDown = (e, action) => {
    if (e.key === 'Enter' && !isLoading) {
      e.preventDefault();
      action();
    }
  };

  const handleTabSwitch = (mode) => {
    setLoginMode(mode);
    if (mode === 'traditional') {
      setRegisterData({ name: '', email: '', password: '', confirmPassword: '' });
    } else {
      setCredentials({ email: '', password: '' });
    }
  };

  return (
    <div className="login-container">
      {/* Animação de fundo */}
      <div className="background-animation">
        <div className="floating-element element-1"></div>
        <div className="floating-element element-2"></div>
        <div className="floating-element element-3"></div>
        <div className="floating-element element-4"></div>
      </div>

      <div className="login-card">
        {/* Cabeçalho */}
        <div className="login-header">
          <div className="logo-container">
            <FileText size={40} />
          </div>
          <h1 className="system-title">AskFile</h1>
          <p className="system-subtitle">Faça perguntas ao seu PDF</p>
          <p className="document-version">Upload, Pergunte e Descubra</p>
        </div>

        {/* Conteúdo principal */}
        <div className="login-content">
          {/* Botões de navegação */}
          <div className="tab-buttons">
            <button
              onClick={() => handleTabSwitch('traditional')}
              className={`tab-button ${loginMode === 'traditional' ? 'active-tab-teal' : 'inactive-tab'}`}
              disabled={isLoading}
            >
              Login
            </button>
            <button
              onClick={() => handleTabSwitch('register')}
              className={`tab-button ${loginMode === 'register' ? 'active-tab-blue' : 'inactive-tab'}`}
              disabled={isLoading}
            >
              Cadastro
            </button>
          </div>

          {/* Formulário de Login */}
          {loginMode === 'traditional' ? (
            <div className="form-container">
              <div className="form-group">
                <label className="form-label">Email</label>
                <input
                  type="email"
                  className="form-input"
                  placeholder="Digite seu email"
                  value={credentials.email}
                  onChange={(e) => setCredentials({...credentials, email: e.target.value})}
                  onKeyDown={(e) => handleKeyDown(e, handleLogin)}
                  disabled={isLoading}
                />
              </div>
              
              <div className="form-group">
                <label className="form-label">Senha</label>
                <input
                  type="password"
                  className="form-input"
                  placeholder="Digite sua senha"
                  value={credentials.password}
                  onChange={(e) => setCredentials({...credentials, password: e.target.value})}
                  onKeyDown={(e) => handleKeyDown(e, handleLogin)}
                  disabled={isLoading}
                />
              </div>
              
              <div className="button-group">
                <button
                  onClick={handleLogin}
                  disabled={isLoading}
                  className="primary-button"
                >
                  {isLoading ? (
                    <div className="loading-content">
                      <div className="spinner"></div>
                      Entrando...
                    </div>
                  ) : (
                    <>
                      <User className="button-icon" />
                      Entrar
                    </>
                  )}
                </button>
                
                <GoogleLoginButton
                  clientId={process.env.REACT_APP_GOOGLE_CLIENT_ID}
                  onSuccess={handleGoogleSuccess}
                  onError={handleGoogleError}
                  disabled={isLoading}
                  buttonText="Entrar com Google"
                />
                
                <div className="info-box info-box-teal">
                  <p className="info-text">
                    ✨ Sistema AskFile - Transforme seus PDFs em conversas inteligentes
                  </p>
                  <div className="feature-list">
                    <div className="feature-item">
                      <span>📄 Upload de PDFs</span>
                    </div>
                    <div className="feature-item">
                      <span>🤖 IA conversacional</span>
                    </div>
                    <div className="feature-item">
                      <span>💬 Perguntas e respostas</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* Formulário de Registro */
            <div className="form-container">
              <div className="form-group">
                <label className="form-label">Nome Completo</label>
                <input
                  type="text"
                  className="form-input-blue"
                  placeholder="Digite seu nome completo"
                  value={registerData.name}
                  onChange={(e) => setRegisterData({...registerData, name: e.target.value})}
                  disabled={isLoading}
                />
              </div>
              
              <div className="form-group">
                <label className="form-label">Email</label>
                <input
                  type="email"
                  className="form-input-blue"
                  placeholder="Digite seu email"
                  value={registerData.email}
                  onChange={(e) => setRegisterData({...registerData, email: e.target.value})}
                  disabled={isLoading}
                />
              </div>
              
              <div className="form-group">
                <label className="form-label">Senha</label>
                <input
                  type="password"
                  className="form-input-blue"
                  placeholder="Digite sua senha (mín. 6 caracteres)"
                  value={registerData.password}
                  onChange={(e) => setRegisterData({...registerData, password: e.target.value})}
                  disabled={isLoading}
                />
              </div>
              
              <div className="form-group">
                <label className="form-label">Confirmar Senha</label>
                <input
                  type="password"
                  className="form-input-blue"
                  placeholder="Confirme sua senha"
                  value={registerData.confirmPassword}
                  onChange={(e) => setRegisterData({...registerData, confirmPassword: e.target.value})}
                  onKeyDown={(e) => handleKeyDown(e, handleRegister)}
                  disabled={isLoading}
                />
              </div>
              
              <button
                onClick={handleRegister}
                disabled={isLoading}
                className="register-button"
              >
                {isLoading ? (
                  <div className="loading-content">
                    <div className="spinner"></div>
                    Criando conta...
                  </div>
                ) : (
                  <>
                    <User className="button-icon" />
                    Criar Conta
                  </>
                )}
              </button>
              
              <div className="info-box info-box-blue">
                <p className="info-text">
                  🚀 Crie sua conta e comece a usar o AskFile
                </p>
                <div className="register-benefits">
                  <div className="benefit-item">
                    <span>✅ Acesso gratuito</span>
                  </div>
                  <div className="benefit-item">
                    <span>💾 Histórico salvo</span>
                  </div>
                  <div className="benefit-item">
                    <span>🔒 Dados seguros</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Rodapé */}
        <div className="terms-text">
          <p>Ao fazer login, você concorda com nossos termos de uso</p>
        </div>
      </div>
    </div>
  );
};

export default LoginView;