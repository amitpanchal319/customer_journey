'use client'
import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LabelList } from 'recharts'
import { Download, Calendar } from 'lucide-react'
import { api } from '../../lib/api'
import { PageHeader, CardSkeleton, Table, Empty } from '../../components/UI'

function fmt(n)  { if(!n&&n!==0) return '—'; if(n>=10000000) return `₹${(n/10000000).toFixed(1)}Cr`; if(n>=100000) return `₹${(n/100000).toFixed(1)}L`; if(n>=1000) return `₹${(n/1000).toFixed(1)}K`; return `₹${n}` }
function fmtN(n) { if(!n&&n!==0) return '—'; if(n>=10000000) return `${(n/10000000).toFixed(1)}Cr`; if(n>=100000) return `${(n/100000).toFixed(1)}L`; if(n>=1000) return `${(n/1000).toFixed(1)}K`; return `${n}` }

const CHANNEL = 'Online Only'

function getMonthOptions() {
  const opts = [{ value:'', label:'All Time' }]
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

export default function OnlinePage() {
  const [freq,        setFreq]        = useState([])
  const [aov,         setAov]         = useState([])
  const [cat,         setCat]         = useState([])
  const [loading,     setLoading]     = useState(true)
  const [month,       setMonth]       = useState('')

  const monthLabel = MONTH_OPTIONS.find(o => o.value === month)?.label || 'All Time'

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const monthParam = month ? { month } : {}
    Promise.all([
      api.getFrequency({ channel_journey: CHANNEL, ...monthParam }),
      api.getAOVComparison({ channel_journey: CHANNEL, ...monthParam }),
      api.getCategory({ channel: CHANNEL, ...monthParam }),
    ]).then(([f, a, c]) => {
      if (cancelled) return
      setFreq(f || [])
      setAov(a || [])
      setCat((c || []).sort((x,y) => y.customers - x.customers))
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [month])

  const handleMonthChange = (m) => setMonth(m)

  return (
    <div style={{ padding:'32px 36px', maxWidth:1400, margin:'0 auto' }}>
      <PageHeader
        title="Online Customers (Shopify)"
        subtitle="Customers who purchased only via Shopify — never visited a store"
        action={
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <div style={{ display:'flex', alignItems:'center', gap:6 }}>
              <Calendar size={13} style={{ color:'var(--text-muted)' }}/>
              <select className="input" style={{ width:'auto', padding:'6px 12px', fontSize:12 }}
                value={month} onChange={e => handleMonthChange(e.target.value)}>
                {MONTH_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              {month && (
                <button className="btn-ghost" style={{ fontSize:11, padding:'4px 8px' }}
                  onClick={() => handleMonthChange('')}>✕ Clear</button>
              )}
            </div>
          </div>
        }
      />

      {month && (
        <div style={{ background:'var(--accent-light)', border:'1px solid var(--accent)',
          borderRadius:8, padding:'10px 16px', marginBottom:20, fontSize:13,
          color:'var(--accent)', display:'flex', alignItems:'center', gap:8 }}>
          <Calendar size={14}/>
          <span>Showing customers active in <strong>{monthLabel}</strong> — all charts updated</span>
        </div>
      )}

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20, marginBottom:20 }}>

        {/* AOV — Online only */}
        <div className="card" style={{ padding:24 }}>
          <div style={{ fontSize:14, fontWeight:600, marginBottom:4 }}>Online AOV — New vs Repeat{month ? ` · ${monthLabel}` : ''}</div>
          <div style={{ fontSize:12, color:'var(--text-muted)', marginBottom:16 }}>
            Average Shopify order value by customer type
          </div>
          {loading ? <CardSkeleton rows={4}/> : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={aov}>
                <XAxis dataKey="customer_type" tick={{fontSize:12,fill:'var(--text-muted)'}}
                  axisLine={false} tickLine={false}/>
                <YAxis tick={{fontSize:11,fill:'var(--text-muted)'}} axisLine={false} tickLine={false}
                  tickFormatter={v=>`₹${v}`}/>
                <Tooltip contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',
                  borderRadius:8,fontSize:12}} formatter={v=>[`₹${v}`,'Online AOV']}/>
                <Bar dataKey="avg_online_aov" name="Online AOV" fill="var(--accent)" radius={[4,4,0,0]}>
                  <LabelList dataKey="avg_online_aov" position="top"
                    formatter={v=>`₹${v}`} style={{fontSize:11,fill:'var(--text-muted)'}}/>
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Purchase Frequency */}
        <div className="card" style={{ padding:24 }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8, marginBottom:4 }}>
            <div style={{ fontSize:14, fontWeight:600 }}>Purchase Frequency{month ? ` · ${monthLabel}` : ''}</div>
            <a
              href={api.getFrequencyExportUrl({ channel_journey: CHANNEL, month })}
              title={`Download purchase frequency CSV${month ? ` · ${monthLabel}` : ''}`}
              className="seg-export-btn"
              style={{ display:'inline-flex', alignItems:'center', justifyContent:'center',
                width:30, height:30, borderRadius:8, color:'var(--text-secondary)',
                border:'1px solid var(--border)', textDecoration:'none', flexShrink:0 }}>
              <Download size={15}/>
            </a>
          </div>
          <div style={{ fontSize:12, color:'var(--text-muted)', marginBottom:16 }}>
            How many times online customers have ordered
          </div>
          {loading ? <CardSkeleton rows={4}/> : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={freq} layout="vertical">
                <XAxis type="number" tick={{fontSize:11,fill:'var(--text-muted)'}}
                  axisLine={false} tickLine={false} tickFormatter={fmtN}/>
                <YAxis type="category" dataKey="frequency_bucket" width={90}
                  tick={{fontSize:11,fill:'var(--text-muted)'}} axisLine={false} tickLine={false}/>
                <Tooltip contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',
                  borderRadius:8,fontSize:12}}/>
                <Bar dataKey="customers" name="Customers" fill="var(--accent)" radius={[0,4,4,0]}>
                  <LabelList dataKey="customers" position="right" formatter={fmtN}
                    style={{fontSize:11,fill:'var(--text-muted)'}}/>
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Category breakdown */}
      <div className="card" style={{ padding:24 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
          <div>
            <div style={{ fontSize:14, fontWeight:600 }}>Category Breakdown{month ? ` · ${monthLabel}` : ''}</div>
            <div style={{ fontSize:12, color:'var(--text-muted)', marginTop:2 }}>
              All categories · sorted by customers descending
            </div>
          </div>
        </div>
        {loading ? <CardSkeleton rows={8}/> :
         cat.length === 0 ? (
          <Empty title="No category data" sub="item_master join may have no matches"/>
         ) : (
          <Table
            columns={[
              { key:'top_category',         label:'Category' },
              { key:'customers',            label:'Customers',     render:v=>fmtN(v) },
              { key:'repeat_customers',     label:'Repeat',        render:v=>fmtN(v) },
              { key:'repeat_rate_pct',      label:'Repeat Rate',   render:v=>v?`${v}%`:'—' },
              { key:'single_cat_customers', label:'Category Only', render:v=>fmtN(v) },
              { key:'avg_ltv',              label:'Avg LTV',       render:v=>fmt(v) },
              { key:'__csv', label:'',
                render:(_,row) => (
                  <button className="btn-ghost"
                    style={{ fontSize:11, padding:'3px 8px', display:'flex', alignItems:'center', gap:3 }}
                    onClick={() => window.open(api.getExportUrl({
                      channel_journey: CHANNEL,
                      top_category   : row.top_category,
                    }), '_blank')}>
                    <Download size={10}/> CSV
                  </button>
                )
              },
            ]}
            rows={cat}
          />
        )}
      </div>
    </div>
  )
}
