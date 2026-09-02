import { useCallback, useEffect, useState } from 'react'
import { Activity, AlertTriangle, ChevronLeft, ChevronRight, RefreshCw, Trash2 } from 'lucide-react'

import { MetricCard } from './components/MetricCard'
import { TraceDetail } from './components/TraceDetail'
import {
  clearTraces,
  deleteTrace,
  getMetrics,
  getTrace,
  getTraces,
  type Metrics,
  type TraceDetail as TraceDetailType,
  type TraceFilters,
  type TraceSummary,
} from './services/api'

const initialFilters: TraceFilters = { path: '', statusCode: '', minDuration: '' }
const pageSize = 50

function formatDuration(duration: number) {
  return `${Math.round(duration)} ms`
}

function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function App() {
  const [filters, setFilters] = useState(initialFilters)
  const [offset, setOffset] = useState(0)
  const [traces, setTraces] = useState<TraceSummary[]>([])
  const [totalTraces, setTotalTraces] = useState(0)
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [selectedTrace, setSelectedTrace] = useState<TraceDetailType | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async (activeFilters = filters, activeOffset = offset) => {
    setError(null)
    try {
      const [traceResponse, metricResponse] = await Promise.all([
        getTraces(activeFilters, activeOffset, pageSize),
        getMetrics(),
      ])
      setTraces(traceResponse.items)
      setTotalTraces(traceResponse.total)
      setMetrics(metricResponse)
    } catch {
      setError('TraceLens cannot reach the local API. Start the proxy and refresh.')
    } finally {
      setLoading(false)
    }
  }, [filters, offset])

  useEffect(() => {
    void loadData()
    const refreshTimer = window.setInterval(() => void loadData(), 2000)
    return () => window.clearInterval(refreshTimer)
  }, [loadData])

  async function selectTrace(traceId: number) {
    setLoadingDetail(true)
    setSelectedTrace(null)
    try {
      setSelectedTrace(await getTrace(traceId))
    } catch {
      setError('That trace is no longer available.')
    } finally {
      setLoadingDetail(false)
    }
  }

  async function clearHistory() {
    if (!window.confirm('Clear all locally captured traces? This cannot be undone.')) return
    await clearTraces()
    setSelectedTrace(null)
    await loadData()
  }

  async function deleteSelectedTrace(traceId: number) {
    if (!window.confirm('Delete this trace and its local analysis audit metadata?')) return
    try {
      await deleteTrace(traceId)
      setSelectedTrace(null)
      const nextOffset = traces.length === 1 && offset > 0 ? offset - pageSize : offset
      setOffset(nextOffset)
      await loadData(filters, nextOffset)
    } catch {
      setError('That trace could not be deleted.')
    }
  }

  function updateFilters(nextFilters: TraceFilters) {
    setFilters(nextFilters)
    setOffset(0)
  }

  const filterActive = Object.values(filters).some(Boolean)
  const anomalyCount = traces.filter((trace) => trace.is_anomaly).length
  const rangeStart = totalTraces ? offset + 1 : 0
  const rangeEnd = Math.min(offset + traces.length, totalTraces)

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><Activity size={19} /></div>
          <div><strong>TraceLens</strong><span>Local observability</span></div>
        </div>
        <div className="live-state"><i /> Capturing traffic</div>
      </header>

      <section className="workspace">
        <div className="page-title">
          <div>
            <p className="eyebrow">Traffic console</p>
            <h1>API traffic, in focus.</h1>
          </div>
          <div className="toolbar">
            <button className="icon-button" onClick={() => void loadData()} aria-label="Refresh traffic" title="Refresh traffic">
              <RefreshCw size={17} />
            </button>
            <button className="command-button danger" onClick={() => void clearHistory()} disabled={!traces.length}>
              <Trash2 size={16} /> Clear history
            </button>
          </div>
        </div>

        <section className="metrics-grid" aria-label="Traffic metrics">
          <MetricCard label="Requests" value={metrics?.request_count.toLocaleString() ?? '--'} />
          <MetricCard label="Error rate" value={metrics ? `${(metrics.error_rate * 100).toFixed(1)}%` : '--'} tone={metrics && metrics.error_rate > 0 ? 'alert' : 'default'} />
          <MetricCard label="Average latency" value={metrics ? formatDuration(metrics.average_duration_ms) : '--'} />
          <MetricCard label="P95 latency" value={metrics ? formatDuration(metrics.p95_duration_ms) : '--'} />
        </section>

        <section className="traffic-panel">
          <div className="panel-heading">
            <div><h2>Recent requests</h2><span>{loading ? 'Connecting...' : `${rangeStart}-${rangeEnd} of ${totalTraces} traces`}</span></div>
            {!!anomalyCount && <span className="anomaly-summary"><AlertTriangle size={14} /> {anomalyCount} {anomalyCount === 1 ? 'latency anomaly' : 'latency anomalies'}</span>}
            <span className="refresh-note">Refreshes every 2 seconds</span>
          </div>

          <div className="filters" aria-label="Trace filters">
            <label>Endpoint<input value={filters.path} onChange={(event) => updateFilters({ ...filters, path: event.target.value })} placeholder="Filter path" /></label>
            <label>Status<select value={filters.statusCode} onChange={(event) => updateFilters({ ...filters, statusCode: event.target.value })}><option value="">All statuses</option><option value="200">200 OK</option><option value="201">201 Created</option><option value="400">400 Bad request</option><option value="404">404 Not found</option><option value="500">500 Server error</option><option value="502">502 Gateway error</option><option value="504">504 Timeout</option></select></label>
            <label>Min latency<input type="number" min="0" value={filters.minDuration} onChange={(event) => updateFilters({ ...filters, minDuration: event.target.value })} placeholder="Milliseconds" /></label>
            {filterActive && <button className="text-button" onClick={() => updateFilters(initialFilters)}>Reset filters</button>}
          </div>

          {error && <p className="error-state">{error}</p>}
          {!error && !loading && !traces.length && <div className="empty-state"><Activity size={26} /><h3>No traffic captured yet</h3><p>Send a request through TraceLens to see it appear here.</p></div>}
          {!!traces.length && <div className="table-wrap"><table><thead><tr><th>Method</th><th>Endpoint</th><th>Status</th><th>Duration</th><th>Signal</th><th>Time</th></tr></thead><tbody>{traces.map((trace) => <tr key={trace.id} onClick={() => void selectTrace(trace.id)}><td><span className="method-badge">{trace.method}</span></td><td className="path-cell">{trace.path}</td><td><span className={`status status-${Math.floor((trace.status_code ?? 0) / 100)}`}>{trace.status_code ?? trace.error_type ?? 'Failed'}</span></td><td className={trace.is_anomaly ? 'slow' : ''}>{formatDuration(trace.duration_ms)}</td><td>{trace.is_anomaly && <span className="anomaly-icon" title="Latency anomaly"><AlertTriangle size={15} /><span className="sr-only">Latency anomaly</span></span>}</td><td>{formatTime(trace.timestamp)}</td></tr>)}</tbody></table></div>}
          {!!traces.length && <div className="pagination" aria-label="Trace pagination"><button className="icon-button" onClick={() => setOffset(Math.max(0, offset - pageSize))} disabled={offset === 0} aria-label="Previous page" title="Previous page"><ChevronLeft size={17} /></button><span>{rangeStart}-{rangeEnd} of {totalTraces}</span><button className="icon-button" onClick={() => setOffset(offset + pageSize)} disabled={offset + traces.length >= totalTraces} aria-label="Next page" title="Next page"><ChevronRight size={17} /></button></div>}
        </section>
      </section>

      <TraceDetail trace={selectedTrace} loading={loadingDetail} onClose={() => { setSelectedTrace(null); setLoadingDetail(false) }} onDelete={(traceId) => void deleteSelectedTrace(traceId)} />
    </main>
  )
}

export default App
