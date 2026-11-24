import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OnboardingGuide } from './OnboardingGuide';

describe('Quick start guide', () => {
  it('moves through the steps, supports returning and offers the appropriate final action', () => {
    const start = vi.fn();
    const dismiss = vi.fn();
    render(<OnboardingGuide userRole="user" hasActiveCalculation onDismiss={dismiss} onStart={start} />);
    expect(screen.getByRole('button', { name: 'Voltar' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Próxima etapa' }));
    expect(screen.getByRole('heading', { name: 'Confira antes de calcular' })).toHaveFocus();
    fireEvent.click(screen.getByRole('button', { name: 'Voltar' }));
    expect(screen.getByRole('heading', { name: 'Prepare os documentos' })).toHaveFocus();
    fireEvent.click(screen.getByRole('button', { name: 'Próxima etapa' }));
    fireEvent.click(screen.getByRole('button', { name: 'Próxima etapa' }));
    expect(screen.getByText('Resultado', { exact: true }).closest('li')).toHaveAttribute('aria-current', 'step');
    expect(screen.queryByText(/Na área Administração/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retomar cálculo' }));
    expect(start).toHaveBeenCalledOnce();
    expect(dismiss).not.toHaveBeenCalled();
  });

  it('shows administration guidance only to a manager and allows skipping at any step', () => {
    const dismiss = vi.fn();
    render(<OnboardingGuide userRole="admin" hasActiveCalculation={false} onDismiss={dismiss} onStart={vi.fn()} focusOnOpen />);
    expect(screen.getByRole('heading', { name: 'Prepare os documentos' })).toHaveFocus();
    fireEvent.click(screen.getByRole('button', { name: 'Próxima etapa' }));
    fireEvent.click(screen.getByRole('button', { name: 'Próxima etapa' }));
    expect(screen.getByText(/Na área Administração/)).toBeVisible();
    expect(screen.getByRole('button', { name: 'Começar cálculo' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Pular guia' }));
    expect(dismiss).toHaveBeenCalledOnce();
  });
});
