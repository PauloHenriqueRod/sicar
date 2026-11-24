import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { Login } from './Login';

describe('Login Component', () => {
  it('renders login form correctly', () => {
    render(<Login onLogin={vi.fn()} />);
    
    expect(screen.getByText('SICAR')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Digite seu usuário')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Digite sua senha')).toBeInTheDocument();
    expect(screen.getByLabelText('Usuário')).toHaveAttribute('autocomplete', 'username');
    expect(screen.getByLabelText('Senha')).toHaveAttribute('autocomplete', 'current-password');
    expect(screen.getByRole('button', { name: /entrar no sistema/i })).toBeInTheDocument();
  });

  it('disables submit button when fields are empty', () => {
    render(<Login onLogin={vi.fn()} />);
    
    const submitButton = screen.getByRole('button', { name: /entrar no sistema/i });
    expect(submitButton).toBeDisabled();
  });

  it('enables submit button when both fields are filled', () => {
    render(<Login onLogin={vi.fn()} />);
    
    const userField = screen.getByPlaceholderText('Digite seu usuário');
    const passField = screen.getByPlaceholderText('Digite sua senha');
    const submitButton = screen.getByRole('button', { name: /entrar no sistema/i });
    
    fireEvent.change(userField, { target: { value: 'admin' } });
    fireEvent.change(passField, { target: { value: '123456' } });
    
    expect(submitButton).not.toBeDisabled();
  });
});
