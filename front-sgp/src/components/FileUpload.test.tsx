import type { ComponentProps } from 'react';
import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { FileUpload } from './FileUpload';
import type { CalculationAttachment } from '../utils/calculationAttachments';
import type { TipoCalculo } from '../types';

function Workspace({ disabled = false }: { disabled?: boolean }) {
  const [attachments, setAttachments] = useState<CalculationAttachment[]>([]);
  return <FileUpload tipoCalculo="rescisao" setTipoCalculo={() => {}} attachments={attachments} setAttachments={setAttachments} isUploading={disabled} onSubmit={event => event.preventDefault()} />;
}

describe('FileUpload Component', () => {
  it('renders without crashing', () => {
    const props: ComponentProps<typeof FileUpload> = { tipoCalculo: null, setTipoCalculo: () => {}, attachments: [], setAttachments: () => {}, isUploading: false, onSubmit: () => {} };
    const { container } = render(<FileUpload {...props} />);
    expect(container.firstChild).not.toBeNull();
  });

  it.each(['apuracao_periodos', 'progressao', 'insalubridade', 'substituicao', 'rescisao', 'abono', 'exercicio_anterior'] as TipoCalculo[])('shows optional categorized inputs for %s', tipoCalculo => {
    render(<FileUpload tipoCalculo={tipoCalculo} setTipoCalculo={() => {}} attachments={[]} setAttachments={() => {}} isUploading={false} onSubmit={event => event.preventDefault()} />);
    expect(screen.getByRole('group', { name: 'Ficha Financeira' })).toBeVisible();
    expect(screen.getByRole('group', { name: tipoCalculo === 'progressao' ? 'Ata de progressão' : 'Ata ou outro documento de apoio' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Continuar para revisão' })).toBeEnabled();
    expect(screen.getByLabelText('Selecionar PDFs — Ficha Financeira')).not.toBeRequired();
    expect(screen.queryByLabelText('Selecionar documentos PDF')).not.toBeInTheDocument();
  });


  it('keeps sections independent, appends annual statements and removes only the chosen file', () => {
    render(<Workspace />);
    const add = (label: string, name: string) => fireEvent.change(screen.getByLabelText(label), { target: { files: [new File(['sintético'], name, { lastModified: 1 })] } });
    add('Selecionar PDFs — Ficha Financeira', 'ficha-2025.pdf');
    add('Selecionar PDFs — Cadastro funcional', 'cadastro.pdf');
    add('Selecionar PDFs — Ficha Financeira', 'ficha-2026.pdf');
    const financial = screen.getByRole('group', { name: 'Ficha Financeira' });
    const registration = screen.getByRole('group', { name: 'Cadastro funcional' });
    expect(within(financial).getByText('ficha-2025.pdf')).toBeVisible();
    expect(within(financial).getByText('ficha-2026.pdf')).toBeVisible();
    expect(within(financial).queryByText('cadastro.pdf')).not.toBeInTheDocument();
    expect(within(registration).getByText('cadastro.pdf')).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Remover ficha-2025.pdf de Ficha Financeira' }));
    expect(screen.queryByText('ficha-2025.pdf')).not.toBeInTheDocument();
    expect(screen.getByText('ficha-2026.pdf')).toBeVisible();
    expect(screen.getByText('cadastro.pdf')).toBeVisible();
    add('Selecionar PDFs — Ficha Financeira', 'ficha-2025.pdf');
    expect(screen.getByText('ficha-2025.pdf')).toBeVisible();
  });

  it('assigns dropped files only to their section and ignores duplicates and non-PDF files', () => {
    render(<Workspace />);
    const document = new File(['sintético'], 'cadastro.pdf', { lastModified: 1 });
    fireEvent.drop(screen.getByRole('group', { name: 'Cadastro funcional' }), { dataTransfer: { files: [document] } });
    fireEvent.change(screen.getByLabelText('Selecionar PDFs — Ficha Financeira'), { target: { files: [document, new File(['x'], 'invalido.txt')] } });
    expect(screen.getAllByText('cadastro.pdf')).toHaveLength(1);
    expect(within(screen.getByRole('group', { name: 'Ficha Financeira' })).queryByRole('list')).not.toBeInTheDocument();
    expect(screen.queryByText('invalido.txt')).not.toBeInTheDocument();
    expect(screen.getByText(/Arquivos repetidos ou que não são PDF/)).toBeVisible();
  });

  it('does not accept dropped files during extraction', () => {
    const change = vi.fn();
    render(<FileUpload tipoCalculo="rescisao" setTipoCalculo={() => {}} attachments={[]} setAttachments={change} isUploading={true} onSubmit={() => {}} />);
    fireEvent.drop(screen.getByRole('group', { name: 'Cadastro funcional' }), { dataTransfer: { files: [new File(['x'], 'cadastro.pdf')] } });
    expect(change).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Selecionar PDFs — Cadastro funcional')).toBeDisabled();
  });
});
