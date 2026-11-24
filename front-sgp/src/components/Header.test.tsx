import type { ComponentProps } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { Header } from './Header';

describe('Header Component', () => {
  it('renders without crashing', () => {
    const props: ComponentProps<typeof Header> = { isSidebarOpen: true, setIsSidebarOpen: () => {}, activeTab: 'dashboard', setShowAlterarSenha: () => {}, handleLogout: () => {} };
    const { container } = render(<Header {...props} />);
    expect(container.firstChild).not.toBeNull();
  });

  it('opens by click and closes by another click, Escape or a click outside', () => {
    render(<Header isSidebarOpen={true} setIsSidebarOpen={() => {}} activeTab="dashboard" setShowAlterarSenha={() => {}} handleLogout={() => {}} />);
    const trigger = screen.getByRole('button', { name: 'Menu da conta' });
    expect(screen.queryByRole('button', { name: 'Alterar senha' })).not.toBeInTheDocument();
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: 'Alterar senha' })).toBeVisible();
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(trigger);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(trigger);
    fireEvent.pointerDown(document.body);
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('closes before invoking the selected account action', () => {
    const changePassword = vi.fn();
    const logout = vi.fn();
    render(<Header isSidebarOpen={true} setIsSidebarOpen={() => {}} activeTab="dashboard" setShowAlterarSenha={changePassword} handleLogout={logout} />);
    const trigger = screen.getByRole('button', { name: 'Menu da conta' });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('button', { name: 'Alterar senha' }));
    expect(changePassword).toHaveBeenCalledWith(true);
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole('button', { name: 'Encerrar sessão' }));
    expect(logout).toHaveBeenCalledOnce();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });
});
