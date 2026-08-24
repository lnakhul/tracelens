export type TraceSummary = {
    id: number
    timestamp: string
    method: string
    path: string
    status_code: number | null
    duration_ms: number
    error_type: string | null
    baseline_duration_ms: number | null
    latency_increase_ratio: number | null
    is_anomaly: boolean
}

export type TraceDetail = TraceSummary & {
    query_string: string | null
    request_headers: string | null
    request_body: string | null
    response_headers: string | null
    response_body: string | null
}

export type Metrics = {
    request_count: number
    error_rate: number
    average_duration_ms: number
    p95_duration_ms: number
}

export type FailureAnalysis = {
    likely_cause: string
    evidence: string[]
    suggested_investigation: string
    model: string
    data_shared: boolean
}

export type TraceFilters = {
    path: string
    statusCode: string
    minDuration: string
}

type TraceList = {
    items: TraceSummary[]
    total: number
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
    const response = await fetch(url, init)
    if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null
        throw new Error(payload?.detail ?? `Request failed with ${response.status}`)
    }
    return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export function getTraces(filters: TraceFilters): Promise<TraceList> {
    const parameters = new URLSearchParams({ limit: '50' })
    if (filters.path) parameters.set('path', filters.path)
    if (filters.statusCode) parameters.set('status_code', filters.statusCode)
    if (filters.minDuration) parameters.set('min_duration_ms', filters.minDuration)
    return request<TraceList>(`/api/traces?${parameters}`)
}

export function getTrace(traceId: number): Promise<TraceDetail> {
    return request<TraceDetail>(`/api/traces/${traceId}`)
}

export function getMetrics(): Promise<Metrics> {
    return request<Metrics>('/api/metrics')
}

export function clearTraces(): Promise<void> {
    return request<void>('/api/traces', { method: 'DELETE' })
}

export function analyzeFailure(
    traceId: number,
    includeBodies: boolean,
): Promise<FailureAnalysis> {
    return request<FailureAnalysis>(`/api/traces/${traceId}/analysis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ share_data: true, include_bodies: includeBodies }),
    })
}