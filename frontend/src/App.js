import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { Send, Settings, FileText, BarChart3, Brain, Loader2, Globe, Database, Zap } from 'lucide-react';
import './App.css';

const API_BASE = 'http://localhost:8000/api';

function App() {
  const [messages, setMessages] = useState([]);
  const [userId] = useState(() => `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);
  const [sessionId] = useState(() => `session_${Date.now()}`);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('chat');
  const [stats, setStats] = useState(null);
  
  // Ayarlar
  const [mode, setMode] = useState('normal');
  const [useWebSearch, setUseWebSearch] = useState(true);
  const [maxSources, setMaxSources] = useState(5);
  const [temperature, setTemperature] = useState(0.5);
  const [maxTokens, setMaxTokens] = useState(1500);
  
  const modeDefaults = {
    normal: { temperature: 0.5, maxTokens: 1500 },
    research: { temperature: 0.3, maxTokens: 2500 },
    creative: { temperature: 0.8, maxTokens: 2000 },
    code: { temperature: 0.2, maxTokens: 3000 }
  };

  useEffect(() => {
  const defaults = modeDefaults[mode] || modeDefaults.normal;
  setTemperature(defaults.temperature);
  setMaxTokens(defaults.maxTokens);
}, [mode, modeDefaults]);
  
  const [uploadedFile, setUploadedFile] = useState(null);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  
  useEffect(scrollToBottom, [messages]);
  
  // İstatistikler
  useEffect(() => {
    const loadStats = async () => {
      try {
        const response = await axios.get(`${API_BASE}/stats`);
        setStats(response.data);
      } catch (error) {
        console.error('Stats hatası:', error);
      }
    };
    
    loadStats();
    const interval = setInterval(loadStats, 60000);
    return () => clearInterval(interval);
  }, []);
  
  // ⚡ YENİ: Debug + Düzeltilmiş Mesaj Gönderme
  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    
    const simpleQueries = ['merhaba', 'selam', 'nasılsın', 'nasilsin', 'naber', 'hello', 'hi'];
    const isSimple = simpleQueries.some(word => input.toLowerCase().includes(word));
    const shouldUseWeb = isSimple ? false : useWebSearch;
    
    const userMessage = {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString()
    };
    
    setMessages(prev => [...prev, userMessage]);
    const currentInput = input;
    setInput('');
    setLoading(true);
    
    try {
      console.log('📤 İstek gönderiliyor:', {
        message: currentInput,
        mode,
        use_web_search: shouldUseWeb
      });
      
      const response = await axios.post(`${API_BASE}/chat`, {
        message: currentInput,
        mode: mode,
        use_web_search: shouldUseWeb,
        max_sources: maxSources,
        temperature: temperature,
        max_tokens: maxTokens,
        user_id: userId,
        session_id: sessionId
      }, {
        timeout: 90000
      });
      
      console.log('📥 Cevap geldi:', response.data);
      
      // ⚠️ DÜZELTME: response.data.response kontrolü
      const aiResponse = response.data?.response || response.data?.content || 'Cevap alınamadı';
      
      if (!aiResponse || aiResponse.trim() === '') {
        console.error('❌ Boş cevap geldi! Response:', response.data);
        throw new Error('Backend boş cevap döndürdü');
      }
      
      const aiMessage = {
        role: 'assistant',
        content: aiResponse,
        sources: response.data.sources || [],
        timestamp: response.data.timestamp || new Date().toISOString()
      };
      
      console.log('✅ AI Mesajı oluşturuldu:', aiMessage);
      setMessages(prev => [...prev, aiMessage]);
      
      if (stats) {
        setStats(prev => ({
          ...prev,
          total_queries: (prev?.total_queries || 0) + 1
        }));
      }
      
    } catch (error) {
      console.error('❌ Hata:', error);
      console.error('❌ Error response:', error.response?.data);
      
      let errorText = "Bağlantı sorunu. Lütfen tekrar deneyin.";
      
      if (error.code === 'ECONNABORTED') {
        errorText = "İstek zaman aşımına uğradı. Lütfen tekrar deneyin.";
      } else if (error.response) {
        errorText = `Backend hatası (${error.response.status}): ${JSON.stringify(error.response.data)}`;
      } else if (error.message) {
        errorText = `Hata: ${error.message}`;
      }
      
      const errorMessage = {
        role: 'assistant',
        content: `❌ ${errorText}`,
        timestamp: new Date().toISOString()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };
  
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };
  
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    
    setUploadedFile(file);
    
    try {
      const text = await file.text();
      
      await axios.post(`${API_BASE}/upload-document`, {
        content: text,
        filename: file.name,
        metadata: {
          size: file.size,
          type: file.type
        }
      });
      
      alert(`✅ ${file.name} başarıyla yüklendi!`);
      setUploadedFile(null);
      
      if (stats) {
        setStats(prev => ({
          ...prev,
          total_documents: (prev?.total_documents || 0) + 1,
          db_size: (prev?.db_size || 0) + 1
        }));
      }
      
    } catch (error) {
      alert(`❌ Hata: ${error.message}`);
      setUploadedFile(null);
    }
  };
  
  const promptTemplates = {
    'Araştırma': 'Şu konuda detaylı araştırma yap: ',
    'Kod Yaz': 'Şu işi yapan kod yaz: ',
    'Özet': 'Şunu özetle: ',
    'Karşılaştır': 'Şu ikisini karşılaştır: ',
    'Açıkla': 'Şunu basitçe açıkla: '
  };
  
  const applyTemplate = (template) => {
    setInput(template);
  };
  
  return (
    <div className="app">
      <div className="sidebar">
        <div className="logo">
          <Zap size={32} color="#8b5cf6" />
          <h1>DeepSeek AI</h1>
          <span className="badge">SANSÜRSÜZ</span>
        </div>
        
        <nav className="nav-tabs">
          <button 
            className={activeTab === 'chat' ? 'active' : ''}
            onClick={() => setActiveTab('chat')}
          >
            <Send size={20} />
            Chat
          </button>
          <button 
            className={activeTab === 'settings' ? 'active' : ''}
            onClick={() => setActiveTab('settings')}
          >
            <Settings size={20} />
            Ayarlar
          </button>
          <button 
            className={activeTab === 'documents' ? 'active' : ''}
            onClick={() => setActiveTab('documents')}
          >
            <FileText size={20} />
            Dökümanlar
          </button>
          <button 
            className={activeTab === 'stats' ? 'active' : ''}
            onClick={() => setActiveTab('stats')}
          >
            <BarChart3 size={20} />
            İstatistikler
          </button>
        </nav>
        
        {stats && (
          <div className="quick-stats">
            <div className="stat-item">
              <span className="stat-label">Toplam Soru</span>
              <span className="stat-value">{stats.total_queries}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Taranan Site</span>
              <span className="stat-value">{stats.total_scraped_sites || 0}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">DB Boyutu</span>
              <span className="stat-value">{stats.db_size}</span>
            </div>
          </div>
        )}
        
        <div className="sidebar-footer">
          <div className="optimize-badge">
            <Zap size={16} />
            <span>Sansürsüz Mod</span>
          </div>
        </div>
      </div>
      
      <div className="main-content">
        {activeTab === 'chat' && (
          <div className="chat-container">
            <div className="prompt-templates">
              {Object.entries(promptTemplates).map(([name, template]) => (
                <button 
                  key={name}
                  className="template-btn"
                  onClick={() => applyTemplate(template)}
                >
                  {name}
                </button>
              ))}
            </div>
            
            <div className="messages">
              {messages.length === 0 && (
                <div className="welcome">
                  <Brain size={64} />
                  <h2>DeepSeek AI - Sansürsüz</h2>
                  <p>Türkçe optimizasyonlu • Hybrid learning</p>
                  <small style={{marginTop: '10px', color: '#888'}}>
                    🔍 F12 açıp Console'u kontrol edin
                  </small>
                </div>
              )}
              
              {messages.map((msg, idx) => (
                <div key={idx} className={`message ${msg.role}`}>
                  <div className="message-content">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                    
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="sources">
                        <h4>📚 Kaynaklar ({msg.sources.length})</h4>
                        {msg.sources.map((source, i) => (
                          <a 
                            key={i}
                            href={source.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="source-link"
                          >
                            {source.title}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                  {msg.timestamp && (
                    <div className="message-timestamp">
                      {new Date(msg.timestamp).toLocaleTimeString('tr-TR')}
                    </div>
                  )}
                </div>
              ))}
              
              {loading && (
                <div className="message assistant">
                  <div className="message-content">
                    <Loader2 className="spinner" size={24} />
                    <span>💭 Düşünüyor...</span>
                  </div>
                </div>
              )}
              
              <div ref={messagesEndRef} />
            </div>
            
            <div className="input-area">
              <div className="mode-selector">
                <select value={mode} onChange={(e) => setMode(e.target.value)}>
                  <option value="normal">💬 Normal</option>
                  <option value="research">🔍 Araştırma</option>
                  <option value="creative">🎨 Yaratıcı</option>
                  <option value="code">💻 Kod</option>
                </select>
                
                <label className="web-toggle">
                  <Globe size={16} />
                  <input 
                    type="checkbox"
                    checked={useWebSearch}
                    onChange={(e) => setUseWebSearch(e.target.checked)}
                  />
                  Web Araması
                </label>
              </div>
              
              <div className="input-wrapper">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Mesajınızı yazın... (Enter: Gönder)"
                  rows={3}
                  disabled={loading}
                />
                <button 
                  onClick={sendMessage}
                  disabled={loading || !input.trim()}
                  className="send-btn"
                >
                  {loading ? <Loader2 className="spinner" size={20} /> : <Send size={20} />}
                </button>
              </div>
            </div>
          </div>
        )}
        
        {activeTab === 'settings' && (
          <div className="settings-panel">
            <h2>⚙️ Model Ayarları</h2>
            
            <div className="setting-group">
              <label>Temperature: {temperature}</label>
              <input 
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
              />
            </div>
            
            <div className="setting-group">
              <label>Maksimum Token: {maxTokens}</label>
              <input 
                type="range"
                min="500"
                max="3000"
                step="100"
                value={maxTokens}
                onChange={(e) => setMaxTokens(parseInt(e.target.value))}
              />
            </div>
            
            <div className="setting-group">
              <label>Maksimum Kaynak: {maxSources}</label>
              <input 
                type="range"
                min="3"
                max="10"
                step="1"
                value={maxSources}
                onChange={(e) => setMaxSources(parseInt(e.target.value))}
              />
            </div>
            
            <div className="setting-group">
              <label>
                <input 
                  type="checkbox"
                  checked={useWebSearch}
                  onChange={(e) => setUseWebSearch(e.target.checked)}
                />
                Otomatik Web Araması
              </label>
            </div>
          </div>
        )}
        
        {activeTab === 'documents' && (
          <div className="documents-panel">
            <h2>📄 Döküman Yönetimi</h2>
            
            <div className="upload-area">
              <input 
                ref={fileInputRef}
                type="file"
                accept=".txt,.md"
                onChange={handleFileUpload}
                style={{ display: 'none' }}
              />
              <button 
                className="upload-btn"
                onClick={() => fileInputRef.current.click()}
              >
                <FileText size={24} />
                Döküman Yükle
              </button>
              
              {uploadedFile && (
                <div className="upload-status">
                  ✅ {uploadedFile.name} yükleniyor...
                </div>
              )}
            </div>
            
            <div className="info-box">
              <Database size={32} />
              <h3>Vektör Database</h3>
              <p><strong>Toplam:</strong> {stats?.total_documents || 0} döküman</p>
              <p><strong>DB Boyutu:</strong> {stats?.db_size || 0} kayıt</p>
            </div>
          </div>
        )}
        
        {activeTab === 'stats' && stats && (
          <div className="stats-panel">
            <h2>📊 Sistem İstatistikleri</h2>
            
            <div className="stats-grid">
              <div className="stat-card">
                <div className="stat-icon">💬</div>
                <div className="stat-info">
                  <h3>Toplam Soru</h3>
                  <p className="stat-number">{stats.total_queries}</p>
                </div>
              </div>
              
              <div className="stat-card">
                <div className="stat-icon">🌐</div>
                <div className="stat-info">
                  <h3>Taranan Site</h3>
                  <p className="stat-number">{stats.total_scraped_sites || 0}</p>
                </div>
              </div>
              
              <div className="stat-card">
                <div className="stat-icon">📚</div>
                <div className="stat-info">
                  <h3>Döküman</h3>
                  <p className="stat-number">{stats.total_documents}</p>
                </div>
              </div>
              
              <div className="stat-card">
                <div className="stat-icon">💾</div>
                <div className="stat-info">
                  <h3>Database</h3>
                  <p className="stat-number">{stats.db_size}</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;