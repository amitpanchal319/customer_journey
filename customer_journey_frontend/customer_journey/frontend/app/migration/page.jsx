'use client'
import { useState, useEffect } from 'react'
import { Download, Users } from 'lucide-react'
import { PageHeader, Table, CardSkeleton, SegBadge, ChurnBadge, Empty } from '../../components/UI'

function fmt(n)  { if (!n&&n!==0) return '—'; if(n>=10000000) return `₹${(n/10000000).toFixed(1)}Cr`; if(n>=100000) return `₹${(n/100000).toFixed(1)}L`; if(n>=1000) return `₹${(n/1000).toFixed(1)}K`; return `₹${n}` }
function fmtN(n) { if (!n&&n!==0) return '—'; if(n>=10000000) return `${(n/10000000).toFixed(1)}Cr`; if(n>=100000) return `${(n/100000).toFixed(1)}L`; if(n>=1000) return `${(n/1000).toFixed(1)}K`; return `${n}` }

const PATTERNS = [
  {
    key        : 'ebo_never_back',
    label      : 'EBO → Never Came Back',
    desc       : 'Visited store but never returned offline (180+ days silent)',
    color      : 'var(--amber)',
    apiPath    : '/api/cohorts/channel-migration/ebo-first-never-back',
    exportParam: 'ebo_never_back',
  },
  {
    key        : 'online_never_offline',
    label      : 'Online → Never Visited Store',
    desc       : 'Purchased only online, never visited any EBO store',
    color      : 'var(--accent)',
    apiPath    : '/api/cohorts/channel-migration/online-never-offline',
    exportParam: 'online_never_offline',
  },
  {
    key        : 'same_month',
    label      : 'EBO + Online Same Month',
    desc       : 'Bought offline and online in the same month',
    color      : 'var(--purple)',
    apiPath    : '/api/cohorts/channel-migration/ebo-to-online-same-month',
    exportParam: 'same_month',
  },
]

const COLS_MAP = {
  ebo_never_back: [
    { key:'consumer_name',    label:'Name' },
    { key:'email',            label:'Email' },
    { key:'phone',            label:'Phone' },
    { key:'consumer_city',    label:'City' },
    { key:'consumer_zone',    label:'Zone' },
    { key:'total_ebo_bills',  label:'Visits',      render:v=>v||0 },
    { key:'total_ebo_spend',  label:'EBO Spend',   render:v=>fmt(v) },
    { key:'ebo_days_since_last', label:'Days Silent', render:v=>v?`${v}d`:'—' },
    { key:'primary_store',    label:'Store' },
    { key:'top_category',     label:'Category' },
    { key:'rfm_segment',      label:'Segment',     render:v=><SegBadge segment={v}/> },
    { key:'churn_risk',       label:'Churn',       render:v=><ChurnBadge risk={v}/> },
  ],
  online_never_offline: [
    { key:'consumer_name',       label:'Name' },
    { key:'email',               label:'Email' },
    { key:'phone',               label:'Phone' },
    { key:'consumer_city',       label:'City' },
    { key:'consumer_zone',       label:'Zone' },
    { key:'total_online_orders', label:'Orders',      render:v=>v||0 },
    { key:'total_online_spend',  label:'Online Spend',render:v=>fmt(v) },
    { key:'top_category',        label:'Category' },
    { key:'cod_pct',             label:'COD%',        render:v=>v?`${v}%`:'—' },
    { key:'rfm_segment',         label:'Segment',     render:v=><SegBadge segment={v}/> },
    { key:'churn_risk',          label:'Churn',       render:v=><ChurnBadge risk={v}/> },
  ],
  same_month: [
    { key:'consumer_name',        label:'Name' },
    { key:'email',                label:'Email' },
    { key:'phone',                label:'Phone' },
    { key:'consumer_city',        label:'City' },
    { key:'migration_lag_days',   label:'Lag Days',    render:v=>v?`${v}d`:'0d' },
    { key:'total_ebo_spend',      label:'EBO Spend',   render:v=>fmt(v) },
    { key:'total_online_spend',   label:'Online Spend',render:v=>fmt(v) },
    { key:'total_lifetime_spend', label:'Total LTV',   render:v=>fmt(v) },
    { key:'primary_store',        label:'Store' },
    { key:'top_category',         label:'Category' },
    { key:'rfm_segment',          label:'Segment',     render:v=><SegBadge segment={v}/> },
  ],
}

function getMonthOptions() {
  const opts = [{ value: '', label: 'All Time' }]
  const now  = new Date()
  for (let i = 0; i < 24; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    opts.push({
      value: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`,
      label: d.toLocaleString('en-IN', { month: 'short', year: 'numeric' }),
    })
  }
  return opts
}
const MONTH_OPTIONS = getMonthOptions()

// The 6 KPI cards — each maps to a summary count + an export pattern
const KPI_CARDS = [
  { key: 'ebo_first_never_back',       label: 'EBO First → Never Back',       color: 'var(--amber)'  },
  { key: 'online_only_never_offline',  label: 'Online Only (Never In-Store)', color: 'var(--accent)' },
  { key: 'ebo_first_moved_online',     label: 'EBO → Moved Online',           color: 'var(--green)'  },
  { key: 'online_first_moved_offline', label: 'Online → Moved Offline',       color: 'var(--teal)'   },
  { key: 'same_month_both',            label: 'Same Month Both Channels',     color: 'var(--purple)' },
]

export default function MigrationPage() {
  const [summary,     setSummary]     = useState(null)
  const [activeTab,   setActiveTab]   = useState('ebo_never_back')
  const [tabData,     setTabData]     = useState({})
  const [tabLoading,  setTabLoading]  = useState({})
  const [month,       setMonth]       = useState('')   // '' = all time — drives the KPI cards
  const [summLoading, setSummLoading] = useState(true)

  const monthLabel = MONTH_OPTIONS.find(o => o.value === month)?.label || 'All Time'

  // Summary cards — reload whenever the selected month changes
  useEffect(() => {
    setSummLoading(true)
    const url = '/api/cohorts/channel-migration/summary' + (month ? `?month=${month}` : '')
    fetch(url)
      .then(r => r.json())
      .then(setSummary)
      .catch(e => console.error('Summary failed:', e))
      .finally(() => setSummLoading(false))
  }, [month])

  const cardExportUrl = (key) =>
    `/api/cohorts/channel-migration/export-pattern?pattern=${key}${month ? `&month=${month}` : ''}`

  // Load tab data
  const loadTab = async (key) => {
    // Reset if already errored so user can retry
    if (tabData[key] && !tabData[key].error) return
    const pattern = PATTERNS.find(p => p.key === key)
    if (!pattern) return

    setTabLoading(t => ({ ...t, [key]: true }))
    try {
      const res = await fetch(pattern.apiPath + '?limit=500')
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      const data = await res.json()
      setTabData(t => ({ ...t, [key]: data }))
    } catch(e) {
      console.error(`Tab [${key}] failed:`, e)
      setTabData(t => ({ ...t, [key]: { count:0, customers:[], error: e.message } }))
    } finally {
      setTabLoading(t => ({ ...t, [key]: false }))
    }
  }

  useEffect(() => { loadTab(activeTab) }, [activeTab])

  const downloadCsv = (exportParam) =>
    window.open(`/api/cohorts/channel-migration/export-csv?pattern=${exportParam}&limit=10000`, '_blank')

  const currentData    = tabData[activeTab]
  const currentLoading = tabLoading[activeTab]
  const currentPattern = PATTERNS.find(p => p.key === activeTab)

  return (
    <div style={{ padding:'32px 36px', maxWidth:1400, margin:'0 auto' }}>
      <PageHeader
        title="Channel Migration Analysis"
        subtitle="Track how customers move between online and offline channels"
        action={
          <select className="input" style={{ width: 'auto', padding: '7px 12px', fontSize: 13 }}
            value={month} onChange={e => setMonth(e.target.value)} title="Filter KPI cards by month">
            {MONTH_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        }
      />

      {/* Summary cards — each downloadable, month-aware */}
      {month && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10 }}>
          Showing customers active in <strong style={{ color: 'var(--accent)' }}>{monthLabel}</strong>
        </div>
      )}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))', gap:14, marginBottom:24 }}>
        {summLoading ? Array.from({length:6}).map((_,i)=>(
          <div key={i} className="card" style={{padding:20}}>
            <div className="skeleton" style={{height:14,width:'60%',marginBottom:8}}/>
            <div className="skeleton" style={{height:26,width:'40%'}}/>
          </div>
        )) : summary && KPI_CARDS.map((c)=>(
          <div key={c.key} className="card" style={{padding:'16px 18px', position:'relative'}}>
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8, marginBottom:6}}>
              <div style={{fontSize:11,color:'var(--text-muted)',fontWeight:500, lineHeight:1.3}}>{c.label}</div>
              <a
                href={cardExportUrl(c.key)}
                title={`Download ${c.label} customers${month ? ` · ${monthLabel}` : ''}`}
                className="seg-export-btn"
                style={{ display:'inline-flex', alignItems:'center', justifyContent:'center',
                  width:26, height:26, borderRadius:7, color:'var(--text-secondary)',
                  border:'1px solid var(--border)', textDecoration:'none', flexShrink:0 }}>
                <Download size={13}/>
              </a>
            </div>
            <div style={{fontSize:22,fontWeight:800,fontFamily:'var(--font-display)',color:c.color}}>
              {fmtN(summary[c.key])}
            </div>
          </div>
        ))}
      </div>

      {/* Pattern tabs */}
      <div className="card" style={{overflow:'hidden'}}>
        {/* Tab headers */}
        <div style={{display:'flex',borderBottom:'1px solid var(--border)',background:'var(--bg-subtle)'}}>
          {PATTERNS.map(p=>(
            <button key={p.key} onClick={()=>setActiveTab(p.key)} style={{
              flex:1, padding:'14px 12px', border:'none', cursor:'pointer',
              background: activeTab===p.key ? 'var(--bg-card)' : 'transparent',
              borderBottom: activeTab===p.key ? `2px solid ${p.color}` : '2px solid transparent',
              transition:'all 0.15s',
            }}>
              <div style={{fontSize:13,fontWeight:600,color:activeTab===p.key?p.color:'var(--text-secondary)'}}>
                {p.label}
              </div>
              <div style={{fontSize:10,color:'var(--text-muted)',marginTop:2}}>{p.desc}</div>
            </button>
          ))}
        </div>

        {/* Tab body */}
        <div style={{padding:24}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:16}}>
            <div>
              <div style={{fontSize:14,fontWeight:600}}>{currentPattern?.label}</div>
              <div style={{fontSize:12,color:'var(--text-muted)',marginTop:2}}>
                {currentData && !currentData.error
                  ? `${fmtN(currentData.count)} customers · ${currentPattern?.desc}`
                  : currentPattern?.desc}
              </div>
            </div>
            {currentData && !currentData.error && currentData.count > 0 && (
              <button className="btn-primary"
                onClick={()=>downloadCsv(currentPattern.exportParam)}
                style={{display:'flex',alignItems:'center',gap:6,fontSize:12}}>
                <Download size={13}/> Export {fmtN(currentData.count)} customers
              </button>
            )}
          </div>

          {/* Loading */}
          {currentLoading && <CardSkeleton rows={6}/>}

          {/* Error */}
          {!currentLoading && currentData?.error && (
            <div style={{background:'var(--red-light)',borderRadius:8,padding:'12px 16px'}}>
              <div style={{fontSize:12,fontWeight:600,color:'var(--red)',marginBottom:4}}>Failed to load</div>
              <div style={{fontSize:11,color:'var(--red)',fontFamily:'var(--font-mono)'}}>{currentData.error}</div>
              <button className="btn-ghost" style={{marginTop:8,fontSize:12}}
                onClick={()=>{ setTabData(t=>({...t,[activeTab]:null})); loadTab(activeTab) }}>
                Retry
              </button>
            </div>
          )}

          {/* Empty */}
          {!currentLoading && !currentLoading && currentData && !currentData.error && currentData.count===0 && (
            <Empty icon={Users} title="No customers found for this pattern" sub=""/>
          )}

          {/* Not loaded yet */}
          {!currentLoading && !currentData && (
            <Empty icon={Users} title="Loading..." sub=""/>
          )}

          {/* Table */}
          {!currentLoading && currentData && !currentData.error && currentData.customers?.length > 0 && (
            <Table columns={COLS_MAP[activeTab]||[]} rows={currentData.customers}/>
          )}
        </div>
      </div>
    </div>
  )
}
