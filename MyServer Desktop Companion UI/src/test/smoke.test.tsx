import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'

describe('Wave 0 Vitest + React Testing Library harness', () => {
  it('renders React element in jsdom with jest-dom matchers', () => {
    render(<main data-testid="wizard-harness-smoke">Wave 0 Ready</main>)
    expect(screen.getByTestId('wizard-harness-smoke')).toHaveTextContent('Wave 0 Ready')
  })
})
