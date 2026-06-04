'use client'
import { useState, useEffect, useRef } from 'react'
import { Send, Download, ChevronDown, ChevronUp, BarChart2, Sparkles } from 'lucide-react'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { api } from '../lib/api'

const COLORS = ['#0c8de4','#16a34a','#d97706','#7c3aed','#dc2626','#0d9488','#ec4899','#6b7280']

function fmt(n) {
  if (n == null) return '—'
  if (typeof n === 'string') return n
  if (typeof n !== 'number') return String(n)
  if (n >= 10000000) return `₹${(n/10000000).toFixed(1)}Cr`
  if (n >= 100000)   return `₹${(n/100000).toFixed(1)}L`
  if (n >= 1000)     return `₹${(n/1000).toFixed(1)}K`
  return n % 1 === 0 ? n.toString() : n.toFixed(2)
}

// Detect product-image URLs so SKU images render as thumbnails (not raw text)
function isImageUrl(col, val) {
  if (typeof val !== 'string' || !/^https?:\/\//i.test(val)) return false
  const c = (col || '').toLowerCase()
  return c.includes('image') || c.includes('img') || c.includes('photo')
      || val.includes('cdn.shopify') || /\.(jpe?g|png|webp|gif)(\?|$)/i.test(val)
}

function detectChart(columns, rows) {
  if (!rows || rows.length < 2) return null
  const numericCols = columns.filter((c, i) =>
    rows.slice(0,5).every(r => r[i] === null || typeof r[i] === 'number')
  )
  const textCols = columns.filter((c, i) =>
    rows.slice(0,5).some(r => typeof r[i] === 'string')
  )
  if (!numericCols.length || !textCols.length) return null
  return {
    labelIdx : columns.indexOf(textCols[0]),
    valueIdxs: numericCols.map(c => columns.indexOf(c)),
    labelKey : textCols[0],
    valueKeys: numericCols,
  }
}

function ResultBlock({ result, onExport }) {
  const [showSql, setShowSql] = useState(false)
  const [editSql, setEditSql] = useState(result.sql || '')
  const [view,    setView]    = useState('table')
  const cfg = result.rows?.length > 1 ? detectChart(result.columns, result.rows) : null

  const data = cfg ? result.rows.slice(0,20).map(r => {
    const obj = { label: String(r[cfg.labelIdx] || '—') }
    cfg.valueIdxs.forEach(vi => { obj[result.columns[vi]] = r[vi] })
    return obj
  }) : []

  if (result.status === 'error') return (
    <div style={{ background:'var(--red-light)', borderRadius:8, padding:'12px 14px', marginTop:8 }}>
      <div style={{ fontSize:12, fontWeight:600, color:'var(--red)', marginBottom:4 }}>Query Error</div>
      <div style={{ fontSize:11, fontFamily:'var(--font-mono)', color:'var(--red)' }}>{result.error}</div>
      {result.sql && (
        <div style={{ marginTop:8 }}>
          <textarea value={editSql} onChange={e => setEditSql(e.target.value)}
            style={{ width:'100%', fontFamily:'var(--font-mono)', fontSize:11,
              background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:6,
              padding:'8px', color:'var(--text-primary)', resize:'vertical', minHeight:70, outline:'none' }}/>
        </div>
      )}
    </div>
  )

  return (
    <div style={{ marginTop:8 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
        <span style={{ fontSize:11, color:'var(--text-muted)' }}>
          <strong style={{ color:'var(--text-primary)' }}>{result.row_count?.toLocaleString()}</strong> rows
        </span>
        <div style={{ display:'flex', gap:6 }}>
          {cfg && (
            <div style={{ display:'flex', background:'var(--bg-subtle)', borderRadius:5, overflow:'hidden', border:'1px solid var(--border)' }}>
              {[['table','Table'],['chart','Chart']].map(([v,l]) => (
                <button key={v} onClick={() => setView(v)} style={{
                  padding:'3px 10px', fontSize:10, fontWeight:600, border:'none', cursor:'pointer',
                  background: view===v ? 'var(--accent)' : 'transparent',
                  color: view===v ? '#fff' : 'var(--text-secondary)',
                }}>
                  {l}
                </button>
              ))}
            </div>
          )}
          <button onClick={() => setShowSql(s=>!s)} style={{
            fontSize:10, padding:'3px 8px', borderRadius:5, border:'1px solid var(--border)',
            background:'transparent', cursor:'pointer', color:'var(--text-secondary)',
            display:'flex', alignItems:'center', gap:3 }}>
            SQL {showSql ? <ChevronUp size={10}/> : <ChevronDown size={10}/>}
          </button>
          <button onClick={() => onExport(result.sql)} style={{
            fontSize:10, padding:'3px 8px', borderRadius:5, border:'1px solid var(--border)',
            background:'transparent', cursor:'pointer', color:'var(--text-secondary)',
            display:'flex', alignItems:'center', gap:3 }}>
            <Download size={10}/> CSV
          </button>
        </div>
      </div>

      {result.image && (
        <div style={{ marginBottom:10, textAlign:'center' }}>
          <img src={`data:image/png;base64,${result.image}`} alt="chart"
            style={{ maxWidth:'100%', borderRadius:8, border:'1px solid var(--border)' }}/>
        </div>
      )}

      {showSql && (
        <div style={{ marginBottom:8 }}>
          <textarea value={editSql} onChange={e => setEditSql(e.target.value)}
            style={{ width:'100%', fontFamily:'var(--font-mono)', fontSize:11,
              background:'var(--bg-subtle)', border:'1px solid var(--border)', borderRadius:6,
              padding:'8px', color:'var(--text-primary)', resize:'vertical', minHeight:60, outline:'none' }}/>
        </div>
      )}

      {view === 'chart' && cfg && (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={data} layout={data.length > 6 ? 'vertical' : 'horizontal'}>
            {data.length > 6 ? (
              <>
                <XAxis type="number" tick={{fontSize:10,fill:'var(--text-muted)'}} axisLine={false} tickLine={false} tickFormatter={fmt}/>
                <YAxis type="category" dataKey="label" tick={{fontSize:10,fill:'var(--text-muted)'}} axisLine={false} tickLine={false} width={120}/>
              </>
            ) : (
              <>
                <XAxis dataKey="label" tick={{fontSize:10,fill:'var(--text-muted)'}} axisLine={false} tickLine={false}/>
                <YAxis tick={{fontSize:10,fill:'var(--text-muted)'}} axisLine={false} tickLine={false} tickFormatter={fmt}/>
              </>
            )}
            <Tooltip formatter={v=>fmt(v)} contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:6,fontSize:11}}/>
            {cfg.valueKeys.map((key,i) => (
              <Bar key={key} dataKey={key} fill={COLORS[i%COLORS.length]} radius={[3,3,0,0]}/>
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}

      {view === 'table' && result.rows.length > 0 && (
        <div style={{ overflowX:'auto', borderRadius:6, border:'1px solid var(--border)', maxHeight:300, overflowY:'auto' }}>
          <table style={{ width:'100%', borderCollapse:'collapse', fontSize:11 }}>
            <thead style={{ position:'sticky', top:0, zIndex:1 }}>
              <tr style={{ background:'var(--bg-subtle)' }}>
                {result.columns.map(col => (
                  <th key={col} style={{ padding:'6px 10px', textAlign:'left', fontSize:10,
                    fontWeight:600, color:'var(--text-muted)', textTransform:'uppercase',
                    letterSpacing:'0.05em', whiteSpace:'nowrap', borderBottom:'1px solid var(--border)' }}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.slice(0,200).map((row,i) => (
                <tr key={i} style={{ borderBottom:'1px solid var(--border)' }}
                  onMouseEnter={e => e.currentTarget.style.background='var(--bg-hover)'}
                  onMouseLeave={e => e.currentTarget.style.background='transparent'}>
                  {row.map((val,j) => (
                    <td key={j} style={{ padding:'6px 10px', color:'var(--text-primary)', whiteSpace:'nowrap' }}>
                      {isImageUrl(result.columns[j], val)
                        ? <a href={val} target="_blank" rel="noreferrer">
                            <img src={val} alt="product" loading="lazy"
                              style={{ height:54, width:54, objectFit:'cover', borderRadius:6,
                                border:'1px solid var(--border)' }}/>
                          </a>
                        : (typeof val === 'number' ? fmt(val) : (val ?? '—'))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ── EBO Agent Component ────────────────────────────────────────────────────
export default function EBOAgent({ storeName = '' }) {
  const [messages,  setMessages]  = useState([])
  const [input,     setInput]     = useState('')
  const [loading,   setLoading]   = useState(false)
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  const EXAMPLES = storeName ? [
    `Top 10 customers by spend at ${storeName} this month`,
    `Which customers haven't visited ${storeName} in 90 days?`,
    `Top categories at ${storeName} by revenue`,
    `Cannot Lose customers at ${storeName} with contact details`,
    `New vs repeat customers at ${storeName} last 6 months`,
    `Which sizes sell most at ${storeName}?`,
  ] : [
    'Top 10 stores by revenue this month',
    'Which customers buy LEHENGA at EBO stores?',
    'Champion customers who shop both online and offline',
    'Average bill value per store',
    'Customers in NORTH zone with 5+ EBO visits',
    'Which store has the highest repeat rate?',
  ]

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:'smooth' }) }, [messages])

  const send = async () => {
    const q = input.trim()
    if (!q || loading) return
    setMessages(m => [...m, { role:'user', content:q }])
    setInput('')
    setLoading(true)

    const history = messages.slice(-6).map(m => ({
      role: m.role, content: m.role==='assistant' ? (m.sql||m.content) : m.content
    }))

    try {
      const result = await api.agentV2Query(q, storeName, history)
      setMessages(m => [...m, {
        role   : 'assistant',
        content: result.status==='success'
          ? (result.answer || `Found ${result.row_count?.toLocaleString()} rows`)
          : `Error: ${result.error}`,
        sql    : result.sql,
        result : result,
      }])
    } catch(e) {
      setMessages(m => [...m, { role:'assistant', content:`Failed: ${e.message}`, result:{status:'error',error:e.message,sql:'',columns:[],rows:[],row_count:0} }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const clearChat = () => {
    setMessages([])
    setInput('')
    setLoading(false)
    inputRef.current?.focus()
  }

  const exportCsv = async (sql) => {
    const res  = await api.agentV2ExportCsv(sql)
    const blob = await res.blob()
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url; a.download = 'ebo_query.csv'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="card" style={{ marginTop:24, overflow:'hidden' }}>
      {/* Header */}
      <div style={{ padding:'16px 20px', borderBottom:'1px solid var(--border)',
        background:'var(--bg-subtle)', display:'flex', alignItems:'center', gap:10 }}>
        <div style={{ width:32, height:32, borderRadius:'50%', background:'var(--accent)',
          display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
          <Sparkles size={16} color="#fff"/>
        </div>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:14, fontWeight:700 }}>
            EBO AI Agent {storeName && <span style={{ fontSize:12, color:'var(--accent)', fontWeight:400 }}>— {storeName}</span>}
          </div>
          <div style={{ fontSize:11, color:'var(--text-muted)' }}>
            Ask anything about {storeName ? 'this store' : 'EBO stores'} in plain English
          </div>
        </div>
        {messages.length > 0 && (
          <button onClick={clearChat} title="Clear all questions and answers"
            style={{ fontSize:12, fontWeight:600, padding:'6px 12px', borderRadius:7,
              border:'1px solid var(--border)', background:'var(--bg-card)', cursor:'pointer',
              color:'var(--text-secondary)', flexShrink:0 }}>
            Clear
          </button>
        )}
      </div>

      {/* Chat area */}
      <div style={{ padding:'16px 20px', maxHeight:480, overflowY:'auto' }}>
        {messages.length === 0 && (
          <div>
            <div style={{ fontSize:12, color:'var(--text-muted)', marginBottom:10 }}>Try asking:</div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6 }}>
              {EXAMPLES.map((q,i) => (
                <button key={i} onClick={() => { setInput(q); inputRef.current?.focus() }}
                  style={{ textAlign:'left', padding:'8px 12px', background:'var(--bg-subtle)',
                    border:'1px solid var(--border)', borderRadius:7, cursor:'pointer',
                    fontSize:11, color:'var(--text-secondary)', transition:'all 0.15s',
                    lineHeight:1.4 }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor='var(--accent)'; e.currentTarget.style.color='var(--accent)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor='var(--border)'; e.currentTarget.style.color='var(--text-secondary)' }}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg,i) => (
          <div key={i} style={{ marginBottom:16 }}>
            {msg.role === 'user' && (
              <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:6 }}>
                <div style={{ background:'var(--accent)', color:'#fff', padding:'8px 14px',
                  borderRadius:'14px 14px 4px 14px', fontSize:13, maxWidth:'75%' }}>
                  {msg.content}
                </div>
              </div>
            )}
            {msg.role === 'assistant' && (
              <div style={{ display:'flex', gap:8, alignItems:'flex-start' }}>
                <div style={{ width:26, height:26, borderRadius:'50%', background:'var(--accent)',
                  display:'flex', alignItems:'center', justifyContent:'center',
                  fontSize:13, flexShrink:0, marginTop:2 }}>🤖</div>
                <div style={{ flex:1 }}>
                  <div style={{ fontSize:12, color:'var(--text-secondary)', marginBottom:4 }}>
                    {msg.content}
                  </div>
                  {msg.result && <ResultBlock result={msg.result} onExport={exportCsv}/>}
                </div>
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div style={{ display:'flex', gap:8, alignItems:'center' }}>
            <div style={{ width:26, height:26, borderRadius:'50%', background:'var(--accent)',
              display:'flex', alignItems:'center', justifyContent:'center', fontSize:13 }}>🤖</div>
            <div style={{ display:'flex', gap:3 }}>
              {[0,1,2].map(i => (
                <div key={i} style={{ width:7, height:7, borderRadius:'50%', background:'var(--accent)',
                  animation:`pulse 1.2s ease-in-out ${i*0.2}s infinite` }}/>
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef}/>
      </div>

      {/* Input */}
      <div style={{ padding:'12px 16px', borderTop:'1px solid var(--border)',
        display:'flex', gap:8, alignItems:'center', background:'var(--bg-card)' }}>
        <input
          ref={inputRef}
          className="input"
          style={{ flex:1, border:'none', background:'transparent',
            padding:'6px 0', fontSize:13, outline:'none' }}
          placeholder={storeName
            ? `Ask about ${storeName}...`
            : "Ask about EBO customers, stores, categories..."}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key==='Enter' && !e.shiftKey && send()}
          disabled={loading}
        />
        <button className="btn-primary" onClick={send} disabled={loading||!input.trim()}
          style={{ display:'flex', alignItems:'center', gap:5, padding:'7px 14px', flexShrink:0 }}>
          <Send size={13}/>
          {loading ? '...' : 'Ask'}
        </button>
      </div>
      <style>{`@keyframes pulse{0%,100%{opacity:.3;transform:scale(.8)}50%{opacity:1;transform:scale(1)}}`}</style>
    </div>
  )
}
