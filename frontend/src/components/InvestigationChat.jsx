import React, { useState, useRef, useEffect } from 'react'
import { Send, Bot, User, ChevronDown, ChevronUp, ExternalLink, AlertCircle, RotateCcw, Sparkles, FileText, Search, Clock, Maximize2, Minimize2, Cpu } from 'lucide-react'
import { localCaseChat, getLLMProviders } from '../api'

// ── Markdown-lite renderer ──────────────────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return null
  
  return text.split('\n').map((line, i) => {
    // Bold
    let processed = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    // Inline code
    processed = processed.replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>')
    // Citation badges [Doc: ..., Chunk: ...]
    processed = processed.replace(
      /\[Doc:\s*(.*?),\s*Chunk:\s*(\d+)\]/g,
      '<span class="citation-badge">📄 $1 · Chunk #$2</span>'
    )
    // Warning marker
    processed = processed.replace(
      /⚠️\s*(.*)/g,
      '<span class="chat-warning">⚠️ $1</span>'
    )
    
    if (!processed.trim()) return <br key={i} />
    
    // Heading-like lines
    if (processed.startsWith('### ')) {
      return <h4 key={i} className="chat-heading" dangerouslySetInnerHTML={{ __html: processed.slice(4) }} />
    }
    if (processed.startsWith('## ')) {
      return <h3 key={i} className="chat-heading" dangerouslySetInnerHTML={{ __html: processed.slice(3) }} />
    }
    
    // Bullet points
    if (/^\s*[-•]\s/.test(processed)) {
      return <li key={i} className="chat-list-item" dangerouslySetInnerHTML={{ __html: processed.replace(/^\s*[-•]\s/, '') }} />
    }
    // Numbered list
    if (/^\s*\d+\.\s/.test(processed)) {
      return <li key={i} className="chat-list-item chat-list-numbered" dangerouslySetInnerHTML={{ __html: processed.replace(/^\s*\d+\.\s/, '') }} />
    }
    
    return <p key={i} className="chat-paragraph" dangerouslySetInnerHTML={{ __html: processed }} />
  })
}

// ── Score color helper ──────────────────────────────────────────────────────
function getScoreColor(score) {
  if (score >= 0.8) return '#10b981'
  if (score >= 0.6) return '#3b82f6'
  if (score >= 0.4) return '#f59e0b'
  return '#ef4444'
}

function getScoreLabel(score) {
  if (score >= 0.8) return 'High'
  if (score >= 0.6) return 'Good'
  if (score >= 0.4) return 'Moderate'
  return 'Low'
}

// ── Evidence Inspector Panel ────────────────────────────────────────────────
function EvidenceInspector({ sources }) {
  const [expanded, setExpanded] = useState(false)
  
  if (!sources || sources.length === 0) return null
  
  return (
    <div className="evidence-inspector">
      <button 
        className="evidence-inspector-toggle"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="evidence-inspector-toggle-left">
          <FileText size={14} />
          <span>{sources.length} evidence source{sources.length !== 1 ? 's' : ''} referenced</span>
        </div>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      
      {expanded && (
        <div className="evidence-inspector-body">
          {sources.map((src, idx) => (
            <div key={idx} className="evidence-chip">
              <div className="evidence-chip-header">
                <div className="evidence-chip-name">
                  <FileText size={12} />
                  <span>{src.file_name}</span>
                  <span className="evidence-chip-chunk">Chunk #{src.chunk_index}</span>
                </div>
                <div className="evidence-chip-score">
                  <span className="score-label" style={{ color: getScoreColor(src.score) }}>
                    {getScoreLabel(src.score)}
                  </span>
                  <span className="score-value">{(src.score * 100).toFixed(0)}%</span>
                </div>
              </div>
              
              <div className="score-bar-track">
                <div 
                  className="score-bar-fill"
                  style={{ 
                    width: `${src.score * 100}%`,
                    background: `linear-gradient(90deg, ${getScoreColor(src.score)}88, ${getScoreColor(src.score)})`
                  }}
                />
              </div>
              
              <div className="evidence-chip-text">
                {src.chunk_text.length > 300 
                  ? src.chunk_text.slice(0, 300) + '...' 
                  : src.chunk_text
                }
              </div>
              
              {src.file_url && (
                <a 
                  href={src.file_url} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="evidence-chip-link"
                >
                  <ExternalLink size={12} /> View Document
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Typing Indicator ────────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <div className="chat-bubble chat-bubble-assistant">
      <div className="chat-bubble-avatar assistant-avatar">
        <Bot size={16} />
      </div>
      <div className="chat-bubble-content">
        <div className="typing-indicator">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>
  )
}

// ── Starter Queries ─────────────────────────────────────────────────────────
const STARTER_QUERIES = [
  { icon: <Search size={14} />, text: "Who are the persons of interest in this case?" },
  { icon: <Search size={14} />, text: "What vehicles were mentioned in the evidence?" },
  { icon: <Clock size={14} />, text: "Show me a timeline of events from the evidence" },
  { icon: <Search size={14} />, text: "What locations are connected to this case?" },
]

// ── Main Component ──────────────────────────────────────────────────────────
export default function InvestigationChat({ caseId, messages: propMessages, setMessages: propSetMessages }) {
  const [localMessages, setLocalMessages] = useState([])
  const messages = propMessages || localMessages
  const setMessages = propSetMessages || setLocalMessages
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [isExpanded, setIsExpanded] = useState(false)
  const [providers, setProviders] = useState([])
  const [selectedProvider, setSelectedProvider] = useState('')
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  
  useEffect(() => {
    getLLMProviders().then(data => {
      setProviders(data.providers || [])
      setSelectedProvider(data.default_provider || '')
    }).catch(err => console.error('Failed to load providers:', err))
  }, [])
  
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }
  
  useEffect(() => {
    scrollToBottom()
  }, [messages, loading])
  
  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px'
    }
  }, [input])
  
  const handleSubmit = async (queryText) => {
    const query = queryText || input.trim()
    if (!query || loading) return
    
    setInput('')
    setError(null)
    
    // Add user message
    const userMsg = { role: 'user', content: query, timestamp: new Date() }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)
    
    try {
      // Build chat history (exclude sources, just role+content)
      const chatHistory = messages.map(m => ({
        role: m.role,
        content: m.content,
      }))
      
      const result = await localCaseChat(caseId, {
        query,
        chat_history: chatHistory,
        provider: selectedProvider || undefined,
        top_k: 10
      })
      
      const assistantMsg = {
        role: 'assistant',
        content: result.answer,
        sources: result.sources,
        documents_used: result.documents_used,
        context_strategy: result.context_strategy,
        provider_used: result.provider_used,
        model_used: result.model_used,
        failover_occurred: result.failover_occurred,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, assistantMsg])
      
    } catch (err) {
      console.error('Chat query failed:', err)
      const detail = err.response?.data?.detail || err.message || 'Unknown error'
      setError(detail)
    } finally {
      setLoading(false)
    }
  }
  
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }
  
  const handleRetry = () => {
    if (messages.length === 0) return
    // Find the last user message and retry
    const lastUserMsg = [...messages].reverse().find(m => m.role === 'user')
    if (lastUserMsg) {
      setError(null)
      // Remove last assistant message if it exists
      setMessages(prev => {
        const last = prev[prev.length - 1]
        return last?.role === 'assistant' ? prev.slice(0, -1) : prev
      })
      handleSubmit(lastUserMsg.content)
    }
  }
  
  return (
    <div className={`chat-container ${isExpanded ? 'chat-expanded' : ''}`}>
      {/* Header */}
      <div className="chat-header">
        <div className="chat-header-left">
          <div className="chat-header-avatar">
            <Sparkles size={18} />
          </div>
          <div>
            <h3 className="chat-header-title">Crime Investigation AI (CIA)</h3>
            <span className="chat-header-subtitle">Evidence-grounded investigation assistant</span>
          </div>
        </div>
        <div className="chat-header-right" style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <select 
            value={selectedProvider} 
            onChange={e => setSelectedProvider(e.target.value)}
            style={{ padding: '4px 8px', borderRadius: '6px', border: '1px solid rgba(0,0,0,0.1)', background: 'rgba(255,255,255,0.5)', fontSize: '0.8rem', outline: 'none' }}
          >
            <option value="">Default AI Model</option>
            {providers.filter(p => p.available).map(p => (
              <option key={p.provider} value={p.provider}>
                {p.provider.charAt(0).toUpperCase() + p.provider.slice(1)}
              </option>
            ))}
          </select>
          <button 
            style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center' }}
            onClick={() => setIsExpanded(!isExpanded)}
            title={isExpanded ? "Restore" : "Maximize"}
          >
            {isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
        </div>
      </div>
      
      {/* Messages Area */}
      <div className="chat-messages">
        {messages.length === 0 && !loading && (
          <div className="chat-empty-state">
            <div className="chat-empty-icon">
              <Bot size={40} />
            </div>
            <h3>Investigation Assistant</h3>
            <p>Ask questions about the evidence uploaded to this case. All answers are grounded in the uploaded documents with source citations.</p>
            
            <div className="chat-starter-queries">
              {STARTER_QUERIES.map((sq, idx) => (
                <button
                  key={idx}
                  className="starter-query-btn"
                  onClick={() => handleSubmit(sq.text)}
                >
                  {sq.icon}
                  <span>{sq.text}</span>
                </button>
              ))}
            </div>
          </div>
        )}
        
        {messages.map((msg, idx) => (
          <div key={idx} className={`chat-bubble chat-bubble-${msg.role}`}>
            <div className={`chat-bubble-avatar ${msg.role}-avatar`}>
              {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
            </div>
            <div className="chat-bubble-content">
              <div className="chat-bubble-meta">
                <span className="chat-bubble-role">
                  {msg.role === 'user' ? 'You' : 'CIA'}
                </span>
                {msg.role === 'assistant' && (
                  <span className="chat-bubble-model" style={{ fontSize: '0.7rem', background: 'rgba(0,0,0,0.05)', padding: '2px 6px', borderRadius: '4px', marginLeft: '6px' }}>
                    <Cpu size={10} style={{ display: 'inline', marginRight: '3px' }} />
                    {msg.model_used} 
                    {msg.context_strategy === 'full_document' ? ' (Long Context)' : ' (RAG)'}
                  </span>
                )}
                <span className="chat-bubble-time" style={{ marginLeft: 'auto' }}>
                  {msg.timestamp?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
              <div className="chat-bubble-text">
                {renderMarkdown(msg.content)}
              </div>
              {msg.sources && <EvidenceInspector sources={msg.sources} />}
            </div>
          </div>
        ))}
        
        {loading && <TypingIndicator />}
        
        {error && (
          <div className="chat-error">
            <AlertCircle size={16} />
            <span>{error}</span>
            <button className="chat-error-retry" onClick={handleRetry}>
              <RotateCcw size={14} /> Retry
            </button>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>
      
      {/* Input Area */}
      <div className="chat-input-area">
        <div className="chat-input-wrap">
          <textarea
            ref={textareaRef}
            className="chat-input"
            placeholder="Ask about the evidence..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
            rows={1}
          />
          <button
            className="chat-send-btn"
            onClick={() => handleSubmit()}
            disabled={!input.trim() || loading}
          >
            <Send size={18} />
          </button>
        </div>
        <div className="chat-input-hint">
          Press Enter to send · Shift+Enter for new line
        </div>
      </div>
    </div>
  )
}
