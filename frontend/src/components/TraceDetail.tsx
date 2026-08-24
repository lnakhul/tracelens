import { useEffect, useState } from 'react'
import { AlertTriangle, Sparkles, X } from 'lucide-react'

import { analyzeFailure, type FailureAnalysis, type TraceDetail as TraceDetailType } from '../services/api'

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

function formatIncrease(ratio: number) {
    return `+${Math.round((ratio - 1) * 100)}%`
}

export function TraceDetail({ trace, loading, onClose }: TraceDetailProps) {
    const [consented, setConsented] = useState(false)
    const [includeBodies, setIncludeBodies] = useState(false)
    const [analysis, setAnalysis] = useState<FailureAnalysis | null>(null)
    const [analysisError, setAnalysisError] = useState<string | null>(null)
    const [analyzing, setAnalyzing] = useState(false)

    useEffect(() => {
        setConsented(false)
        setIncludeBodies(false)
        setAnalysis(null)
        setAnalysisError(null)
        setAnalyzing(false)
    }, [trace?.id])

    if (!trace && !loading) return null

    const isFailure = trace && ((trace.status_code !== null && trace.status_code >= 500) || trace.error_type !== null)

    async function requestAnalysis() {
        if (!trace || !consented) return
        setAnalyzing(true)
        setAnalysisError(null)
        try {
            setAnalysis(await analyzeFailure(trace.id, includeBodies))
        } catch (error) {
            setAnalysisError(error instanceof Error ? error.message : 'Analysis is unavailable.')
        } finally {
            setAnalyzing(false)
        }
    }

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
            <div className={`trace-callout ${trace.is_anomaly ? 'anomaly-callout' : ''}`}>
                <span className="method-badge">{trace.method}</span>
                <span className={`status status-${Math.floor((trace.status_code ?? 0) / 100)}`}>
                {trace.status_code ?? trace.error_type ?? 'Failed'}
                </span>
                <strong>{formatDuration(trace.duration_ms)}</strong>
            </div>

            {trace.is_anomaly && trace.baseline_duration_ms !== null && trace.latency_increase_ratio !== null && (
                <div className="anomaly-detail"><AlertTriangle size={17} /><span>Latency anomaly: {formatDuration(trace.duration_ms)} vs {formatDuration(trace.baseline_duration_ms)} baseline ({formatIncrease(trace.latency_increase_ratio)})</span></div>
            )}

            <dl className="trace-meta">
                <div><dt>Timestamp</dt><dd>{new Date(trace.timestamp).toLocaleString()}</dd></div>
                <div><dt>Query</dt><dd>{trace.query_string || 'None'}</dd></div>
                <div><dt>Error</dt><dd>{trace.error_type || 'None'}</dd></div>
            </dl>

            {isFailure && <section className="analysis-block">
                <div className="analysis-heading"><div><p className="eyebrow">Failure analysis</p><h3>Investigate with AI</h3></div><Sparkles size={19} /></div>
                {!analysis && <>
                    <label className="consent-option"><input type="checkbox" checked={consented} onChange={(event) => setConsented(event.target.checked)} /> I consent to share this trace's sanitized metadata with my configured AI provider.</label>
                    <label className="consent-option"><input type="checkbox" checked={includeBodies} disabled={!consented} onChange={(event) => setIncludeBodies(event.target.checked)} /> Include captured request and response bodies.</label>
                    <button className="command-button" onClick={() => void requestAnalysis()} disabled={!consented || analyzing}>{analyzing ? 'Analyzing...' : 'Analyze failure'}</button>
                    {analysisError && <p className="analysis-error">{analysisError}</p>}
                </>}
                {analysis && <div className="analysis-result">
                    <div><h4>Likely cause</h4><p>{analysis.likely_cause}</p></div>
                    <div><h4>Evidence</h4><ul>{analysis.evidence.map((item) => <li key={item}>{item}</li>)}</ul></div>
                    <div><h4>Suggested investigation</h4><p>{analysis.suggested_investigation}</p></div>
                    <span>Analyzed with {analysis.model}</span>
                </div>}
            </section>}

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