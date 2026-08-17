type MetricCardProps = {
    label: string
    value: string
    tone?: 'default' | 'alert'
}

export function MetricCard({ label, value, tone = 'default' }: MetricCardProps) {
    return (
        <article className={`metric-card ${tone}`}>
        <span>{label}</span>
        <strong>{value}</strong>
        </article>
    )
}