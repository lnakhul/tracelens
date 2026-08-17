export type TraceSummary = {
    id: number
    timestamp: string
    method: string
    path: string
    status_code: number | null
    duration_ms: number
    error_type: string | null
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
        throw new Error(`Request failed with ${response.status}`)
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