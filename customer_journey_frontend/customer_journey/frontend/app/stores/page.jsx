'use client'
import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts'
import { ArrowLeft, Download, Users, Store, AlertTriangle, TrendingUp, ArrowLeftRight } from 'lucide-react'
import { api } from '../../lib/api'
import EBOAgent from '../../components/EBOAgent'
import { PageHeader, CardSkeleton, Table, SegBadge, ChurnBadge, Empty } from '../../components/UI'

function fmt(n)  { if(!n&&n!==0) return '—'; if(n>=10000000) return `₹${(n/10000000).toFixed(1)}Cr`; if(n>=100000) return `₹${(n/100000).toFixed(1)}L`; if(n>=1000) return `₹${(n/1000).toFixed(1)}K`; return `₹${n}` }
function fmtN(n) { if(!n&&n!==0) return '—'; if(n>=100000) return `${(n/100000).toFixed(1)}L`; if(n>=1000) return `${(n/1000).toFixed(1)}K`; return `${n}` }

// Generate last 24 month options
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

const RFM_COLORS = {
  Champion:'#f59e0b',Loyal:'#22c55e','New Customer':'#3b82f6',
  Promising:'#8b5cf6','Need Attention':'#f97316','At Risk':'#ef4444',
  'Cannot Lose':'#ec4899',Lost:'#9ca3af',Occasional:'#14b8a6'
}
const ZONES = ['NORTH','SOUTH','EAST','WEST','CENTRAL']


// ── Store Comparison Page ──────────────────────────────────────────────────
function CompareStorePage({ data, names, onBack }) {
  const metrics = [
    { key:'total_customers',     label:'Total Customers',  fmt:fmtN },
    { key:'repeat_customer_pct', label:'Repeat %',         fmt:v=>v?`${v}%`:'—' },
    { key:'avg_customer_ltv',    label:'Avg LTV',          fmt:fmt },
    { key:'retention_30d_pct',   label:'Retention 30d',    fmt:v=>v?`${v}%`:'—' },
    { key:'retention_90d_pct',   label:'Retention 90d',    fmt:v=>v?`${v}%`:'—' },
    { key:'champion_count',      label:'Champions',        fmt:fmtN },
    { key:'high_churn_count',    label:'High Churn',       fmt:fmtN },
    { key:'migrated_to_online',  label:'Went Online',      fmt:fmtN },
    { key:'top_category_at_store',label:'Top Category',    fmt:v=>v||'—' },
    { key:'primary_customer_zone',label:'Primary Zone',    fmt:v=>v||'—' },
  ]

  const COLS = ['var(--accent)','var(--green)','var(--amber)']

  return (
    <div style={{ padding:'32px 36px', maxWidth:1200, margin:'0 auto' }}>
      <button className="btn-ghost" onClick={onBack}
        style={{ display:'flex', alignItems:'center', gap:6, marginBottom:20, fontSize:13 }}>
        <ArrowLeft size={13}/> All Stores
      </button>
      <PageHeader title="Store Comparison" subtitle={`Comparing ${names.join(' vs ')}`}/>
      <div className="card" style={{ overflow:'hidden' }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:13 }}>
          <thead>
            <tr style={{ background:'var(--bg-subtle)' }}>
              <th style={{ padding:'12px 16px', textAlign:'left', fontSize:11,
                fontWeight:600, color:'var(--text-muted)', textTransform:'uppercase',
                letterSpacing:'0.06em', width:180 }}>Metric</th>
              {(data||[]).map((s,i) => (
                <th key={i} style={{ padding:'12px 16px', textAlign:'center', fontSize:13,
                  fontWeight:700, color:COLS[i], borderLeft:'1px solid var(--border)' }}>
                  {s.store_name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.map((m,i) => {
              const values = (data||[]).map(s => s[m.key])
              const nums   = values.map(v => parseFloat(v)||0)
              const maxVal = Math.max(...nums)
              return (
                <tr key={i} style={{ borderTop:'1px solid var(--border)',
                  background: i%2===0 ? 'transparent' : 'var(--bg-subtle)' }}>
                  <td style={{ padding:'11px 16px', color:'var(--text-secondary)',
                    fontWeight:500, fontSize:12 }}>{m.label}</td>
                  {(data||[]).map((s,j) => {
                    const raw = s[m.key]
                    const num = parseFloat(raw)||0
                    const isMax = num === maxVal && maxVal > 0
                    return (
                      <td key={j} style={{ padding:'11px 16px', textAlign:'center',
                        borderLeft:'1px solid var(--border)',
                        fontWeight: isMax ? 700 : 400,
                        color: isMax ? COLS[j] : 'var(--text-primary)' }}>
                        {m.fmt(raw)}
                        {isMax && nums.filter(n=>n===maxVal).length===1 &&
                          <span style={{ marginLeft:4, fontSize:10 }}>★</span>}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div style={{ fontSize:11, color:'var(--text-muted)', textAlign:'center', marginTop:10 }}>
        ★ = highest value for that metric
      </div>
    </div>
  )
}

// ── Multi-Store Customers Page ─────────────────────────────────────────────
function MultiStorePage({ onBack }) {
  const [zone,     setZone]     = useState('')
  const [minStores,setMinStores]= useState(2)
  const [data,     setData]     = useState(null)
  const [loading,  setLoading]  = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const d = await api.getMultiStoreCustomers(zone, minStores)
      setData(d)
    } catch(e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [zone, minStores])

  const download = () => {
    const params = new URLSearchParams({ min_stores: minStores })
    if (zone) params.append('zone', zone)
    window.open(`/api/stores/multi-store-customers/export-csv?${params}`, '_blank')
  }

  return (
    <div style={{ padding:'32px 36px', maxWidth:1400, margin:'0 auto' }}>
      <button className="btn-ghost" onClick={onBack}
        style={{ display:'flex', alignItems:'center', gap:6, marginBottom:20, fontSize:13 }}>
        <ArrowLeft size={13}/> All Stores
      </button>
      <PageHeader
        title="Multi-Store Customers"
        subtitle="Customers who visited more than one EBO store — your most loyal offline shoppers"
      />

      {/* Filters */}
      <div className="card" style={{ padding:'16px 20px', marginBottom:20,
        display:'flex', gap:14, alignItems:'flex-end', flexWrap:'wrap' }}>
        <div>
          <label style={{ display:'block', fontSize:11, fontWeight:600, color:'var(--text-muted)',
            marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }}>Zone</label>
          <select className="input" style={{ width:'auto', padding:'7px 12px', fontSize:12 }}
            value={zone} onChange={e => setZone(e.target.value)}>
            <option value="">All Zones</option>
            {ZONES.map(z => <option key={z} value={z}>{z}</option>)}
          </select>
        </div>
        <div>
          <label style={{ display:'block', fontSize:11, fontWeight:600, color:'var(--text-muted)',
            marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }}>Min Stores</label>
          <select className="input" style={{ width:'auto', padding:'7px 12px', fontSize:12 }}
            value={minStores} onChange={e => setMinStores(+e.target.value)}>
            {[2,3,4,5].map(n => <option key={n} value={n}>{n}+ stores</option>)}
          </select>
        </div>
        {data && data.total > 0 && (
          <button className="btn-primary" onClick={download}
            style={{ display:'flex', alignItems:'center', gap:6, fontSize:12 }}>
            <Download size={13}/> Export {fmtN(data.total)} customers
          </button>
        )}
      </div>

      {/* Zone summary */}
      {data && data.zone_summary?.length > 0 && (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(160px,1fr))',
          gap:12, marginBottom:20 }}>
          {data.zone_summary.map((z,i) => (
            <div key={i} className="card" style={{ padding:'14px 16px', cursor:'pointer',
              borderColor: zone===z.zone ? 'var(--accent)' : 'var(--border)' }}
              onClick={() => setZone(zone===z.zone ? '' : z.zone)}>
              <div style={{ fontSize:11, color:'var(--text-muted)', fontWeight:600,
                textTransform:'uppercase', marginBottom:5 }}>{z.zone}</div>
              <div style={{ fontSize:20, fontWeight:800, fontFamily:'var(--font-display)',
                color:'var(--accent)' }}>{fmtN(z.multi_store_customers)}</div>
              <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:3 }}>
                avg {z.avg_stores_visited} stores · LTV {fmt(z.avg_ltv)}
              </div>
            </div>
          ))}
        </div>
      )}

      {loading && <CardSkeleton rows={6}/>}
      {!loading && !data && <Empty icon={Users} title='No data found' sub='Try different filters'/>}
      {!loading && data && data.total === 0 && <Empty icon={Users} title='No multi-store customers found' sub='Try reducing min stores filter'/>}
      {!loading && data && data.total > 0 && (
        <div className="card" style={{ padding:24 }}>
          <div style={{ fontSize:14, fontWeight:600, marginBottom:4 }}>
            {fmtN(data.total)} customers visited {minStores}+ stores
            {zone && ` in ${zone} zone`}
          </div>
          <div style={{ fontSize:12, color:'var(--text-muted)', marginBottom:16 }}>
            Sorted by number of stores visited — most loyal offline customers first
          </div>
          <Table
            columns={[
              { key:'consumer_name',   label:'Name' },
              { key:'email',           label:'Email' },
              { key:'phone',           label:'Phone' },
              { key:'consumer_city',   label:'City' },
              { key:'consumer_zone',   label:'Zone' },
              { key:'stores_visited',  label:'Stores',     render:v=><strong style={{color:'var(--accent)'}}>{v}</strong> },
              { key:'stores_list',     label:'Store Names', render:v=>v ? v.substring(0,40)+(v.length>40?'...':'') : '—' },
              { key:'total_bills',     label:'Total Bills', render:v=>v||0 },
              { key:'total_ebo_spend', label:'EBO Spend',  render:v=>fmt(v) },
              { key:'total_lifetime_spend', label:'Total LTV', render:v=>fmt(v) },
              { key:'rfm_segment',     label:'Segment',    render:v=><SegBadge segment={v}/> },
              { key:'top_category',    label:'Category',   render:v=>v||'—' },
              { key:'channel_journey', label:'Channel',    render:v=>v||'—' },
            ]}
            rows={data.customers}
          />
        </div>
      )}
    </div>
  )
}

// ── Store Detail Page ──────────────────────────────────────────────────────
function StoreDetailPage({ store, onBack }) {
  const [detail,  setDetail]  = useState(null)
  const [mom,     setMom]     = useState([])
  const [months,  setMonths]  = useState('')  // empty = last 24 months
  const [loading, setLoading] = useState(true)
  const [tab,     setTab]     = useState('overview') // overview|rfm|categories|cannot_lose|customers

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.getStoreDetail(store.store_name),
      api.getStoreMoM(store.store_name, months),
    ]).then(([d, m]) => {
      setDetail(d)
      setMom(m)
    }).finally(() => setLoading(false))
  }, [store.store_name, months])

  const download = (segment='') => {
    window.open(api.getStoreExportUrl(store.store_name, segment), '_blank')
  }

  if (loading) return (
    <div style={{ padding:'32px 36px', maxWidth:1400, margin:'0 auto' }}>
      <button className="btn-ghost" onClick={onBack} style={{ marginBottom:20, fontSize:13 }}>
        <ArrowLeft size={13}/> All Stores
      </button>
      <CardSkeleton rows={8}/>
    </div>
  )

  const d = detail

  return (
    <div style={{ padding:'32px 36px', maxWidth:1400, margin:'0 auto' }}>
      <button className="btn-ghost" onClick={onBack}
        style={{ display:'flex', alignItems:'center', gap:6, marginBottom:20, fontSize:13 }}>
        <ArrowLeft size={13}/> All Stores
      </button>

      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:24 }}>
        <div>
          <h1 style={{ fontFamily:'var(--font-display)', fontSize:24, fontWeight:800, letterSpacing:'-0.02em' }}>
            {store.store_name}
          </h1>
          <div style={{ fontSize:13, color:'var(--text-secondary)', marginTop:4 }}>
            {fmtN(d?.store?.total_customers)} total customers · {d?.store?.primary_customer_zone || '—'} zone
          </div>
        </div>
        <button className="btn-primary" onClick={() => download()}
          style={{ display:'flex', alignItems:'center', gap:6, fontSize:12 }}>
          <Download size={13}/> Export All Customers
        </button>
      </div>

      {/* KPI cards — each downloadable */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(160px,1fr))',
        gap:12, marginBottom:20 }}>
        {[
          { label:'Total Customers',   value:fmtN(d?.store?.total_customers),        color:'var(--accent)',  metric:'all'          },
          { label:'Repeat Rate',       value:`${d?.store?.repeat_customer_pct||0}%`, color:'var(--green)',   metric:'repeat'       },
          { label:'Avg LTV',           value:fmt(d?.store?.avg_customer_ltv),        color:'var(--amber)',   metric:'all'          },
          { label:'Retention 30d',     value:`${d?.store?.retention_30d_pct||0}%`,   color:'var(--teal)',    metric:'retained_30d' },
          { label:'Went Online',       value:fmtN(d?.store?.migrated_to_online),     color:'var(--purple)',  metric:'went_online'  },
          { label:'High Churn',        value:fmtN(d?.store?.high_churn_count),       color:'var(--red)',     metric:'high_churn'   },
        ].map((s,i) => (
          <div key={i} className="card" style={{ padding:'14px 16px' }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8, marginBottom:5 }}>
              <div style={{ fontSize:11, color:'var(--text-muted)', fontWeight:500 }}>{s.label}</div>
              <a
                href={api.getStoreMetricExportUrl(store.store_name, s.metric)}
                title={`Download ${s.label} customers (with contact details)`}
                className="seg-export-btn"
                style={{ display:'inline-flex', alignItems:'center', justifyContent:'center',
                  width:24, height:24, borderRadius:6, color:'var(--text-secondary)',
                  border:'1px solid var(--border)', textDecoration:'none', flexShrink:0 }}>
                <Download size={12}/>
              </a>
            </div>
            <div style={{ fontSize:20, fontWeight:800, fontFamily:'var(--font-display)', color:s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* MoM Chart */}
      <div className="card" style={{ padding:24, marginBottom:20 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
          <div style={{ fontSize:14, fontWeight:600 }}>Month-on-Month Performance</div>
          <select className="input" style={{ width:'auto', padding:'6px 10px', fontSize:12 }}
            value={months} onChange={e => setMonths(e.target.value)}>
            <option value="">Last 24 months</option>
            {MONTH_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={mom}>
            <XAxis dataKey="month_label" tick={{fontSize:11,fill:'var(--text-muted)'}} axisLine={false} tickLine={false}/>
            <YAxis tick={{fontSize:11,fill:'var(--text-muted)'}} axisLine={false} tickLine={false} tickFormatter={fmtN}/>
            <Tooltip contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:8,fontSize:12}}/>
            <Bar dataKey="new_customers"    name="New"    fill="var(--accent)" radius={[3,3,0,0]} stackId="a"/>
            <Bar dataKey="repeat_customers" name="Repeat" fill="var(--green)"  radius={[3,3,0,0]} stackId="a"/>
          </BarChart>
        </ResponsiveContainer>
        <div style={{ display:'flex', gap:12, marginTop:8 }}>
          {[['New','var(--accent)'],['Repeat','var(--green)']].map(([l,c]) => (
            <div key={l} style={{ display:'flex', alignItems:'center', gap:5, fontSize:11 }}>
              <div style={{ width:10, height:10, borderRadius:2, background:c }}/>
              <span style={{ color:'var(--text-secondary)' }}>{l}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="card" style={{ overflow:'hidden' }}>
        <div style={{ display:'flex', borderBottom:'1px solid var(--border)',
          background:'var(--bg-subtle)', overflowX:'auto' }}>
          {[
            { key:'rfm',         label:'RFM Segments'  },
            { key:'categories',  label:'Categories'    },
            { key:'sizes',       label:'Sizes'         },
            { key:'cannot_lose', label:`Alerts (${d?.cannot_lose?.length||0})` },
            { key:'migration',   label:'Migration'     },
            { key:'customers',   label:'Top Customers' },
          ].map(t => (
            <button key={t.key} onClick={() => setTab(t.key)} style={{
              padding:'12px 16px', border:'none', cursor:'pointer', whiteSpace:'nowrap',
              background: tab===t.key ? 'var(--bg-card)' : 'transparent',
              borderBottom: tab===t.key ? '2px solid var(--accent)' : '2px solid transparent',
              fontSize:12, fontWeight: tab===t.key ? 600 : 400,
              color: tab===t.key ? 'var(--accent)' : 'var(--text-secondary)',
              transition:'all 0.15s',
            }}>
              {t.label}
            </button>
          ))}
        </div>

        <div style={{ padding:24 }}>
          {/* RFM Tab */}
          {tab === 'rfm' && (
            <div>
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:16 }}>
                <div style={{ fontSize:14, fontWeight:600 }}>RFM Segments at {store.store_name}</div>
              </div>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(140px,1fr))', gap:10, marginBottom:20 }}>
                {(d?.rfm||[]).map((r,i) => (
                  <div key={i} className="card" style={{ padding:'12px 14px', cursor:'pointer' }}
                    onClick={() => download(r.rfm_segment)}>
                    <div style={{ marginBottom:6 }}><SegBadge segment={r.rfm_segment}/></div>
                    <div style={{ fontSize:18, fontWeight:800, fontFamily:'var(--font-display)' }}>{fmtN(r.customers)}</div>
                    <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:3 }}>
                      {r.pct}% · avg {fmt(r.avg_ltv)}
                    </div>
                    <div style={{ fontSize:10, color:'var(--accent)', marginTop:4 }}>↓ Export</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Categories Tab */}
          {tab === 'categories' && (
            <div>
              <div style={{ fontSize:14, fontWeight:600, marginBottom:16 }}>Top Categories at {store.store_name}</div>
              <Table
                columns={[
                  { key:'category',  label:'Category' },
                  { key:'customers', label:'Customers', render:v=>fmtN(v) },
                  { key:'revenue',   label:'Revenue',   render:v=>fmt(v) },
                  { key:'avg_bill',  label:'Avg Bill',  render:v=>fmt(v) },
                ]}
                rows={d?.categories||[]}
              />
            </div>
          )}

          {/* Sizes Tab */}
          {tab === 'sizes' && (
            <div>
              <div style={{ fontSize:14, fontWeight:600, marginBottom:16 }}>Top Sizes at {store.store_name}</div>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(120px,1fr))', gap:10 }}>
                {(d?.sizes||[]).map((s,i) => (
                  <div key={i} className="card" style={{ padding:'14px 16px', textAlign:'center' }}>
                    <div style={{ fontSize:20, fontWeight:800, fontFamily:'var(--font-display)',
                      color:'var(--purple)', marginBottom:4 }}>{s.size}</div>
                    <div style={{ fontSize:12, color:'var(--text-secondary)' }}>{fmtN(s.qty_sold)} sold</div>
                    <div style={{ fontSize:11, color:'var(--text-muted)' }}>{fmtN(s.customers)} cx</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Cannot Lose Tab */}
          {tab === 'cannot_lose' && (
            <div>
              <div style={{ display:'flex', justifyContent:'space-between', marginBottom:16 }}>
                <div>
                  <div style={{ fontSize:14, fontWeight:600, color:'var(--red)' }}>
                    High Value Customers — Action Required
                  </div>
                  <div style={{ fontSize:12, color:'var(--text-muted)', marginTop:3 }}>
                    Champions, Cannot Lose and At Risk customers who haven't visited in 90+ days
                  </div>
                </div>
                <button className="btn-primary" onClick={() => download('Cannot Lose')}
                  style={{ fontSize:12, display:'flex', alignItems:'center', gap:5 }}>
                  <Download size={12}/> Export
                </button>
              </div>
              {d?.cannot_lose?.length === 0 ? (
                <Empty icon={AlertTriangle} title="No critical alerts" sub="All high-value customers are active ✓"/>
              ) : (
                <Table
                  columns={[
                    { key:'consumer_name',      label:'Name' },
                    { key:'email',              label:'Email' },
                    { key:'phone',              label:'Phone' },
                    { key:'consumer_city',      label:'City' },
                    { key:'total_lifetime_spend',label:'LTV',      render:v=>fmt(v) },
                    { key:'total_ebo_bills',    label:'Visits',   render:v=>v||0 },
                    { key:'ebo_days_since_last',label:'Days Silent',render:v=><span style={{color:'var(--red)',fontWeight:600}}>{v}d</span> },
                    { key:'top_category',       label:'Category', render:v=>v||'—' },
                    { key:'rfm_segment',        label:'Segment',  render:v=><SegBadge segment={v}/> },
                  ]}
                  rows={d?.cannot_lose||[]}
                />
              )}
            </div>
          )}

          {/* Migration Tab */}
          {tab === 'migration' && (
            <div>
              <div style={{ fontSize:14, fontWeight:600, marginBottom:16 }}>Channel Migration at {store.store_name}</div>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(160px,1fr))', gap:12, marginBottom:20 }}>
                {(d?.migration||[]).map((m,i) => (
                  <div key={i} className="card" style={{ padding:'14px 16px' }}>
                    <div style={{ fontSize:11, color:'var(--text-muted)', marginBottom:5 }}>{m.migration_type||'Unknown'}</div>
                    <div style={{ fontSize:20, fontWeight:800, fontFamily:'var(--font-display)', color:'var(--accent)' }}>
                      {fmtN(m.customers)}
                    </div>
                    <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:3 }}>avg LTV {fmt(m.avg_ltv)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Customers Tab */}
          {tab === 'customers' && (
            <div>
              <div style={{ fontSize:14, fontWeight:600, marginBottom:16 }}>
                Top Customers — {store.store_name}
              </div>
              <Table
                columns={[
                  { key:'consumer_name',        label:'Name' },
                  { key:'email',                label:'Email' },
                  { key:'phone',                label:'Phone' },
                  { key:'consumer_city',        label:'City' },
                  { key:'total_ebo_bills',      label:'Visits',    render:v=>v||0 },
                  { key:'total_ebo_spend',      label:'EBO Spend', render:v=>fmt(v) },
                  { key:'total_lifetime_spend', label:'Total LTV', render:v=>fmt(v) },
                  { key:'top_category',         label:'Category',  render:v=>v||'—' },
                  { key:'rfm_segment',          label:'Segment',   render:v=><SegBadge segment={v}/> },
                  { key:'churn_risk',           label:'Churn',     render:v=><ChurnBadge risk={v}/> },
                  { key:'migration_type',       label:'Migration', render:v=>v||'—' },
                ]}
                rows={d?.customers||[]}
              />
            </div>
          )}
        </div>
      </div>
      {/* EBO Agent — scoped to this store */}
      <EBOAgent storeName={store.store_name} />
    </div>
  )
}

// ── Main Stores Page ───────────────────────────────────────────────────────
export default function StoresPage() {
  const [stores,   setStores]   = useState([])
  const [loading,  setLoading]  = useState(true)
  const [selected, setSelected] = useState(null)
  const [showMulti,setShowMulti]= useState(false)
  const [compare,  setCompare]  = useState([])

  useEffect(() => {
    api.getStores().then(d => setStores(d||[])).finally(() => setLoading(false))
  }, [])

  if (showMulti) return <MultiStorePage onBack={() => setShowMulti(false)}/>
  if (selected?.store_name === '__compare__') return <CompareStorePage data={selected.compareData} names={selected.compareNames} onBack={() => setSelected(null)}/>
  if (selected)  return <StoreDetailPage store={selected} onBack={() => setSelected(null)}/>

  return (
    <div style={{ padding:'32px 36px', maxWidth:1400, margin:'0 auto' }}>
      <PageHeader
        title="Store Intelligence"
        subtitle="EBO store-wise performance, repeat customers, retention and revenue"
        action={
          <button className="btn-ghost" onClick={() => setShowMulti(true)}
            style={{ display:'flex', alignItems:'center', gap:6, fontSize:13 }}>
            <ArrowLeftRight size={13}/> Multi-Store Customers
          </button>
        }
      />

      {loading ? <CardSkeleton rows={8}/> : (
        <>
          {/* Top stores bar chart */}
          <div className="card" style={{ padding:24, marginBottom:20 }}>
            <div style={{ fontSize:14, fontWeight:600, marginBottom:16 }}>Top 10 Stores by Customers</div>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={stores.slice(0,10)} layout="vertical"
                onClick={d => d?.activePayload && setSelected(d.activePayload[0].payload)}>
                <XAxis type="number" tick={{fontSize:11,fill:'var(--text-muted)'}} axisLine={false} tickLine={false} tickFormatter={fmtN}/>
                <YAxis type="category" dataKey="store_name" tick={{fontSize:11,fill:'var(--text-muted)'}} axisLine={false} tickLine={false} width={160}/>
                <Tooltip contentStyle={{background:'var(--bg-card)',border:'1px solid var(--border)',borderRadius:8,fontSize:12}}/>
                <Bar dataKey="total_customers" name="Customers" fill="var(--accent)" radius={[0,4,4,0]} cursor="pointer"/>
              </BarChart>
            </ResponsiveContainer>
            <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:8, textAlign:'center' }}>
              Click any bar to open store detail
            </div>
          </div>

          {/* Stores table */}
          <div className="card" style={{ padding:24 }}>
            {compare.length > 0 && (
              <div style={{ marginBottom:16, padding:'10px 14px', background:'var(--accent-light)',
                borderRadius:8, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                <span style={{ fontSize:13, color:'var(--accent)', fontWeight:600 }}>
                  {compare.length} store{compare.length>1?'s':''} selected for comparison
                </span>
                <div style={{ display:'flex', gap:8 }}>
                  <button className="btn-primary" style={{ fontSize:12 }}
                    onClick={async () => {
                      const names = compare.join(',')
                      const d = await api.getStoreCompare(names)
                      setSelected({ store_name: '__compare__', compareData: d, compareNames: compare })
                    }}>
                    Compare Stores
                  </button>
                  <button className="btn-ghost" style={{ fontSize:12 }}
                    onClick={() => setCompare([])}>Clear</button>
                </div>
              </div>
            )}
            <Table
              columns={[
                { key:'__compare', label:'',
                  render:(_, row) => (
                    <input type="checkbox"
                      checked={compare.includes(row.store_name)}
                      onChange={e => {
                        e.stopPropagation()
                        setCompare(prev =>
                          prev.includes(row.store_name)
                            ? prev.filter(s => s !== row.store_name)
                            : prev.length < 3 ? [...prev, row.store_name] : prev
                        )
                      }}
                      onClick={e => e.stopPropagation()}
                      style={{ cursor:'pointer', width:14, height:14 }}
                    />
                  )
                },
                { key:'store_name',          label:'Store' },
                { key:'total_customers',     label:'Customers',    render:v=>fmtN(v) },
                { key:'repeat_customer_pct', label:'Repeat %',     render:v=>v?`${v}%`:'—' },
                { key:'retention_30d_pct',   label:'Ret. 30d',     render:v=>v?`${v}%`:'—' },
                { key:'retention_90d_pct',   label:'Ret. 90d',     render:v=>v?`${v}%`:'—' },
                { key:'avg_customer_ltv',    label:'Avg LTV',      render:v=>fmt(v) },
                { key:'champion_count',      label:'Champions',    render:v=>fmtN(v) },
                { key:'high_churn_count',    label:'High Churn',   render:v=><span style={{color:'var(--red)'}}>{fmtN(v)}</span> },
                { key:'migrated_to_online',  label:'Went Online',  render:v=>fmtN(v) },
                { key:'top_category_at_store',label:'Top Category' },
                { key:'__csv', label:'',
                  render:(_, row) => (
                    <button className="btn-ghost"
                      style={{ fontSize:11, padding:'3px 8px', display:'flex', alignItems:'center', gap:4 }}
                      onClick={e => { e.stopPropagation(); window.open(api.getStoreExportUrl(row.store_name), '_blank') }}>
                      <Download size={11}/> CSV
                    </button>
                  )
                },
              ]}
              rows={stores}
              onRowClick={row => row.store_name !== '__compare__' && setSelected(row)}
            />
            <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:10, textAlign:'center' }}>
              ☑ Check up to 3 stores to compare side by side
            </div>
          </div>
        </>
      )}
    </div>
  )
}
