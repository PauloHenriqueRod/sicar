import type { ComponentProps } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ResultadoCalculo } from './ResultadoCalculo';

describe('ResultadoCalculo Component', () => {
  it('renders without crashing', () => {
    const props: ComponentProps<typeof ResultadoCalculo> = { data: { dados_extraidos: {}, resultado_calculo: {} }, isExporting: false, onExportPDF: () => {}, onReset: () => {} };
    const { container } = render(<ResultadoCalculo {...props} />);
    expect(container.firstChild).not.toBeNull();
  });

  it.each([
    { total_a_receber: 1500, dias_substituicao: 30 },
    { resultado_calculo: { total_a_receber: 1500, dias_substituicao: 30 } },
  ])('shows the total before the breakdown for supported API responses', (resultado) => {
    render(<ResultadoCalculo data={{ dados_extraidos: {}, resultado_calculo: resultado }} isExporting={false} onExportPDF={() => {}} onReset={() => {}} />);
    const total = screen.getByText('R$ 1.500,00');
    const breakdown = screen.getByRole('heading', { name: 'Detalhamento do cálculo' });
    expect(total.compareDocumentPosition(breakdown) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(total).toBeVisible();
    expect(screen.getByRole('button', { name: 'Baixar PDF' })).toBeVisible();
    expect(screen.getByText('30')).not.toBeVisible();
    fireEvent.click(breakdown.closest('summary')!);
    expect(screen.getByText('30')).toBeVisible();
  });

  it('shows a zero proportional total once in the summary', () => {
    render(<ResultadoCalculo data={{ dados_extraidos: {}, resultado_calculo: { valor_proporcional_devido: 0 } }} isExporting={false} onExportPDF={() => {}} onReset={() => {}} />);
    expect(screen.getAllByText('R$ 0,00')).toHaveLength(1);
  });

  it('uses the server total and explains the rounding difference visibly', () => {
    const note = 'O total utiliza a precisão interna das parcelas, antes do arredondamento.';
    render(<ResultadoCalculo data={{ dados_extraidos: {}, resultado_calculo: {
      total_acumulado: 0.03, detalhamento_mensal: [{ valor_calculado: 0.02 }, { valor_calculado: 0.02 }],
      politica_arredondamento: 'decimal_half_up_final_v3', nota_arredondamento: note,
    } }} isExporting={false} onExportPDF={() => {}} onReset={() => {}} />);
    expect(document.querySelector('.financial-total')).toHaveTextContent('R$ 0,03');
    expect(screen.getByText(note)).toBeVisible();
    expect(screen.queryByText('decimal_half_up_final_v3')).not.toBeInTheDocument();
  });

  it.each([
    { total_geral_devido: 100, reflexo_ferias: 33.33, reflexo_decimo_terceiro: 100, total_com_reflexos: 233.33 },
    { resultado_calculo: { resumo_consolidado: { total_geral_a_receber: 233.33 } } },
  ])('highlights the final total for progression and previous-year calculations', resultado => {
    render(<ResultadoCalculo data={{ dados_extraidos: {}, resultado_calculo: resultado }} isExporting={false} onExportPDF={() => {}} onReset={() => {}} />);
    expect(document.querySelector('.financial-total')).toHaveTextContent('R$ 233,33');
  });
});
