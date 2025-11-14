import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { 
  Send, 
  Settings, 
  FileText, 
  BarChart3, 
  Brain, 
  Loader2, 
  Globe, 
  Database, 
  Zap, 
  Download, 
  Trash2 
} from 'lucide-react';
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
  const [temperature, setTemperature] = useState(0.5);  // 0.3 → 0.5
  const [maxTokens, setMaxTokens] = useState(1500);    // 2000 → 1500
  const modeDefaults = {
    normal: { temperature: 0.5, maxTokens: 1500 },
    research: { temperature: 0.3, maxTokens: 2500 },
    creative: { temperature: 0.8, maxTokens: 2000 },
    code: { temperature: 0.2, maxTokens: 3000 }
  };

  // Mode değiştiğinde parametreleri otomatik ayarla
  useEffect(() => {
    const defaults = modeDefaults[mode] || modeDefaults.normal;
    setTemperature(defaults.temperature);
    setMaxTokens(defaults.maxTokens);
  }, [mode]); // mode değiştiğinde çalışır
  // Döküman
  const [uploadedFile, setUploadedFile] = useState(null);
  
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  
  useEffect(scrollToBottom, [messages]);
  
  // İstatistikleri yükle (optimize - 30s)
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
    const interval = setInterval(loadStats, 60000); // 30s → 60s (daha az istek)
    
    return () => clearInterval(interval);
  }, []);
  
  // Mesaj gönder (optimize)
  // Mesaj gönder (STREAMING DESTEĞI)
const sendMessage = async () => {
  if (!input.trim() || loading) return;
  
  const userMessage = {
    role: 'user',
    content: input,
    timestamp: new Date().toISOString()
  };
  
  setMessages(prev => [...prev, userMessage]);
  const currentInput = input;
  setInput('');
  setLoading(true);
  
  // Streaming için boş assistant mesajı ekle
  const assistantMessageIndex = messages.length + 1;
  setMessages(prev => [...prev, {
    role: 'assistant',
    content: '',
    sources: [],
    timestamp: new Date().toISOString(),
    streaming: true
  }]);
  
  try {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: currentInput,
        mode: mode,
        use_web_search: useWebSearch,
        max_sources: maxSources,
        temperature: temperature,
        max_tokens: maxTokens,
        user_id: userId,
        session_id: sessionId
      })
    });
    
    if (!response.ok) throw new Error('Streaming hatası');
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullText = '';
    let sources = [];
    
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            
            if (data.type === 'metadata') {
              sources = data.sources || [];
            } else if (data.type === 'chunk') {
              fullText += data.content;
              // Mesajı güncelle (streaming)
              setMessages(prev => {
                const newMessages = [...prev];
                newMessages[assistantMessageIndex] = {
                  role: 'assistant',
                  content: fullText,
                  sources: sources,
                  timestamp: new Date().toISOString(),
                  streaming: true
                };
                return newMessages;
              });
            } else if (data.type === 'done') {
              // Streaming bitti
              setMessages(prev => {
                const newMessages = [...prev];
                newMessages[assistantMessageIndex].streaming = false;
                return newMessages;
              });
            } else if (data.type === 'error') {
              throw new Error(data.message);
            }
          } catch (e) {
            console.error('Parse hatası:', e);
          }
        }
      }
    }
    
  } catch (error) {
    console.error('Hata:', error);
    setMessages(prev => {
      const newMessages = [...prev];
      newMessages[assistantMessageIndex] = {
        role: 'assistant',
        content: `❌ ${error.message}`,
        timestamp: new Date().toISOString(),
        streaming: false
      };
      return newMessages;
    });
  } finally {
    setLoading(false);
  }
};
// Chat history yükle
const loadHistory = async () => {
  try {
    const response = await axios.get(`${API_BASE}/history/${userId}/${sessionId}?limit=100`);
    if (response.data.history && response.data.history.length > 0) {
      const formattedMessages = response.data.history.map(msg => ({
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp,
        sources: msg.metadata?.sources || []
      }));
      setMessages(formattedMessages);
    }
  } catch (error) {
    console.error('History yükleme hatası:', error);
  }
};

// Chat export
const exportChat = async () => {
  try {
    const response = await axios.post(`${API_BASE}/history/export`, {
      user_id: userId,
      session_id: sessionId
    }, {
      responseType: 'blob'
    });
    
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `chat_${sessionId}.json`);
    document.body.appendChild(link);
    link.click();
    link.remove();
  } catch (error) {
    alert('Export hatası: ' + error.message);
  }
};

// Chat sil
const clearChat = async () => {
  if (!window.confirm('Tüm chat geçmişi silinecek. Emin misiniz?')) return;
  
  try {
    await axios.delete(`${API_BASE}/history/${userId}/${sessionId}`);
    setMessages([]);
    alert('✅ Chat geçmişi silindi');
  } catch (error) {
    alert('Silme hatası: ' + error.message);
  }
};
// History otomatik yükle
useEffect(() => {
  loadHistory();
}, []);  // Component mount olunca 1 kez çalışır
  
  // Enter ile gönder
  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };
  
  // Döküman yükle
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
      
      // Stats güncelle
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
  
  // Prompt şablonları
  const promptTemplates = {
    'Araştırma': 'Şu konuda detaylı araştırma yap: ',
    'Kod Yaz': 'Şu işi yapan kod yaz: ',
    'Özet': 'Şunu özetle: ',
    'Karşılaştır': 'Şu ikisini karşılaştır: ',
    'Açıkla': 'Şunu basitçe açıkla: '
  };
  
  // ⭐️ HATA DÜZELTMESİ (1/2): Fonksiyonun adını "use" ile başlamayacak şekilde değiştirdim.
  const applyTemplate = (template) => {
    setInput(template);
  };
  
  return (
    <div className="app">
      {/* Sidebar */}
      <div className="sidebar">
        <div className="logo">
          <Zap size={32} color="#8b5cf6" />
          <h1>Muhammet AI</h1>
          <span className="badge">ULTRA</span>
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
        
        {/* Hızlı İstatistikler */}
        {stats && (
          <div className="quick-stats">
            <div className="stat-item">
              <span className="stat-label">Toplam Soru</span>
              <span className="stat-value">{stats.total_queries}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Taranan Site</span>
              <span className="stat-value">{stats.total_scraped_sites}</span>
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
            <span>Ultra Optimize</span>
          </div>
        </div>
      </div>
      
      {/* Ana İçerik */}
      <div className="main-content">
        {activeTab === 'chat' && (
          <div className="chat-container">
            {/* Prompt Şablonları */}
            <div className="prompt-templates">
              {Object.entries(promptTemplates).map(([name, template]) => (
                <button 
                  key={name}
                  className="template-btn"
                  // ⭐️ HATA DÜZELTMESİ (2/2): Şimdi doğru adı ("applyTemplate") çağırıyoruz.
                  onClick={() => applyTemplate(template)}
                >
                  {name}
                </button>
              ))}
            </div>
            {/* Chat Toolbar (EXPORT/CLEAR) */}
<div className="chat-toolbar">
  <button className="toolbar-btn" onClick={loadHistory}>
    <Database size={16} />
    Geçmişi Yükle
  </button>
  <button className="toolbar-btn" onClick={exportChat}>
    <Download size={16} />
    Export JSON
  </button>
  <button className="toolbar-btn danger" onClick={clearChat}>
    <Trash2 size={16} />
    Tümünü Sil
  </button>
</div>
            {/* Mesajlar */}
            <div className="messages">
              {messages.length === 0 && (
                <div className="welcome">
                  <Brain size={64} />
                  <h2>Muhammet AI - Ultra Optimized</h2>
                  <p>3x daha hızlı • Akıllı cache • Sansürsüz</p>
                </div>
              )}
              
              {messages.map((msg, idx) => (
                <div key={idx} className={`message ${msg.role}`}>
                  <div className="message-content">
                    <ReactMarkdown
  components={{
    code({ node, inline, className, children, ...props }) {
      return (
        <code 
          className={className} 
          style={{
            background: 'rgba(0,0,0,0.3)',
            padding: inline ? '2px 6px' : '12px',
            borderRadius: '4px',
            display: inline ? 'inline' : 'block',
            fontFamily: 'monospace',
            fontSize: '14px'
          }}
          {...props}
        >
          {children}
        </code>
      );
    }
  }}
>
  {msg.content}
</ReactMarkdown>
                    
                    {/* Kaynaklar */}
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
      <span>🔍 Web'de aranıyor ve analiz ediliyor...</span>
    </div>
  </div>
)}
              
              <div ref={messagesEndRef} />
            </div>
            
            {/* Input Area */}
            <div className="input-area">
              <div className="mode-selector">
                <select value={mode} onChange={(e) => setMode(e.target.value)}>
                  <option value="normal">💬 Normal Sohbet</option>
                  <option value="research">🔍 Araştırmacı</option>
                  <option value="creative">🎨 Yaratıcı Yazar</option>
                  <option value="code">💻 Yazılımcı</option>
                  <option value="friend">👋 Arkadaş</option>
                  <option value="assistant">📋 Kişisel Asistan</option>
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
              <label>Temperature (Yaratıcılık): {temperature}</label>
              <input 
                type="range"
                min="0"
                max="1"
                step="0.1"
                value={temperature}
                onChange={(e) => setTemperature(parseFloat(e.target.value))}
              />
              <small>0.3 = Tutarlı (önerilen), 1.0 = Yaratıcı</small>
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
              <small>Cevap uzunluğu (1000-2000 önerilen)</small>
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
              <small>Web'de kaç site taransın (5 önerilen)</small>
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
              <small>Her soruda web araması yapsın mı?</small>
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
                Döküman Yükle (.txt, .md)
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
              <p>Yüklediğiniz dökümanlar otomatik indexlenir.</p>
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
                  <p className="stat-number">{stats.total_scraped_sites}</p>
                </div>
              </div>
              
              <div className="stat-card">
                <div className="stat-icon">📚</div>
                <div className="stat-info">
                  <h3>Yüklenen Döküman</h3>
                  <p className="stat-number">{stats.total_documents}</p>
                </div>
              </div>
              
              <div className="stat-card">
                <div className="stat-icon">💾</div>
                <div className="stat-info">
                  <h3>Database</h3>
                  <p className="stat-number">{stats.db_size} kayıt</p>
                </div>
              </div>
            </div>
            
            <div className="optimize-info">
              <h3>⚡ Optimize Özellikler</h3>
              <ul>
                <li>✅ 3x daha hızlı web scraping (paralel)</li>
                <li>✅ Akıllı cache (1 saat)</li>
                <li>✅ ChromaDB garantili kayıt</li>
                <li>✅ Google rate limit bypass</li>
                <li>✅ Duplicate prevention</li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;