'use client'
import { useState } from 'react'
import { Download, Filter, RefreshCw, Calendar } from 'lucide-react'
import { api } from '../../lib/api'
import { PageHeader } from '../../components/UI'

const FILTERS = [
  { key: 'rfm_segment',     label: 'RFM Segment',     opts: ['Champion','Loyal','New Customer','Promising','Need Attention','At Risk','Cannot Lose','Lost','Occasional'] },
  { key: 'churn_risk',      label: 'Churn Risk',       opts: ['High','Medium','Low','None'] },
  { key: 'return_risk',     label: 'Return Risk',      opts: ['High','Medium','Low','No Returns'] },
  { key: 'customer_type',   label: 'Customer Type',    opts: ['New','Repeat'] },
  { key: 'channel_journey', label: 'Channel',          opts: ['Online Only','Offline Only','Both'] },
  { key: 'migration_type',  label: 'Migration',        opts: ['EBO First','Shopify First','Both Same Time','EBO Only','Shopify Only'] },
  { key: 'consumer_zone',   label: 'Zone',             opts: ['NORTH','SOUTH','EAST','WEST','CENTRAL'] },
  { key: 'platform',        label: 'Platform',         opts: ['Shopify','EBO','Both'] },
  { key: 'size_behaviour',  label: 'Size Behaviour',   opts: ['Single Size','Multi Size','No Size Data'] },
  { key: 'recency_bucket',  label: 'Recency',          opts: ['Active','Warm','Cooling','At Risk','Lapsed'] },
  { key: 'frequency_bucket',label: 'Frequency',        opts: ['1 Order','2 Orders','3-4 Orders','5-9 Orders','10+ Orders'] },
]

function getMonthOptions() {
  const opts = []
  const now  = new Date()
  for (let i = 0; i < 24; i++) {
    const d     = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const value = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`
    const label = d.toLocaleDateString('en-IN', { month:'short', year:'numeric' })
    opts.push({ value, label })
  }
  return opts
}
const MONTH_OPTIONS = getMonthOptions()

function fmtN(n) {
  if (!n && n !== 0) return '—'
  if (n>=100000) return `${(n/100000).toFixed(1)}L`
  if (n>=1000)   return `${(n/1000).toFixed(1)}K`
  return `${n}`
}

export default function ExportPage() {
  const [selected,      setSelected]      = useState({})
  const [textFilters,   setTextFilters]   = useState({ top_category:'', primary_store:'', consumer_city:'', consumer_pincode:'' })
  const [selectedMonths,setSelectedMonths]= useState([])
  const [count,         setCount]         = useState(null)
  const [counting,      setCounting]      = useState(false)

  const activeFilters = {
    ...Object.fromEntries(Object.entries(selected).filter(([,v]) => v)),
    ...Object.fromEntries(Object.entries(textFilters).filter(([,v]) => v.trim())),
    ...(selectedMonths.length > 0 ? { months: selectedMonths.join(',') } : {}),
  }

  const getCount = async () => {
    setCounting(true)
    try {
      const d = await api.getExportCount(activeFilters)
      setCount(d.count)
    } catch(e) { console.error(e) }
    finally { setCounting(false) }
  }

  const download = () => {
    const url = api.getExportUrl(activeFilters)
    window.open(url, '_blank')
  }

  const reset = () => {
    setSelected({})
    setTextFilters({ top_category:'', primary_store:'', consumer_city:'', consumer_pincode:'' })
    setSelectedMonths([])
    setCount(null)
  }

  const toggleMonth = (val) => {
    setSelectedMonths(prev =>
      prev.includes(val) ? prev.filter(m => m !== val) : [...prev, val]
    )
    setCount(null)
  }

  const activeCount = Object.values(activeFilters).filter(Boolean).length

  return (
    <div style={{ padding:'32px 36px', maxWidth:960, margin:'0 auto' }}>
      <PageHeader
        title="Self-Serve Export"
        subtitle="Apply any combination of filters and download customer data as CSV"
      />

      <div className="card" style={{ padding:24, marginBottom:16 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:20 }}>
          <div style={{ fontSize:14, fontWeight:600 }}>
            <Filter size={14} style={{ marginRight:6, verticalAlign:'middle' }}/>
            Filters {activeCount > 0 && (
              <span style={{ background:'var(--accent)', color:'#fff',
                borderRadius:20, padding:'1px 8px', fontSize:11, marginLeft:6 }}>
                {activeCount} active
              </span>
            )}
          </div>
          <button className="btn-ghost" onClick={reset} style={{ fontSize:12 }}>
            <RefreshCw size={12} style={{ marginRight:4 }}/> Reset All
          </button>
        </div>

        {/* Dropdown filters */}
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(200px,1fr))', gap:14, marginBottom:20 }}>
          {FILTERS.map(f => (
            <div key={f.key}>
              <label style={{ display:'block', fontSize:11, fontWeight:600,
                color:'var(--text-muted)', marginBottom:5,
                textTransform:'uppercase', letterSpacing:'0.06em' }}>
                {f.label}
              </label>
              <select className="input" style={{ padding:'8px 12px', fontSize:13 }}
                value={selected[f.key] || ''}
                onChange={e => { setSelected(s => ({ ...s, [f.key]: e.target.value })); setCount(null) }}>
                <option value="">All</option>
                {f.opts.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          ))}
        </div>

        {/* Text filters */}
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(200px,1fr))',
          gap:14, paddingTop:14, marginBottom:20, borderTop:'1px solid var(--border)' }}>
          {[
            { key:'top_category',    label:'Category (e.g. LEHENGA)' },
            { key:'primary_store',   label:'Store Name (exact)' },
            { key:'consumer_city',   label:'City (UPPERCASE)' },
            { key:'consumer_pincode',label:'Pincode' },
          ].map(f => (
            <div key={f.key}>
              <label style={{ display:'block', fontSize:11, fontWeight:600,
                color:'var(--text-muted)', marginBottom:5,
                textTransform:'uppercase', letterSpacing:'0.06em' }}>
                {f.label}
              </label>
              <input className="input" style={{ padding:'8px 12px', fontSize:13 }}
                placeholder="Optional"
                value={textFilters[f.key]}
                onChange={e => { setTextFilters(s => ({ ...s, [f.key]: e.target.value })); setCount(null) }}
              />
            </div>
          ))}
        </div>

        {/* Month filter */}
        <div style={{ paddingTop:14, borderTop:'1px solid var(--border)' }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:10 }}>
            <label style={{ fontSize:11, fontWeight:600, color:'var(--text-muted)',
              textTransform:'uppercase', letterSpacing:'0.06em',
              display:'flex', alignItems:'center', gap:6 }}>
              <Calendar size={12}/> Month Filter — select one or multiple
            </label>
            {selectedMonths.length > 0 && (
              <button onClick={() => { setSelectedMonths([]); setCount(null) }}
                style={{ background:'none', border:'none', cursor:'pointer',
                  color:'var(--text-muted)', fontSize:11 }}>
                Clear months ✕
              </button>
            )}
          </div>

          <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
            {MONTH_OPTIONS.map(o => (
              <button key={o.value} onClick={() => toggleMonth(o.value)}
                style={{
                  padding:'5px 12px', borderRadius:20, fontSize:11, cursor:'pointer',
                  border:'1px solid var(--border)', transition:'all 0.15s',
                  background: selectedMonths.includes(o.value) ? 'var(--accent)' : 'var(--bg-subtle)',
                  color: selectedMonths.includes(o.value) ? '#fff' : 'var(--text-secondary)',
                  fontWeight: selectedMonths.includes(o.value) ? 600 : 400,
                }}>
                {o.label}
              </button>
            ))}
          </div>

          {selectedMonths.length > 0 && (
            <div style={{ marginTop:10, padding:'8px 12px', background:'var(--accent-light)',
              borderRadius:7, fontSize:12, color:'var(--accent)', fontWeight:500 }}>
              📅 {selectedMonths.length} month{selectedMonths.length>1?'s':''} selected:&nbsp;
              {selectedMonths
                .sort()
                .map(m => MONTH_OPTIONS.find(o => o.value===m)?.label || m)
                .join(', ')}
            </div>
          )}
        </div>
      </div>

      {/* Action bar */}
      <div className="card" style={{ padding:'16px 24px',
        display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <div>
          {count !== null && (
            <div style={{ fontSize:16, fontWeight:700 }}>
              <span style={{ color:'var(--accent)', fontFamily:'var(--font-display)', fontSize:22 }}>
                {fmtN(count)}
              </span>
              <span style={{ color:'var(--text-secondary)', fontSize:13, marginLeft:8 }}>
                customers match your filters
              </span>
            </div>
          )}
          {count === null && (
            <div style={{ fontSize:13, color:'var(--text-muted)' }}>
              Click "Preview Count" to see how many customers match
            </div>
          )}
        </div>
        <div style={{ display:'flex', gap:10 }}>
          <button className="btn-ghost" onClick={getCount} disabled={counting}>
            {counting ? 'Counting...' : 'Preview Count'}
          </button>
          <button className="btn-primary" onClick={download}
            disabled={count === 0}
            style={{ display:'flex', alignItems:'center', gap:6 }}>
            <Download size={13}/>
            Download CSV {selectedMonths.length > 0 ? `(${selectedMonths.length} months)` : ''}
          </button>
        </div>
      </div>

      <div style={{ marginTop:16, fontSize:12, color:'var(--text-muted)', textAlign:'center' }}>
        Maximum 100,000 rows per export · Sorted by lifetime spend (highest first)
        {selectedMonths.length > 0 && ' · Month filter uses actual transaction dates'}
      </div>
    </div>
  )
}
