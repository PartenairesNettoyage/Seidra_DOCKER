import React from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Sidebar } from '../sidebar'

;(globalThis as unknown as { React?: typeof React }).React = React

describe('Sidebar', () => {
  const defaultProps = {
    activeTab: 'generate',
    onTabChange: vi.fn(),
    collapsed: false,
    onToggleCollapse: vi.fn(),
  }

  it('expose les attributs ARIA essentiels', () => {
    render(<Sidebar {...defaultProps} />)

    const navigation = screen.getByRole('navigation', { name: /navigation principale/i })
    expect(navigation).toBeInTheDocument()

    const toggleButton = screen.getByRole('button', { name: /réduire la navigation/i })
    expect(toggleButton).toHaveAttribute('aria-expanded', 'true')
    expect(toggleButton).toHaveAttribute('aria-controls')

    const activeButton = within(navigation).getByRole('button', { name: /Generate/i })
    expect(activeButton).toHaveAttribute('aria-current', 'page')
  })

  it('permet de parcourir les onglets au clavier', async () => {
    const user = userEvent.setup()
    render(<Sidebar {...defaultProps} />)

    const navigation = screen.getByRole('navigation', { name: /navigation principale/i })
    const buttons = within(navigation).getAllByRole('button')

    buttons[0].focus()
    expect(buttons[0]).toHaveFocus()

    await user.keyboard('{ArrowDown}')
    expect(buttons[1]).toHaveFocus()

    await user.keyboard('{End}')
    expect(buttons[buttons.length - 1]).toHaveFocus()

    await user.keyboard('{ArrowUp}')
    expect(buttons[buttons.length - 2]).toHaveFocus()
  })
})
