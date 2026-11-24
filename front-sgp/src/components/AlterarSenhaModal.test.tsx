import type { ComponentProps } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { AlterarSenhaModal } from './AlterarSenhaModal';

describe('AlterarSenhaModal Component', () => {
  it('renders without crashing', () => {
    const props: ComponentProps<typeof AlterarSenhaModal> = { onClose: () => {} };
    render(<AlterarSenhaModal {...props} />);
    expect(screen.getByRole('dialog', { name: 'Alterar senha' })).toBeVisible();
    expect(screen.getByLabelText('Senha atual')).toHaveFocus();
  });
});
