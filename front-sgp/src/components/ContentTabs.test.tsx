import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ContentTabs } from './ContentTabs';

function Example() {
  const [tab, setTab] = useState<'first' | 'second' | 'third'>('first');
  return <ContentTabs label="Categorias" value={tab} onChange={setTab} items={[
    { id: 'first', label: 'Primeira', content: <input aria-label="Rascunho" defaultValue="" /> },
    { id: 'second', label: 'Segunda', content: <p>Conteúdo secundário</p> },
    { id: 'third', label: 'Terceira', content: <p>Conteúdo final</p> },
  ]} />;
}

describe('ContentTabs', () => {
  it('shows only the selected panel and preserves drafts when switching categories', () => {
    render(<Example />);
    const draft = screen.getByRole('textbox', { name: 'Rascunho' });
    fireEvent.change(draft, { target: { value: 'Dados em revisão' } });
    fireEvent.click(screen.getByRole('tab', { name: 'Segunda' }));
    expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
    expect(screen.getByRole('tabpanel')).toHaveAccessibleName('Segunda');
    expect(draft).not.toBeVisible();
    fireEvent.click(screen.getByRole('tab', { name: 'Primeira' }));
    expect(screen.getByRole('textbox', { name: 'Rascunho' })).toHaveValue('Dados em revisão');
  });

  it('supports arrows, wrapping, Home and End with focus following selection', () => {
    render(<Example />);
    const first = screen.getByRole('tab', { name: 'Primeira' });
    const second = screen.getByRole('tab', { name: 'Segunda' });
    const third = screen.getByRole('tab', { name: 'Terceira' });
    first.focus();
    fireEvent.keyDown(first, { key: 'ArrowLeft' });
    expect(third).toHaveFocus();
    expect(third).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(third, { key: 'ArrowRight' });
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: 'ArrowRight' });
    expect(second).toHaveFocus();
    fireEvent.keyDown(second, { key: 'End' });
    expect(third).toHaveFocus();
    fireEvent.keyDown(third, { key: 'Home' });
    expect(first).toHaveFocus();
    expect(first).toHaveAttribute('tabindex', '0');
    expect(second).toHaveAttribute('tabindex', '-1');
  });
});
