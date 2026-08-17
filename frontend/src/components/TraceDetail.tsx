import { X } from 'lucide-react'

import type { TraceDetail as TraceDetailType } from '../services/api'

type TraceDetailProps = {
    trace: TraceDetailType | null
    loading: boolean
    onClose: () => void
}

function formatJson(value: string | null) {
    if (!value) return 'Not captured'
    try {
        return JSON.stringify(JSON.parse(value), null, 2)
    } catch {
        return value
    }
}

function formatDuration(duration: number) {
    return `${Math.round(duration)} ms`
}

export function TraceDetail({ trace, loading, onClose }: TraceDetailProps) {
    if (!trace && !loading) return null

    return (
        <aside className="detail-panel" aria-label="Trace detail">
        <div className="detail-header">
            <div>
            <p className="eyebrow">Trace detail</p>
            <h2>{loading || !trace ? 'Loading trace...' : trace.path}</h2>
            </div>
            <button className="icon-button" onClick={onClose} aria-label="Close trace detail">
            <X size={18} />
            </button>
        </div>

        {trace && (
            <div className="detail-content">
            <div className="trace-callout">
                <span className="method-badge">{trace.method}</span>
                <span className={`status status-${Math.floor((trace.status_code ?? 0) / 100)}`}>
                {trace.status_code ?? trace.error_type ?? 'Failed'}
                </span>
                <strong>{formatDuration(trace.duration_ms)}</strong>
            </div>

            <dl className="trace-meta">
                <div><dt>Timestamp</dt><dd>{new Date(trace.timestamp).toLocaleString()}</dd></div>
                <div><dt>Query</dt><dd>{trace.query_string || 'None'}</dd></div>
                <div><dt>Error</dt><dd>{trace.error_type || 'None'}</dd></div>
            </dl>

            <DetailBlock title="Request headers" value={formatJson(trace.request_headers)} />
            <DetailBlock title="Request body" value={formatJson(trace.request_body)} />
            <DetailBlock title="Response headers" value={formatJson(trace.response_headers)} />
            <DetailBlock title="Response body" value={formatJson(trace.response_body)} />
            </div>
        )}
        </aside>
    )
}

function DetailBlock({ title, value }: { title: string; value: string }) {
    return (
        <section className="detail-block">
        <h3>{title}</h3>
        <pre>{value}</pre>
        </section>
    )
}