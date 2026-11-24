import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Button, Modal, TextField } from './index';

function Example() {
  const [open, setOpen] = useState(false);
  return <><Button onClick={() => setOpen(true)}>Abrir</Button>{open && <Modal title="Novo registro" onClose={() => setOpen(false)}><TextField label="Valor" /><Button>Salvar</Button></Modal>}</>;
}

describe('Shared modal behavior', () => {
  it('moves focus into the form, traps Tab and returns to the trigger on Escape', () => {
    const { container } = render(<Example />);
    const trigger = screen.getByRole('button', { name: 'Abrir' });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByLabelText('Valor')).toHaveFocus();
    expect(container.inert).toBe(true);
    screen.getByRole('button', { name: 'Salvar' }).focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(screen.getByRole('button', { name: 'Fechar janela' })).toHaveFocus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(screen.getByRole('button', { name: 'Salvar' })).toHaveFocus();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(container.inert).not.toBe(true);
  });

  it('blocks closing while busy and preserves edited values across state changes', () => {
    const close = vi.fn();
    const { rerender } = render(<Modal title="Registro" onClose={close}><TextField label="Valor" defaultValue="100" /></Modal>);
    fireEvent.change(screen.getByLabelText('Valor'), { target: { value: '200' } });
    rerender(<Modal title="Registro" busy onClose={close}><TextField label="Valor" defaultValue="100" disabled /></Modal>);
    fireEvent.keyDown(document, { key: 'Escape' });
    fireEvent.click(screen.getByRole('button', { name: 'Fechar janela' }));
    expect(close).not.toHaveBeenCalled();
    rerender(<Modal title="Registro" onClose={close}><TextField label="Valor" defaultValue="100" /></Modal>);
    expect(screen.getByLabelText('Valor')).toHaveValue('200');
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(close).toHaveBeenCalledOnce();
  });

  it('keeps focus inside the dialog when a submitted form is replaced by confirmation', () => {
    const { rerender } = render(<Modal title="Registro" onClose={() => {}}><TextField label="Valor" /></Modal>);
    expect(screen.getByLabelText('Valor')).toHaveFocus();
    rerender(<Modal title="Registro" onClose={() => {}}><p role="status">Salvo.</p></Modal>);
    expect(screen.getByRole('dialog')).toHaveFocus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(screen.getByRole('button', { name: 'Fechar janela' })).toHaveFocus();
  });
});
