import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TraceDetail } from './TraceDetail'
import { analyzeFailure, type TraceDetail as TraceDetailType } from '../services/api'

vi.mock('../services/api', () => ({ analyzeFailure: vi.fn() }))

const failedTrace: TraceDetailType = {
  id: 42,
  timestamp: '2026-08-24T12:00:00Z',
  method: 'POST',
  path: '/orders',
  status_code: 500,
  duration_ms: 124,
  error_type: null,
  baseline_duration_ms: null,
  latency_increase_ratio: null,
  is_anomaly: false,
  query_string: null,
  request_headers: '{}',
  request_body: '{"product_id":"product-1"}',
  response_headers: '{}',
  response_body: '{"detail":"Internal Server Error"}',
}

function renderDetail() {
  return render(<TraceDetail trace={failedTrace} loading={false} onClose={vi.fn()} />)
}

describe('TraceDetail failure analysis', () => {
  afterEach(() => {
    cleanup()
    vi.resetAllMocks()
  })

  it('requires consent before enabling analysis or body sharing', async () => {
    const user = userEvent.setup()
    renderDetail()

    const analyzeButton = screen.getByRole('button', { name: 'Analyze failure' })
    const bodyOption = screen.getByRole('checkbox', {
      name: 'Include captured request and response bodies.',
    })

    expect(analyzeButton).toBeDisabled()
    expect(bodyOption).toBeDisabled()

    await user.click(
      screen.getByRole('checkbox', {
        name: /I consent to share this trace's sanitized metadata/i,
      }),
    )

    expect(analyzeButton).toBeEnabled()
    expect(bodyOption).toBeEnabled()
  })

  it('renders the sanitized provider error', async () => {
    vi.mocked(analyzeFailure).mockRejectedValue(
      new Error('AI provider rejected the request (HTTP 429). Check the API key, billing, and model access.'),
    )
    const user = userEvent.setup()
    renderDetail()

    await user.click(
      screen.getByRole('checkbox', {
        name: /I consent to share this trace's sanitized metadata/i,
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Analyze failure' }))

    expect(analyzeFailure).toHaveBeenCalledWith(42, false)
    expect(
      await screen.findByText(
        'AI provider rejected the request (HTTP 429). Check the API key, billing, and model access.',
      ),
    ).toBeInTheDocument()
  })

  it('renders a structured successful analysis', async () => {
    vi.mocked(analyzeFailure).mockResolvedValue({
      likely_cause: 'The request is missing customer_id.',
      evidence: ['The trace returned HTTP 500.', 'Successful requests include customer_id.'],
      suggested_investigation: 'Validate customer_id before calling OrderService.',
      model: 'gpt-4o-mini',
      data_shared: true,
    })
    const user = userEvent.setup()
    renderDetail()

    await user.click(
      screen.getByRole('checkbox', {
        name: /I consent to share this trace's sanitized metadata/i,
      }),
    )
    await user.click(screen.getByRole('button', { name: 'Analyze failure' }))

    expect(await screen.findByText('The request is missing customer_id.')).toBeInTheDocument()
    expect(screen.getByText('The trace returned HTTP 500.')).toBeInTheDocument()
    expect(
      screen.getByText('Validate customer_id before calling OrderService.'),
    ).toBeInTheDocument()
    expect(screen.getByText('Analyzed with gpt-4o-mini')).toBeInTheDocument()
  })
})