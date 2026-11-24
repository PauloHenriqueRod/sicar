import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Button, Pagination, TextField, SelectField } from './index';

describe('Shared controls behavior', () => {
  it('requires an explicit submit action inside a form and blocks repeated actions while busy', () => {
    const submit = vi.fn(event => event.preventDefault());
    const { rerender } = render(<form onSubmit={submit}><Button>Salvar</Button></form>);
    fireEvent.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(submit).not.toHaveBeenCalled();
    rerender(<form onSubmit={submit}><Button type="submit" busy>Salvando...</Button></form>);
    const pending = screen.getByRole('button', { name: 'Salvando...' });
    expect(pending).toHaveAttribute('aria-busy', 'true');
    fireEvent.click(pending);
    expect(submit).not.toHaveBeenCalled();
    rerender(<form onSubmit={submit}><Button type="submit">Salvar</Button></form>);
    fireEvent.click(screen.getByRole('button', { name: 'Salvar' }));
    expect(submit).toHaveBeenCalledOnce();
  });

  it('associates labels, hints and errors with their own native controls', () => {
    render(<><TextField label="Valor" hint="Informe em reais." error="Confira o valor." /><TextField label="Valor" hint="Valor recebido." /><SelectField label="Perfil" hint="Escolha um acesso." defaultValue="user"><option value="user">Servidor</option></SelectField></>);
    const [first, second] = screen.getAllByLabelText('Valor');
    expect(first.id).not.toBe(second.id);
    expect(first).toHaveAttribute('aria-invalid', 'true');
    for (const control of [first, second, screen.getByLabelText('Perfil')]) {
      for (const id of control.getAttribute('aria-describedby')!.split(' ')) {
        expect(document.getElementById(id)).toBeVisible();
      }
    }
    expect(first).toHaveAccessibleDescription('Informe em reais. Confira o valor.');
    expect(second).toHaveAccessibleDescription('Valor recebido.');
  });

  it('limits pagination to valid pages and disables navigation during an operation', () => {
    const change = vi.fn();
    const props = { page: 1, pageCount: 2, onPageChange: change, label: 'do histórico' };
    const { rerender } = render(<Pagination {...props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Página anterior do histórico' }));
    expect(change).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Próxima página do histórico' }));
    expect(change).toHaveBeenLastCalledWith(2);
    rerender(<Pagination {...props} page={2} />);
    expect(screen.getByRole('button', { name: 'Próxima página do histórico' })).toBeDisabled();
    rerender(<Pagination {...props} disabled />);
    expect(screen.getByRole('button', { name: 'Próxima página do histórico' })).toBeDisabled();
    rerender(<Pagination {...props} pageCount={1} />);
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });
});
