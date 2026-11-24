import type { ComponentProps } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { RevisaoDadosForm } from './RevisaoDadosForm';
import { emptyPeriodPlan } from '../utils/periodReviewData';

describe('RevisaoDadosForm Component', () => {
  it('associa erros da apuração aos campos exatos e abre a coleção com erro', () => {
    const props: ComponentProps<typeof RevisaoDadosForm> = {
      data: { dados_extraidos: { apuracao: { ...emptyPeriodPlan(),
        eventos: [{ id: 'E1', alteracoes: { posicao: { carreira: 'TAE' } } }],
        recebidos: [{ id: 'P1' }, { id: 'P2' }],
      } }, resultado_calculo: null },
      isCalculated: false, isUploading: false, onCalculate: vi.fn(), handleChangeData: vi.fn(),
      fieldErrors: {
        '["apuracao","periodo","inicio"]': 'Confira o início.',
        '["apuracao","estado_inicial","posicao","jornada"]': 'Confira a jornada inicial.',
        '["apuracao","eventos",0,"alteracoes","posicao","padrao_tae"]': 'Confira o novo padrão.',
        '["apuracao","recebidos",1,"valor"]': 'Confira o segundo pagamento.',
        '["apuracao","recebidos",1,"natureza_rubrica"]': 'Confira a natureza.',
      },
    };
    const { rerender } = render(<RevisaoDadosForm {...props} />);
    expect(screen.getByLabelText('Início da apuração')).toHaveAccessibleDescription('Confira o início.');
    const initial = screen.getByRole('group', { name: 'Situação no início do período' });
    expect(within(initial).getByLabelText('Jornada ou regime')).toHaveAttribute('aria-invalid', 'true');
    const event = screen.getByRole('group', { name: 'Mudanças no período: registro 1' });
    expect(event.closest('details')).toHaveAttribute('open');
    expect(within(event).getByLabelText('Padrão TAE')).toHaveAccessibleDescription('Confira o novo padrão.');
    const first = screen.getByRole('group', { name: 'Recebimentos: registro 1' });
    const second = screen.getByRole('group', { name: 'Recebimentos: registro 2' });
    expect(second.closest('details')).toHaveAttribute('open');
    expect(within(first).getByLabelText('Valor recebido ou estornado (positivo)')).not.toHaveAttribute('aria-invalid', 'true');
    expect(within(second).getByLabelText('Valor recebido ou estornado (positivo)')).toHaveAccessibleDescription('Confira o segundo pagamento.');
    expect(within(second).getByLabelText('Natureza da rubrica')).toHaveAttribute('aria-invalid', 'true');
    rerender(<RevisaoDadosForm {...props} fieldErrors={{}} />);
    expect(screen.queryByText('Confira o segundo pagamento.')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Início da apuração')).not.toHaveAttribute('aria-invalid', 'true');
    expect(second.closest('details')).toHaveAttribute('open');
  });

  it('mostra pendências de grupo junto à apuração e às regras do registro', () => {
    render(<RevisaoDadosForm data={{ dados_extraidos: { apuracao: {
      ...emptyPeriodPlan(), rubricas: [{ regra: {} }],
    } }, resultado_calculo: null }} isCalculated={false} isUploading={false}
      onCalculate={vi.fn()} handleChangeData={vi.fn()} fieldErrors={{
        '["apuracao"]': 'Referência salarial pendente.',
        '["apuracao","rubricas",0,"regra"]': 'Confira a regra deste registro.',
      }} />);
    expect(screen.getByText('Referência salarial pendente.')).toHaveAttribute('role', 'alert');
    const rubric = screen.getByRole('group', { name: 'Rubricas devidas: registro 1' });
    expect(within(rubric).getByText('Confira a regra deste registro.')).toBeVisible();
  });
  it('renders without crashing', () => {
    const props: ComponentProps<typeof RevisaoDadosForm> = { data: { dados_extraidos: {}, resultado_calculo: null }, isCalculated: false, isUploading: false, onCalculate: () => {}, handleChangeData: () => {} };
    const { container } = render(<RevisaoDadosForm {...props} />);
    expect(container.firstChild).not.toBeNull();
  });

  it('lets users correct annual contribution values while preserving their year and index', () => {
    const handleChangeData = vi.fn();
    const props: ComponentProps<typeof RevisaoDadosForm> = { data: { dados_extraidos: { nome: 'Servidor', mes: null, dias_interrupcao: 0, valores_anuais: { '2025': [750.25, 800] } }, resultado_calculo: null }, isCalculated: false, isUploading: false, onCalculate: vi.fn(), handleChangeData };
    const { rerender } = render(<RevisaoDadosForm {...props} />);
    expect(screen.getByLabelText('Nome do servidor')).toHaveValue('Servidor');
    expect(screen.getByLabelText('Mês de referência')).toHaveValue('');
    expect(screen.getByLabelText('Mês de referência')).toHaveAccessibleDescription('Informe de 1 (janeiro) a 12 (dezembro).');
    expect(screen.getByLabelText('Dias de interrupção')).toHaveValue('0');
    const value = screen.getByLabelText('Valor 2 de 2025 (R$)');
    expect(value).toHaveValue('800');
    fireEvent.change(value, { target: { value: '850.50' } });
    expect(handleChangeData).toHaveBeenCalledWith(['valores_anuais', '2025', 1], '850.50');
    rerender(<RevisaoDadosForm {...props} isUploading />);
    expect(screen.getByLabelText('Valor 2 de 2025 (R$)')).toBeDisabled();
  });

  it('keeps nested period fields and unfamiliar data editable with readable labels', () => {
    const handleChangeData = vi.fn();
    render(<RevisaoDadosForm data={{ dados_extraidos: { fluxo_mensal: [{ periodo: '2025-01', v_dev: 1500, v_rec: 1000 }], campo_adicional: 'Conferir' }, resultado_calculo: null }} isCalculated={false} isUploading={false} onCalculate={vi.fn()} handleChangeData={handleChangeData} />);
    expect(screen.getByLabelText('Período de referência')).toHaveValue('2025-01');
    fireEvent.change(screen.getByLabelText('Valor devido (R$)'), { target: { value: '1600' } });
    expect(handleChangeData).toHaveBeenCalledWith(['fluxo_mensal', 0, 'v_dev'], '1600');
    fireEvent.change(screen.getByLabelText('Campo adicional'), { target: { value: 'Confirmado' } });
    expect(handleChangeData).toHaveBeenCalledWith(['campo_adicional'], 'Confirmado');
  });
});
