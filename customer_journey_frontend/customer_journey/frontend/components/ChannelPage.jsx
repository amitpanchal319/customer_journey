'use client'
import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { Download } from 'lucide-react'
import { api } from '../lib/api'
import { StatCard, SegBadge, ChurnBadge, Table, PageHeader, CardSkeleton, Empty } from './UI'

function fmt(n)  { if (!n) return '₹0'; if (n>=100000) return `₹${(n/100000).toFixed(1)}L`; if (n>=1000) return `₹${(n/1000).toFixed(1)}K`; return `₹${n}` }
function fmtN(n) { if (!n) return '0';  if (n>=10000000) return `${(n/10000000).toFixed(1)}Cr`; if (n>=100000) return `${(n/100000).toFixed(1)}L`; if (n>=1000) return `${(n/1000).toFixed(1)}K`; return `${n}` }

export default function ChannelPage({ channelFilter, title, subtitle, color = 'blue' }) {
  const [rfm,     setRfm]     = useState([])
  const [freq,    setFreq]    = useState([])
  const [aov,     setAov]     = useState([])
  const [cat,     setCat]     = useState([])
  const [loading, setLoading] = useState(true)
  const [exportCount, setExportCount] = useState(null)

  // Map display channel to API channel_journey value
  const channelMap = {
    'Online Only' : 'Online Only',
    'Offline Only': 'Offline Only',
    'Both'        : 'Both',
  }
  const apiChannel = channelMap[channelFilter]

  useEffect(() => {
    Promise.all([
      api.getRFM({ channel: apiChannel }),
      api.getFrequency(),
      api.getAOVComparison(),
      api.getCategory({ channel: apiChannel }),
      api.getExportCount({ channel_journey: apiChannel }),
    ]).then(([r, f, a, c, ec]) => {
      setRfm(r.segments || [])
      setFreq(f || [])
      setAov(a || [])
      setCat((c || []).slice(0, 10))
      setExportCount(ec?.count)
    }).finally(() => setLoading(false))
  }, [apiChannel])

  const handleExport = () => {
    const url = api.getExportUrl({ channel_journey: apiChannel })
    window.open(url, '_blank')
  }

  return (
    <div style={{ padding: '32px 36px', maxWidth: 1400, margin: '0 auto' }}>
      <PageHeader
        title={title}
        subtitle={subtitle}
        action={
          <button className="btn-primary" onClick={handleExport} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Download size={13} />
            Export {exportCount ? fmtN(exportCount) : ''} customers
          </button>
        }
      />

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14, marginBottom: 24 }}>
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card" style={{ padding: 20 }}>
              <div className="skeleton" style={{ height: 14, width: '60%', marginBottom: 10 }} />
              <div className="skeleton" style={{ height: 28, width: '40%' }} />
            </div>
          ))
        ) : rfm.map((r, i) => (
          <div key={i} className="card" style={{ padding: '16px 18px' }}>
            <div style={{ marginBottom: 8 }}><SegBadge segment={r.rfm_segment} /></div>
            <div style={{ fontSize: 22, fontWeight: 800, fontFamily: 'var(--font-display)' }}>{fmtN(r.customers)}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }}>avg LTV {fmt(r.avg_ltv)}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 20 }}>

        {/* AOV comparison */}
        <div className="card" style={{ padding: 24 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>AOV — New vs Repeat</div>
          {loading ? <CardSkeleton rows={4} /> : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={aov}>
                <XAxis dataKey="customer_type" tick={{ fontSize: 12, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} tickFormatter={v => `₹${v}`} />
                <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }} formatter={v => `₹${v}`} />
                <Bar dataKey="avg_ebo_aov"    name="EBO AOV"    fill="var(--amber)"  radius={[4,4,0,0]} />
                <Bar dataKey="avg_online_aov" name="Online AOV" fill="var(--accent)" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Frequency */}
        <div className="card" style={{ padding: 24 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>Purchase Frequency</div>
          {loading ? <CardSkeleton rows={4} /> : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={freq} layout="vertical">
                <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} tickFormatter={fmtN} />
                <YAxis type="category" dataKey="frequency_bucket" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} width={80} />
                <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }} />
                <Bar dataKey="customers" name="Customers" fill="var(--accent)" radius={[0,4,4,0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Category table */}
      <div className="card" style={{ padding: 24 }}>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>Category Breakdown</div>
        {loading ? <CardSkeleton rows={6} /> : cat.length === 0 ? (
          <Empty title="No category data" sub="item_master join may have no matches for this channel" />
        ) : (
          <Table
            columns={[
              { key: 'top_category',      label: 'Category' },
              { key: 'customers',         label: 'Customers',   render: v => fmtN(v) },
              { key: 'repeat_customers',  label: 'Repeat',      render: v => fmtN(v) },
              { key: 'repeat_rate_pct',   label: 'Repeat Rate', render: v => v ? `${v}%` : '—' },
              { key: 'single_cat_customers', label: 'Category-Only', render: v => fmtN(v) },
              { key: 'avg_ltv',           label: 'Avg LTV',     render: v => fmt(v) },
            ]}
            rows={cat}
          />
        )}
      </div>
    </div>
  )
}
