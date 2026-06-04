'use client'
import { useState, useEffect } from 'react'
import { Search, Download, User, MapPin, Phone, Mail, Globe, Store, ChevronDown, ChevronUp } from 'lucide-react'
import { api } from '../../lib/api'
import { SegBadge, ChurnBadge, ChannelBadge, MetricRow, PageHeader, Empty } from '../../components/UI'

function fmt(n)  { if (!n) return '₹0'; if(n>=10000000) return `₹${(n/10000000).toFixed(1)}Cr`; if(n>=100000) return `₹${(n/100000).toFixed(1)}L`; if(n>=1000) return `₹${(n/1000).toFixed(1)}K`; return `₹${n}` }
function fmtD(d) { if (!d) return '—'; return new Date(d).toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' }) }

// ── Customer Profile Card ──────────────────────────────────────────────────────
function ProfileCard({ customer, onViewTimeline }) {
  const [expanded, setExpanded] = useState(false)
  const c = customer

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden', animation: 'slideUp 0.3s ease forwards' }}>
      {/* Header */}
      <div style={{ padding: '20px 24px', background: 'var(--bg-subtle)', borderBottom: '1px solid var(--border)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          <div style={{ width: 48, height: 48, borderRadius: '50%', background: 'var(--accent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            <span style={{ color: '#fff', fontWeight: 700, fontSize: 18, fontFamily: 'var(--font-display)' }}>
              {(c.consumer_name || c.email || '?')[0].toUpperCase()}
            </span>
          </div>
          <div>
            <div style={{ fontSize: 17, fontWeight: 700, fontFamily: 'var(--font-display)' }}>{c.consumer_name || '—'}</div>
            <div style={{ display: 'flex', gap: 8, marginTop: 4, flexWrap: 'wrap' }}>
              <SegBadge segment={c.rfm_segment} />
              <ChurnBadge risk={c.churn_risk} />
              <ChannelBadge channel={c.channel_journey} />
            </div>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 22, fontWeight: 800, fontFamily: 'var(--font-display)', color: 'var(--accent)' }}>{fmt(c.total_lifetime_spend)}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>Lifetime Value</div>
        </div>
      </div>

      {/* Main metrics */}
      <div style={{ padding: '20px 24px', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 24 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 12 }}>Contact</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <Mail size={13} style={{ flexShrink: 0, color: 'var(--text-muted)' }} />
              <span style={{ wordBreak: 'break-all' }}>{c.email || '—'}</span>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <Phone size={13} style={{ flexShrink: 0, color: 'var(--text-muted)' }} />
              {c.phone || '—'}
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <MapPin size={13} style={{ flexShrink: 0, color: 'var(--text-muted)' }} />
              {[c.consumer_city, c.consumer_state, c.consumer_zone].filter(Boolean).join(', ') || '—'}
            </div>
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 5 }}>
            <Store size={11} /> Offline (EBO)
          </div>
          <MetricRow label="Bills"        value={c.total_ebo_bills || 0} />
          <MetricRow label="Total Spend"  value={fmt(c.total_ebo_spend)} />
          <MetricRow label="Avg Bill"     value={fmt(c.ebo_aov)} />
          <MetricRow label="Last Visit"   value={fmtD(c.last_ebo_date)} />
          {c.primary_store && <MetricRow label="Primary Store" value={c.primary_store} />}
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 5 }}>
            <Globe size={11} /> Online (Shopify)
          </div>
          <MetricRow label="Orders"      value={c.total_online_orders || 0} />
          <MetricRow label="Total Spend" value={fmt(c.total_online_spend)} />
          <MetricRow label="Avg Order"   value={fmt(c.online_aov)} />
          <MetricRow label="Last Order"  value={fmtD(c.last_online_date)} />
          <MetricRow label="Fulfilment"  value={c.fulfilment_rate_pct ? `${c.fulfilment_rate_pct}%` : '—'} />
        </div>
      </div>

      {/* Expanded section */}
      {expanded && (
        <div style={{ padding: '0 24px 20px', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 24,
          borderTop: '1px solid var(--border)', paddingTop: 20 }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 12 }}>Retention</div>
            <MetricRow label="Customer Type"      value={c.customer_type} />
            <MetricRow label="1st → 2nd Purchase" value={c.days_1st_to_2nd_purchase ? `${c.days_1st_to_2nd_purchase} days` : '—'} />
            <MetricRow label="Retained 30d"       value={c.retained_30d ? '✓ Yes' : '✗ No'} />
            <MetricRow label="Retained 60d"       value={c.retained_60d ? '✓ Yes' : '✗ No'} />
            <MetricRow label="Retained 90d"       value={c.retained_90d ? '✓ Yes' : '✗ No'} />
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 12 }}>Product Behaviour</div>
            <MetricRow label="Top Category"     value={c.top_category || '—'} />
            <MetricRow label="Category Label"   value={c.category_label || '—'} />
            <MetricRow label="Top Brand"        value={c.top_brand || '—'} />
            <MetricRow label="Size Behaviour"   value={c.size_behaviour || '—'} />
            <MetricRow label="Size Combination" value={c.size_combination || '—'} />
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 12 }}>Journey & Returns</div>
            <MetricRow label="Migration Type" value={c.migration_type || '—'} />
            <MetricRow label="Migration Lag"  value={c.migration_lag_days ? `${c.migration_lag_days} days` : '—'} />
            <MetricRow label="Total Returns"  value={c.total_returns || 0} />
            <MetricRow label="Return Risk"    value={c.return_risk || '—'} />
            <MetricRow label="First Seen"     value={fmtD(c.first_seen_date)} />
          </div>
        </div>
      )}

      {/* Footer */}
      <div style={{ padding: '12px 24px', borderTop: '1px solid var(--border)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <button className="btn-ghost" style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 4 }}
          onClick={() => setExpanded(e => !e)}>
          {expanded ? <><ChevronUp size={13} />Less details</> : <><ChevronDown size={13} />More details</>}
        </button>
        <button className="btn-primary" style={{ fontSize: 12 }} onClick={() => onViewTimeline(c)}>
          View Timeline
        </button>
      </div>
    </div>
  )
}

// ── Timeline Modal ─────────────────────────────────────────────────────────────
function TimelineModal({ customer, onClose }) {
  const [timeline,  setTimeline]  = useState([])
  const [returns,   setReturns]   = useState([])
  const [loading,   setLoading]   = useState(true)
  const [channel,   setChannel]   = useState('all')
  const [activeTab, setActiveTab] = useState('purchases')
  const [imgErrors, setImgErrors] = useState({})

  useEffect(() => {
    setLoading(true)
    setTimeline([])
    setReturns([])
    api.getTimeline(customer.combo, channel)
      .then(d => {
        setTimeline(d.timeline || [])
        setReturns(d.returns || [])
      })
      .catch(e => console.error(e))
      .finally(() => setLoading(false))
  }, [customer.combo, channel])

  const fmtDate = (d) => d
    ? new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
    : '—'

  const Chip = ({ label, color = 'accent', text }) => label ? (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 4,
      background: `var(--${color}-light)`, color: `var(--${color})`,
    }}>{text || label}</span>
  ) : null

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div className="card" style={{ width: '100%', maxWidth: 860, maxHeight: '88vh',
        display: 'flex', flexDirection: 'column' }}>

        {/* Header */}
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>
              {customer.consumer_name} — Purchase & Return History
            </div>
            <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
              {[
                { key: 'purchases', label: `Purchases (${timeline.length})` },
                { key: 'returns',   label: `Returns (${returns.length})`,
                  danger: returns.length > 0 },
              ].map(tab => (
                <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                  style={{
                    fontSize: 12, fontWeight: 600, padding: '4px 12px',
                    borderRadius: 20, border: 'none', cursor: 'pointer',
                    background: activeTab === tab.key
                      ? (tab.danger ? 'var(--red)' : 'var(--accent)')
                      : 'var(--bg-hover)',
                    color: activeTab === tab.key ? '#fff' : 'var(--text-secondary)',
                    transition: 'all 0.15s',
                  }}>
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {activeTab === 'purchases' && (
              <select
                style={{ fontSize: 12, padding: '5px 10px', borderRadius: 6,
                  border: '1px solid var(--border)', background: 'var(--bg-subtle)',
                  color: 'var(--text-primary)', cursor: 'pointer', outline: 'none' }}
                value={channel}
                onChange={e => setChannel(e.target.value)}
              >
                <option value="all">All Channels</option>
                <option value="ebo">EBO Only</option>
                <option value="shopify">Shopify Only</option>
              </select>
            )}
            <button className="btn-ghost" onClick={onClose} style={{ padding: '5px 12px', fontSize: 12 }}>
              Close
            </button>
          </div>
        </div>

        {/* Body */}
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {loading && (
            <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
              Loading transactions...
            </div>
          )}



          {/* ── Returns Tab ── */}
          {!loading && activeTab === 'returns' && returns.length === 0 && (
            <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
              No returns found for this customer
            </div>
          )}
          {!loading && activeTab === 'returns' && returns.map((r, i) => (
            <div key={i} style={{
              display: 'flex', gap: 14, padding: '14px 20px',
              borderBottom: '1px solid var(--border)', alignItems: 'flex-start',
              background: r.qc_fail_qty > 0 ? 'rgba(220,38,38,0.03)' : 'transparent',
            }}>
              {/* Product image */}
              <div style={{
                width: 200, height: 200, borderRadius: 16, flexShrink: 0,
                background: 'var(--bg-subtle)', border: '1px solid var(--border)',
                overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {r.image_url && !imgErrors['r'+i] ? (
                  <img
                    src={(() => {
                      const url = (r.image_url || '').trim()
                      const idMatch = url.match(/[?&]id=([a-zA-Z0-9_-]{20,})/) || url.match(/\/d\/([a-zA-Z0-9_-]{20,})/)
                      if (idMatch) return 'https://drive.google.com/uc?export=view&id=' + idMatch[1]
                      return url
                    })()}
                    alt={r.category || 'product'}
                    onError={() => setImgErrors(prev => ({ ...prev, ['r'+i]: true }))}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 36 }}>↩️</span>
                    <span style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'center' }}>
                      {r.category || 'Returned item'}
                    </span>
                  </div>
                )}
              </div>

              {/* Return details */}
              <div style={{ flex: 1, minWidth: 0 }}>
                {/* Row 1: title + qty */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>
                    {r.item_no || r.sku_code || 'Unknown Item'}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--red)', marginLeft: 12, flexShrink: 0 }}>
                    {r.total_return_qty} returned
                  </div>
                </div>

                {/* Row 2: dates */}
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4, flexWrap: 'wrap' }}>
                  {r.order_date && (
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      Ordered: {new Date(r.order_date).toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' })}
                    </span>
                  )}
                  {r.return_date && (
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                      → Returned: {new Date(r.return_date).toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' })}
                    </span>
                  )}
                </div>

                {/* Row 3: return type + QC badges */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
                  {r.customer_return_qty > 0 && (
                    <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--red-light)', color: 'var(--red)' }}>
                      Customer Return: {r.customer_return_qty}
                    </span>
                  )}
                  {r.rto_qty > 0 && (
                    <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--amber-light)', color: 'var(--amber)' }}>
                      RTO (Undelivered): {r.rto_qty}
                    </span>
                  )}
                  {r.qc_status && (
                    <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 4,
                      background: r.qc_fail_qty > 0 ? 'var(--red-light)' : 'var(--green-light)',
                      color: r.qc_fail_qty > 0 ? 'var(--red)' : 'var(--green)' }}>
                      QC: {r.qc_status}
                    </span>
                  )}
                  {r.category && (
                    <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--accent-light)', color: 'var(--accent)' }}>
                      {r.category}
                    </span>
                  )}
                  {r.size && (
                    <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--purple-light)', color: 'var(--purple)' }}>
                      Size: {r.size}
                    </span>
                  )}
                  {r.season && (
                    <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--teal-light)', color: 'var(--teal)' }}>
                      {r.season}
                    </span>
                  )}
                  {r.brand && (
                    <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--green-light)', color: 'var(--green)' }}>
                      {r.brand}
                    </span>
                  )}
                  {r.sku_code && (
                    <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)',
                      background: 'var(--bg-subtle)', border: '1px solid var(--border)',
                      borderRadius: 4, padding: '2px 6px', color: 'var(--text-muted)' }}>
                      SKU: {r.sku_code}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}

          {/* ── Purchases Tab ── */}
          {!loading && activeTab === 'purchases' && timeline.length === 0 && (
            <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
              No transactions found
            </div>
          )}
          {!loading && activeTab === 'purchases' && timeline.map((t, i) => (
            <div key={i} style={{
              display: 'flex', gap: 14, padding: '14px 20px',
              borderBottom: '1px solid var(--border)', alignItems: 'flex-start',
            }}>

              {/* Product image — 200x200 thumbnail */}
              <div style={{
                width: 200, height: 200, borderRadius: 16, flexShrink: 0,
                background: 'var(--bg-subtle)', border: '1px solid var(--border)',
                overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {t.image_url && !imgErrors[i] ? (
                  <img
                    src={(() => {
                      const url = (t.image_url || '').trim()
                      if (!url) return null
                      const idMatch = url.match(/[?&]id=([a-zA-Z0-9_-]{20,})/) || url.match(/\/d\/([a-zA-Z0-9_-]{20,})/)
                      if (idMatch) {
                        return 'https://drive.google.com/uc?export=view&id=' + idMatch[1]
                      }
                      return url
                    })()}
                    alt={t.category || 'product'}
                    onError={() => setImgErrors(prev => ({ ...prev, [i]: true }))}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                    <span style={{ fontSize: 36 }}>{t.channel === 'EBO' ? '🏪' : '🛍️'}</span>
                    <span style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'center', padding: '0 8px' }}>
                      {t.category || 'No image'}
                    </span>
                  </div>
                )}
              </div>

              {/* Transaction details */}
              <div style={{ flex: 1, minWidth: 0 }}>
                {/* Row 1: store name + amount */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{t.store_or_platform}</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--accent)', marginLeft: 12, flexShrink: 0 }}>
                    ₹{Number(t.order_amount || 0).toLocaleString('en-IN')}
                  </div>
                </div>

                {/* Row 2: date + channel + return badge */}
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 4, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{fmtDate(t.txn_date)}</span>
                  <span style={{
                    fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 4,
                    background: t.channel === 'EBO' ? 'var(--amber-light)' : 'var(--accent-light)',
                    color: t.channel === 'EBO' ? 'var(--amber)' : 'var(--accent)',
                  }}>{t.channel}</span>
                  {t.return_qty > 0 && (
                    <span style={{ fontSize: 10, fontWeight: 600, padding: '1px 6px',
                      borderRadius: 4, background: 'var(--red-light)', color: 'var(--red)' }}>
                      {t.return_qty} returned
                    </span>
                  )}
                </div>

                {/* Row 3: product detail chips */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 8 }}>
                  {t.item_no && (
                    <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)',
                      background: 'var(--bg-subtle)', border: '1px solid var(--border)',
                      borderRadius: 4, padding: '2px 6px', color: 'var(--text-muted)' }}>
                      {t.item_no}
                    </span>
                  )}
                  {t.category && (
                    <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--accent-light)', color: 'var(--accent)' }}>
                      {t.category}
                    </span>
                  )}
                  {t.sub_category && (
                    <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--bg-hover)', color: 'var(--text-secondary)' }}>
                      {t.sub_category}
                    </span>
                  )}
                  {t.size && (
                    <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--purple-light)', color: 'var(--purple)' }}>
                      Size: {t.size}
                    </span>
                  )}
                  {t.season && (
                    <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--teal-light)', color: 'var(--teal)' }}>
                      {t.season}
                    </span>
                  )}
                  {t.brand && (
                    <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--green-light)', color: 'var(--green)' }}>
                      {t.brand}
                    </span>
                  )}
                  {t.design_type && (
                    <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--bg-subtle)', color: 'var(--text-muted)' }}>
                      {t.design_type}
                    </span>
                  )}
                  {t.occasion && (
                    <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 4,
                      background: 'var(--amber-light)', color: 'var(--amber)' }}>
                      {t.occasion}
                    </span>
                  )}
                  {t.sku_code && (
                    <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)',
                      background: 'var(--bg-subtle)', border: '1px solid var(--border)',
                      borderRadius: 4, padding: '2px 6px', color: 'var(--text-muted)' }}>
                      SKU: {t.sku_code}
                    </span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function CustomerPage() {
  const [query,      setQuery]      = useState('')
  const [results,    setResults]    = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading,    setLoading]    = useState(false)
  const [searched,   setSearched]   = useState(false)
  const [timeline,   setTimeline]   = useState(null)
  const [lastQuery,  setLastQuery]  = useState('')

  const search = async () => {
    if (!query.trim() || query.length < 2) return
    setLoading(true)
    setSearched(true)
    setLastQuery(query.trim())
    try {
      const d = await api.searchCustomer(query.trim())
      setResults(d.customers || [])
      setTotalCount(d.total_count || 0)
    } catch(e) { console.error(e) }
    finally { setLoading(false) }
  }

  const downloadSearchCsv = () => {
    window.open(`/api/customer/search/export-csv?q=${encodeURIComponent(lastQuery)}`, '_blank')
  }

  return (
    <div style={{ padding: '32px 36px', maxWidth: 1000, margin: '0 auto' }}>
      <PageHeader title="Customer 360" subtitle="Search any customer by email, phone, or name" />

      <div style={{ display: 'flex', gap: 12, marginBottom: 32 }}>
        <div style={{ position: 'relative', flex: 1 }}>
          <Search size={16} style={{ position: 'absolute', left: 12, top: '50%',
            transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
          <input
            className="input"
            style={{ paddingLeft: 38 }}
            placeholder="Enter email, phone number, or customer name..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
          />
        </div>
        <button className="btn-primary" onClick={search} disabled={loading}
          style={{ whiteSpace: 'nowrap', minWidth: 100 }}>
          {loading ? 'Searching...' : 'Search'}
        </button>
      </div>

      {/* Result count + CSV download */}
      {searched && !loading && results.length > 0 && (
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center',
          marginBottom:16, padding:'10px 16px', background:'var(--bg-subtle)',
          borderRadius:8, border:'1px solid var(--border)' }}>
          <div style={{ fontSize:13 }}>
            Showing <strong>{results.length}</strong> of{' '}
            <strong style={{ color:'var(--accent)' }}>{totalCount.toLocaleString()}</strong>{' '}
            customers matching <strong>"{lastQuery}"</strong>
            {totalCount > results.length && (
              <span style={{ color:'var(--text-muted)', fontSize:12 }}>
                {' '}— download CSV to get all {totalCount.toLocaleString()}
              </span>
            )}
          </div>
          <button className="btn-primary" onClick={downloadSearchCsv}
            style={{ display:'flex', alignItems:'center', gap:6, fontSize:12 }}>
            <Download size={13}/>
            Download all {totalCount.toLocaleString()} customers
          </button>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {loading && Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="card" style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {[80, 60, 40].map((w, j) => (
              <div key={j} className="skeleton" style={{ height: j===0?20:14, width:`${w}%` }} />
            ))}
          </div>
        ))}
        {!loading && searched && results.length === 0 && (
          <Empty icon={User} title="No customers found"
            sub="Try a different email, phone number, or name" />
        )}
        {!loading && results.map((c, i) => (
          <ProfileCard key={i} customer={c} onViewTimeline={setTimeline} />
        ))}
      </div>

      {timeline && <TimelineModal customer={timeline} onClose={() => setTimeline(null)} />}
    </div>
  )
}
