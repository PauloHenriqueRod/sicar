import { useId } from 'react';
import { Button, SelectField } from './ui';
import { FileText, ArrowRight } from 'lucide-react';
import type { TipoCalculo } from '../types';
import type { CalculationAttachment } from '../utils/calculationAttachments';
import { SectionHeader } from './SectionHeader';
import { DocumentAttachments } from './DocumentAttachments';
import { calculationLabels } from '../utils/presentation';

interface FileUploadProps {
  tipoCalculo: TipoCalculo | null;
  setTipoCalculo: (tipo: TipoCalculo | null) => void;
  attachments: CalculationAttachment[];
  setAttachments: (attachments: CalculationAttachment[]) => void;
  isUploading: boolean;
  onSubmit: (e: React.FormEvent) => void;
}

export function FileUpload({ tipoCalculo, setTipoCalculo, attachments, setAttachments, isUploading, onSubmit }: FileUploadProps) {
  const typeId = useId();
  return <div className="surface w-full max-w-3xl p-6 sm:p-8">
    <SectionHeader title="Documentos do servidor" icon={FileText} description="Selecione o cálculo e adicione as fontes de um servidor por vez." />
    <div className="mb-6">
      <SelectField label="Tipo de cálculo" id={typeId} disabled={isUploading} value={tipoCalculo || ''} onChange={e => setTipoCalculo(e.target.value as TipoCalculo)}>
        <option value="" disabled>Selecione uma opção...</option>
        {Object.entries(calculationLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </SelectField>
    </div>
    {tipoCalculo && <form onSubmit={onSubmit} className="space-y-6">
      <DocumentAttachments key={tipoCalculo} tipoCalculo={tipoCalculo} attachments={attachments} onChange={setAttachments} disabled={isUploading} />
      <p role="status" aria-atomic="true" className="help-text">{attachments.length ? `${attachments.length} ${attachments.length === 1 ? 'documento selecionado' : 'documentos selecionados'} para este cálculo.` : 'PDFs e portarias são opcionais. Sem arquivo ou sem layout suportado, preencha os dados conferidos pelo RH.'}</p>
      <Button type="submit" busy={isUploading} disabled={isUploading} className="w-full">
        {isUploading ? 'Extraindo dados...' : <>Continuar para revisão<ArrowRight className="w-5 h-5 shrink-0" aria-hidden="true" /></>}
      </Button>
    </form>}
  </div>;
}
