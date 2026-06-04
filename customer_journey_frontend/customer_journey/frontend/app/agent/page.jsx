'use client'
import { useState, useEffect, useRef } from 'react'
import { Send, Download, Play, RefreshCw, Database, ChevronDown, ChevronUp, BarChart2, Table } from 'lucide-react'
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { api } from '../../lib/api'
import { PageHeader } from '../../components/UI'

const COLORS = ['#0c8de4','#16a34a','#d97706','#7c3aed','#dc2626','#0d9488','#ec4899','#6b7280']

function fmt(n) {
  if (n == null) return '—'
  if (typeof n === 'string') return n
  if (typeof n !== 'number') return String(n)
  if (n >= 10000000) return `${(n/10000000).toFixed(1)}Cr`
  if (n >= 100000)   return `${(n/100000).toFixed(1)}L`
  if (n >= 1000)     return `${(n/1000).toFixed(1)}K`
  return n % 1 === 0 ? n.toString() : n.toFixed(2)
}

// Detect product-image URLs so SKU images render as thumbnails (not raw text)
function isImageUrl(col, val) {
  if (typeof val !== 'string' || !/^https?:\/\//i.test(val)) return false
  const c = (col || '').toLowerCase()
  return c.includes('image') || c.includes('img') || c.includes('photo')
      || val.includes('cdn.shopify') || /\.(jpe?g|png|webp|gif)(\?|$)/i.test(val)
}

// Detect if columns are suitable for a chart
function detectChartConfig(columns, rows) {
  if (!rows || rows.length === 0) return null
  // Need at least one text col + one numeric col
  const numericCols = columns.filter((c, i) =>
    rows.slice(0,5).every(r => r[i] === null || typeof r[i] === 'number')
  )
  const textCols = columns.filter((c, i) =>
    rows.slice(0,5).some(r => typeof r[i] === 'string')
  )
  if (numericCols.length === 0 || textCols.length === 0) return null
  return {
    labelCol  : columns.indexOf(textCols[0]),
    valueCols : numericCols.map(c => columns.indexOf(c)),
    labelKey  : textCols[0],
    valueKeys : numericCols,
  }
}

function ResultChart({ columns, rows }) {
  const cfg = detectChartConfig(columns, rows)
  if (!cfg || rows.length < 2) return null

  const data = rows.slice(0, 20).map(r => {
    const obj = { label: String(r[cfg.labelCol] || '—') }
    cfg.valueCols.forEach(vi => { obj[columns[vi]] = r[vi] })
    return obj
  })

  const isPie  = rows.length <= 8 && cfg.valueCols.length === 1
  const isLine = columns.some(c => c.toLowerCase().includes('month') || c.toLowerCase().includes('date'))

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)',
        textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
        <BarChart2 size={12} style={{ marginRight: 5, verticalAlign: 'middle' }} />
        Chart View
      </div>
      <ResponsiveContainer width="100%" height={260}>
        {isPie ? (
          <PieChart>
            <Pie data={data} dataKey={columns[cfg.valueCols[0]]}
              nameKey="label" cx="50%" cy="50%" outerRadius={100} paddingAngle={2}>
              {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip formatter={v => fmt(v)}
              contentStyle={{ background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:8, fontSize:12 }} />
          </PieChart>
        ) : isLine ? (
          <LineChart data={data}>
            <XAxis dataKey="label" tick={{ fontSize:11, fill:'var(--text-muted)' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize:11, fill:'var(--text-muted)' }} axisLine={false} tickLine={false} tickFormatter={fmt} />
            <Tooltip formatter={v => fmt(v)}
              contentStyle={{ background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:8, fontSize:12 }} />
            {cfg.valueKeys.map((key, i) => (
              <Line key={key} type="monotone" dataKey={key} stroke={COLORS[i]} strokeWidth={2} dot={{ r:3 }} />
            ))}
          </LineChart>
        ) : (
          <BarChart data={data} layout={rows.length > 8 ? 'vertical' : 'horizontal'}>
            {rows.length > 8 ? (
              <>
                <XAxis type="number" tick={{ fontSize:11, fill:'var(--text-muted)' }} axisLine={false} tickLine={false} tickFormatter={fmt} />
                <YAxis type="category" dataKey="label" tick={{ fontSize:11, fill:'var(--text-muted)' }} axisLine={false} tickLine={false} width={130} />
              </>
            ) : (
              <>
                <XAxis dataKey="label" tick={{ fontSize:11, fill:'var(--text-muted)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize:11, fill:'var(--text-muted)' }} axisLine={false} tickLine={false} tickFormatter={fmt} />
              </>
            )}
            <Tooltip formatter={v => fmt(v)}
              contentStyle={{ background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:8, fontSize:12 }} />
            {cfg.valueKeys.map((key, i) => (
              <Bar key={key} dataKey={key} fill={COLORS[i % COLORS.length]} radius={[3,3,0,0]} />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}

function ResultBlock({ result, onRunSql }) {
  const [showSql,   setShowSql]   = useState(false)
  const [editSql,   setEditSql]   = useState(result.sql || '')
  const [view,      setView]      = useState('table') // 'table' | 'chart'
  const [loading,   setLoading]   = useState(false)

  const hasChart = result.rows && result.rows.length > 1 &&
    detectChartConfig(result.columns, result.rows)

  const downloadCsv = async () => {
    const res = await api.agentV2ExportCsv(result.sql)
    const blob = await res.blob()
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = 'query_results.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const rerunSql = async () => {
    setLoading(true)
    const r = await api.agentExecute(editSql)
    setLoading(false)
    onRunSql(r, editSql)
  }

  if (result.status === 'error') {
    return (
      <div style={{ background:'var(--red-light)', borderRadius:8, padding:'12px 16px', marginTop:10 }}>
        <div style={{ fontSize:12, fontWeight:600, color:'var(--red)', marginBottom:6 }}>Query Error</div>
        <div style={{ fontSize:11, fontFamily:'var(--font-mono)', color:'var(--red)' }}>{result.error}</div>
        {result.sql && (
          <div style={{ marginTop:10 }}>
            <div style={{ fontSize:11, color:'var(--text-muted)', marginBottom:4 }}>Generated SQL (edit and re-run):</div>
            <textarea value={editSql} onChange={e => setEditSql(e.target.value)}
              style={{ width:'100%', fontFamily:'var(--font-mono)', fontSize:11,
                background:'var(--bg-card)', border:'1px solid var(--border)',
                borderRadius:6, padding:'8px 10px', color:'var(--text-primary)',
                resize:'vertical', minHeight:80, outline:'none' }} />
            <button className="btn-primary" onClick={rerunSql} disabled={loading}
              style={{ marginTop:8, fontSize:12, display:'flex', alignItems:'center', gap:5 }}>
              <Play size={12} /> {loading ? 'Running...' : 'Re-run'}
            </button>
          </div>
        )}
      </div>
    )
  }

  return (
    <div style={{ marginTop:10 }}>
      {/* Result header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
        <div style={{ fontSize:12, color:'var(--text-muted)' }}>
          <strong style={{ color:'var(--text-primary)' }}>{result.row_count?.toLocaleString()}</strong> rows returned
        </div>
        <div style={{ display:'flex', gap:8 }}>
          {hasChart && (
            <div style={{ display:'flex', background:'var(--bg-subtle)', borderRadius:6, overflow:'hidden',
              border:'1px solid var(--border)' }}>
              {[['table','Table',Table],['chart','Chart',BarChart2]].map(([v,l,Icon]) => (
                <button key={v} onClick={() => setView(v)} style={{
                  padding:'4px 12px', fontSize:11, fontWeight:600, border:'none',
                  cursor:'pointer', display:'flex', alignItems:'center', gap:4,
                  background: view===v ? 'var(--accent)' : 'transparent',
                  color: view===v ? '#fff' : 'var(--text-secondary)',
                  transition:'all 0.15s',
                }}>
                  <Icon size={11} />{l}
                </button>
              ))}
            </div>
          )}
          <button className="btn-ghost" onClick={() => setShowSql(s=>!s)}
            style={{ fontSize:11, padding:'4px 10px', display:'flex', alignItems:'center', gap:4 }}>
            SQL {showSql ? <ChevronUp size={11}/> : <ChevronDown size={11}/>}
          </button>
          <button className="btn-ghost" onClick={downloadCsv}
            style={{ fontSize:11, padding:'4px 10px', display:'flex', alignItems:'center', gap:4 }}>
            <Download size={11} /> CSV
          </button>
        </div>
      </div>

      {/* SQL block */}
      {showSql && (
        <div style={{ marginBottom:12 }}>
          <textarea value={editSql} onChange={e => setEditSql(e.target.value)}
            style={{ width:'100%', fontFamily:'var(--font-mono)', fontSize:11,
              background:'var(--bg-subtle)', border:'1px solid var(--border)',
              borderRadius:6, padding:'10px 12px', color:'var(--text-primary)',
              resize:'vertical', minHeight:70, outline:'none', lineHeight:1.5 }} />
          <button className="btn-ghost" onClick={rerunSql} disabled={loading}
            style={{ marginTop:6, fontSize:11, display:'flex', alignItems:'center', gap:4 }}>
            <Play size={11} /> {loading ? 'Running...' : 'Re-run edited SQL'}
          </button>
        </div>
      )}

      {/* Agent-generated chart image */}
      {result.image && (
        <div style={{ marginBottom:12, textAlign:'center' }}>
          <img src={`data:image/png;base64,${result.image}`} alt="chart"
            style={{ maxWidth:'100%', borderRadius:8, border:'1px solid var(--border)' }}/>
        </div>
      )}

      {/* Chart view */}
      {view === 'chart' && hasChart && (
        <ResultChart columns={result.columns} rows={result.rows} />
      )}

      {/* Table view */}
      {view === 'table' && result.rows.length > 0 && (
        <div style={{ overflowX:'auto', borderRadius:8, border:'1px solid var(--border)' }}>
          <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
            <thead>
              <tr style={{ background:'var(--bg-subtle)' }}>
                {result.columns.map(col => (
                  <th key={col} style={{ padding:'8px 12px', textAlign:'left', fontSize:11,
                    fontWeight:600, color:'var(--text-muted)', textTransform:'uppercase',
                    letterSpacing:'0.05em', whiteSpace:'nowrap', borderBottom:'1px solid var(--border)' }}>
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.slice(0, 500).map((row, i) => (
                <tr key={i} style={{ borderBottom:'1px solid var(--border)' }}
                  onMouseEnter={e => e.currentTarget.style.background='var(--bg-hover)'}
                  onMouseLeave={e => e.currentTarget.style.background='transparent'}>
                  {row.map((val, j) => (
                    <td key={j} style={{ padding:'8px 12px', color:'var(--text-primary)', whiteSpace:'nowrap' }}>
                      {isImageUrl(result.columns[j], val)
                        ? <a href={val} target="_blank" rel="noreferrer">
                            <img src={val} alt="product" loading="lazy"
                              style={{ height:56, width:56, objectFit:'cover', borderRadius:6,
                                border:'1px solid var(--border)' }}/>
                          </a>
                        : (typeof val === 'number' ? fmt(val) : (val ?? '—'))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {result.rows.length > 500 && (
            <div style={{ padding:'8px 12px', fontSize:11, color:'var(--text-muted)',
              textAlign:'center', borderTop:'1px solid var(--border)' }}>
              Showing first 500 of {result.rows.length.toLocaleString()} rows · Download CSV for full data
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main Agent Page ────────────────────────────────────────────────────────────
export default function AgentPage() {
  const [messages,  setMessages]  = useState([])
  const [input,     setInput]     = useState('')
  const [loading,   setLoading]   = useState(false)
  const [schema,    setSchema]    = useState(null)
  const [showSchema, setShowSchema] = useState(false)
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  useEffect(() => {
    api.getAgentSchema().then(setSchema).catch(() => {})
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    const q = input.trim()
    if (!q || loading) return

    const userMsg = { role:'user', content: q }
    setMessages(m => [...m, userMsg])
    setInput('')
    setLoading(true)

    // Build history for context
    const history = messages.slice(-6).map(m => ({
      role   : m.role,
      content: m.role === 'assistant' ? (m.sql || m.content) : m.content,
    }))

    try {
      const result = await api.agentV2Query(q, '', history)
      setMessages(m => [...m, {
        role   : 'assistant',
        content: result.status === 'success'
          ? (result.answer || `Found ${result.row_count?.toLocaleString()} rows`)
          : `Error: ${result.error}`,
        sql    : result.sql,
        result : result,
      }])
    } catch(e) {
      setMessages(m => [...m, {
        role   : 'assistant',
        content: `Failed to process query: ${e.message}`,
        result : { status:'error', error: e.message, sql:'', columns:[], rows:[], row_count:0 }
      }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const updateResult = (msgIndex, newResult, newSql) => {
    setMessages(m => m.map((msg, i) =>
      i === msgIndex
        ? { ...msg, result: { ...newResult, sql: newSql }, sql: newSql,
            content: newResult.status==='success'
              ? `Found ${newResult.row_count?.toLocaleString()} rows`
              : `Error: ${newResult.error}` }
        : msg
    ))
  }

  const clearChat = () => setMessages([])

  const askExample = (q) => {
    setInput(q)
    inputRef.current?.focus()
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100vh', padding:'24px 32px',
      maxWidth:1200, margin:'0 auto' }}>

      <PageHeader
        title="Libas Query Agent"
        subtitle="Ask any question about your customers in plain English"
        action={
          <div style={{ display:'flex', gap:8 }}>
            <button className="btn-ghost" onClick={() => setShowSchema(s=>!s)}
              style={{ fontSize:12, display:'flex', alignItems:'center', gap:5 }}>
              <Database size={13} /> Schema
            </button>
            {messages.length > 0 && (
              <button className="btn-ghost" onClick={clearChat}
                style={{ fontSize:12, display:'flex', alignItems:'center', gap:5 }}>
                <RefreshCw size={13} /> Clear
              </button>
            )}
          </div>
        }
      />

      {/* Schema panel */}
      {showSchema && schema && (
        <div className="card" style={{ padding:20, marginBottom:16 }}>
          <div style={{ fontSize:13, fontWeight:600, marginBottom:12 }}>Available Tables</div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(280px,1fr))', gap:8 }}>
            {schema.tables.map(t => (
              <div key={t.name} style={{ padding:'8px 12px', background:'var(--bg-subtle)',
                borderRadius:6, border:'1px solid var(--border)' }}>
                <div style={{ fontSize:12, fontWeight:600, fontFamily:'var(--font-mono)' }}>{t.name}</div>
                <div style={{ fontSize:10, color:'var(--text-muted)', marginTop:2 }}>{t.rows} rows · {t.desc}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Chat messages */}
      <div style={{ flex:1, overflowY:'auto', marginBottom:16 }}>
        {messages.length === 0 && (
          <div style={{ padding:'20px 0' }}>
            <div style={{ fontSize:14, fontWeight:600, marginBottom:16, color:'var(--text-secondary)' }}>
              💬 Try asking:
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
              {(schema?.example_questions || []).map((q, i) => (
                <button key={i} onClick={() => askExample(q)}
                  style={{ textAlign:'left', padding:'10px 14px', background:'var(--bg-card)',
                    border:'1px solid var(--border)', borderRadius:8, cursor:'pointer',
                    fontSize:12, color:'var(--text-secondary)', transition:'all 0.15s' }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor='var(--accent)'; e.currentTarget.style.color='var(--accent)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor='var(--border)'; e.currentTarget.style.color='var(--text-secondary)' }}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} style={{ marginBottom:20 }}>
            {/* User message */}
            {msg.role === 'user' && (
              <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:8 }}>
                <div style={{ background:'var(--accent)', color:'#fff', padding:'10px 16px',
                  borderRadius:'16px 16px 4px 16px', fontSize:13, maxWidth:'70%' }}>
                  {msg.content}
                </div>
              </div>
            )}

            {/* Assistant message */}
            {msg.role === 'assistant' && (
              <div style={{ display:'flex', gap:10, alignItems:'flex-start' }}>
                <div style={{ width:28, height:28, borderRadius:'50%', background:'var(--accent)',
                  display:'flex', alignItems:'center', justifyContent:'center',
                  fontSize:14, flexShrink:0, marginTop:2 }}>🤖</div>
                <div style={{ flex:1 }}>
                  <div style={{ fontSize:13, color:'var(--text-secondary)', marginBottom:6 }}>
                    {msg.content}
                  </div>
                  {msg.result && (
                    <ResultBlock
                      result={msg.result}
                      onRunSql={(newResult, newSql) => updateResult(i, newResult, newSql)}
                    />
                  )}
                </div>
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div style={{ display:'flex', gap:10, alignItems:'center', marginBottom:20 }}>
            <div style={{ width:28, height:28, borderRadius:'50%', background:'var(--accent)',
              display:'flex', alignItems:'center', justifyContent:'center', fontSize:14 }}>🤖</div>
            <div style={{ display:'flex', gap:4 }}>
              {[0,1,2].map(i => (
                <div key={i} style={{ width:8, height:8, borderRadius:'50%', background:'var(--accent)',
                  animation:`pulse 1.2s ease-in-out ${i*0.2}s infinite` }} />
              ))}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="card" style={{ padding:'12px 16px', display:'flex', gap:10, alignItems:'center' }}>
        <input
          ref={inputRef}
          className="input"
          style={{ flex:1, border:'none', background:'transparent', padding:'6px 0',
            fontSize:14, outline:'none' }}
          placeholder="Ask anything... e.g. 'Show me top 10 customers by lifetime value in Delhi'"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
          disabled={loading}
        />
        <button className="btn-primary" onClick={handleSend} disabled={loading || !input.trim()}
          style={{ display:'flex', alignItems:'center', gap:6, padding:'8px 16px', flexShrink:0 }}>
          <Send size={14} />
          {loading ? 'Thinking...' : 'Ask'}
        </button>
      </div>
      <div style={{ fontSize:11, color:'var(--text-muted)', textAlign:'center', marginTop:8 }}>
        Powered by Groq LLaMA 3.3 · Read-only access · Results limited to 500 rows display (full data via CSV)
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50%       { opacity: 1;   transform: scale(1); }
        }
      `}</style>
    </div>
  )
}
