import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { GestaoUsuarios } from './GestaoUsuarios';

describe('GestaoUsuarios Component', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('renders without crashing', () => {
    const { container } = render(<GestaoUsuarios />);
    expect(container.firstChild).not.toBeNull();
  });

  it.each([true, false])('reports user creation accurately when the subsequent list refresh succeeds: %s', async (refreshSucceeds) => {
    let reads = 0;
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, options?: RequestInit) => {
      if (options?.method === 'POST') return new Response('{}', { status: 201 });
      reads++;
      return new Response('[]', { status: reads > 1 && !refreshSucceeds ? 500 : 200 });
    }));
    render(<GestaoUsuarios />);
    fireEvent.click(screen.getByText('Cadastrar usuário', { selector: 'summary span' }).closest('summary')!);
    fireEvent.change(screen.getByLabelText('Login'), { target: { value: 'equipe-teste' } });
    fireEvent.change(screen.getByLabelText('Senha inicial'), { target: { value: 'Acesso1!' } });
    expect(screen.getByText('Use pelo menos 8 caracteres, uma letra maiúscula, um número e um caractere especial.')).not.toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Cadastrar usuário' }));
    if (refreshSucceeds) expect(await screen.findByText('Usuário criado.')).toBeVisible();
    else {
      expect(await screen.findByText('Usuário criado. A lista não foi atualizada.')).toBeVisible();
      expect(screen.getByRole('status')).toHaveTextContent('Não é necessário cadastrar novamente.');
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(vi.mocked(fetch).mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1);
    }
    expect(screen.getByLabelText('Login')).toHaveValue('');
    expect(screen.getByLabelText('Senha inicial')).toHaveValue('');
  });

  it('confirms password reset in the page after the API succeeds', async () => {
    vi.stubGlobal('prompt', vi.fn(() => 'Acesso1!'));
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, options?: RequestInit) => new Response(options?.method === 'PUT' ? '{}' : JSON.stringify([{ id: 1, username: 'equipe-teste', role: 'user' }]), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    render(<GestaoUsuarios />);
    fireEvent.click(await screen.findByRole('button', { name: 'Redefinir senha' }));
    expect(await screen.findByText('Senha do usuário redefinida.')).toBeVisible();
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'PUT')).toBe(true);
    expect(screen.getByRole('button', { name: 'Redefinir senha' })).toBeEnabled();
  });
});
