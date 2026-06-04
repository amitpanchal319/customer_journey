// lib/api.js
// Central API client — all fetch calls go through Next.js proxy

const BASE = ''  // empty = use Next.js proxy via next.config.js (rewrites /api/* → localhost:8002/api/*)

async function get(path) {
  const res = await fetch(`${BASE}${path}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json()
}

export const api = {
  // ── Health ──────────────────────────────────────────────────
  health: () => get('/api/health'),

  // ── Customer 360 ────────────────────────────────────────────
  searchCustomer: (q)              => get(`/api/customer/search?q=${encodeURIComponent(q)}`),
  getCustomer:    (combo)          => get(`/api/customer/by-combo?combo=${encodeURIComponent(combo)}`),
  getCustomerByUnqId: (unqId)      => get(`/api/customer/by-unq-id/${unqId}`),
  getTimeline:    (combo, channel = 'all') =>
    get(`/api/customer/timeline?combo=${encodeURIComponent(combo)}&channel=${channel}`),

  // ── Segments ─────────────────────────────────────────────────
  getSegmentSummary: (filters={}) => get('/api/segments/summary' + buildQuery(filters)),
  getRFM:            (filters={}) => get('/api/segments/rfm'       + buildQuery(filters)),
  getRFMCustomers:   (filters={}) => get('/api/segments/rfm/customers' + buildQuery(filters)),
  getRFMExportUrl:   (filters={}) => `/api/segments/rfm/export-csv${buildQuery(filters)}`,
  getChurn:          (filters={}) => get('/api/segments/churn'     + buildQuery(filters)),
  getReturnRisk:     (filters={}) => get('/api/segments/return-risk' + buildQuery(filters)),
  getAOVComparison:  (filters={}) => get('/api/segments/aov-comparison' + buildQuery(filters)),
  getFrequency:      (filters={}) => get('/api/segments/frequency'    + buildQuery(filters)),
  getFrequencyExportUrl: (filters={}) => `/api/segments/frequency/export-csv${buildQuery(filters)}`,
  getMigration:      ()           => get('/api/segments/migration'),
  getCategory:       (filters={}) => get('/api/segments/category'  + buildQuery(filters)),
  getSizeBehaviour:  ()           => get('/api/segments/size'),

  // ── Cohorts ──────────────────────────────────────────────────
  getCohortRetention:       (months=12)     => get(`/api/cohorts/retention?months=${months}`),
  getCohortRetentionByMonth:(startMonth)    => get(`/api/cohorts/retention?start_month=${startMonth}`),
  getCohortExportUrl:       (months=12)     => `/api/cohorts/export-csv?months=${months}`,
  getCohortExportUrlByMonth:(startMonth)    => `/api/cohorts/export-csv?start_month=${startMonth}`,
  getCohortRetentionByMonths:(monthsCsv)    => get(`/api/cohorts/retention?cohort_months=${encodeURIComponent(monthsCsv)}`),
  getCohortExportUrlByMonths:(monthsCsv)    => `/api/cohorts/export-csv?cohort_months=${encodeURIComponent(monthsCsv)}`,
  getMoM:                   (months=12)     => get(`/api/cohorts/mom?months=${months}`),
  getMoMFiltered:           (filters={})    => get('/api/cohorts/mom' + buildQuery(filters)),
  getMoMByMonth:            (startMonth)    => get(`/api/cohorts/mom?start_month=${startMonth}`),
  getRetentionFlags:        ()              => get('/api/cohorts/retention-flags'),

  // ── Stores ───────────────────────────────────────────────────
  getStores:           ()              => get('/api/stores/summary'),
  getStoreDetail:      (name)          => get(`/api/stores/detail/${encodeURIComponent(name)}`),
  getStoreMoM:         (name, months='12') => get(`/api/stores/mom/${encodeURIComponent(name)}?months=${months}`),
  getStoreCompare:     (stores)        => get(`/api/stores/store-compare?stores=${Array.isArray(stores) ? stores.map(encodeURIComponent).join(',') : encodeURIComponent(stores)}`),
  getMultiStoreCustomers: (zone='', minStores=2) =>
    get(`/api/stores/multi-store-customers?min_stores=${minStores}${zone ? '&zone='+zone : ''}`),
  getStoreExportUrl:   (name, segment='') =>
    `/api/stores/export-csv/${encodeURIComponent(name)}${segment ? '?segment='+encodeURIComponent(segment) : ''}`,
  getStoreMetricExportUrl: (name, metric='all') =>
    `/api/stores/export-metric/${encodeURIComponent(name)}?metric=${encodeURIComponent(metric)}`,

  // ── Export ───────────────────────────────────────────────────
  getExportCount: (filters={}) => get('/api/export/count' + buildQuery(filters)),
  getExportUrl:   (filters={}) => `/api/export/csv${buildQuery(filters)}`,

  // ── AI Agent ─────────────────────────────────────────────────
  getAgentSchema  : ()           => get('/api/agent/schema'),
  agentQuery      : (question, history=[]) =>
    fetch('/api/agent/query', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ question, history }),
    }).then(r => r.json()),
  agentExecute    : (sql) =>
    fetch('/api/agent/execute', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ sql }),
    }).then(r => r.json()),
  agentExportUrl  : (sql) => {
    const encoded = encodeURIComponent(sql)
    return `/api/agent/export-csv`
  },
  // ── Agentic AI (v2 — LangGraph) ──────────────────────────────
  agentV2Query : (question, storeName='', history=[]) =>
    fetch('/api/agent/v2/query', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ question, store_name: storeName, history }),
    }).then(r => r.json()),
  agentV2ExportCsv : (sql) =>
    fetch('/api/agent/v2/export-csv', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ sql }),
    }),

  // ── EBO Agent ────────────────────────────────────────────────
  eboAgentQuery   : (question, storeName='', history=[]) =>
    fetch('/api/agent/ebo-query', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ question, store_name: storeName, history }),
    }).then(r => r.json()),
  eboExportCsv    : (sql) =>
    fetch('/api/agent/ebo-export-csv', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ sql }),
    }),

  agentExportCsv  : (sql) =>
    fetch('/api/agent/export-csv', {
      method : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body   : JSON.stringify({ sql }),
    }),
}

function buildQuery(filters) {
  const params = Object.entries(filters)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join('&')
  return params ? `?${params}` : ''
}