import { useId, useState } from 'react';
import { FileText, X } from 'lucide-react';
import type { TipoCalculo } from '../types';
import { attachmentSections } from '../utils/calculationAttachments';
import type { CalculationAttachment } from '../utils/calculationAttachments';

interface Props {
  tipoCalculo: TipoCalculo;
  attachments: CalculationAttachment[];
  onChange: (attachments: CalculationAttachment[]) => void;
  disabled?: boolean;
}

const fileKey = (file: File) => JSON.stringify([file.name, file.size, file.lastModified]);

export function DocumentAttachments({ tipoCalculo, attachments, onChange, disabled = false }: Props) {
  const id = useId();
  const [notice, setNotice] = useState('');
  const add = (category: string, selected: File[]) => {
    if (disabled) return;
    const keys = new Set(attachments.map(item => fileKey(item.file)));
    const additions: CalculationAttachment[] = [];
    let skipped = 0;
    for (const file of selected) {
      const key = fileKey(file);
      if (!/\.pdf$/i.test(file.name) || keys.has(key)) { skipped++; continue; }
      keys.add(key);
      additions.push({ category, file });
    }
    onChange([...attachments, ...additions]);
    setNotice(skipped ? 'Arquivos repetidos ou que não são PDF não foram adicionados. Para mudar a seção de um arquivo, remova-o primeiro.' : '');
  };

  return <section aria-label="Anexos por tipo de documento" className="space-y-4">
    <p className="help-text">Um servidor e um vínculo por cálculo. Separe os PDFs nas seções abaixo; todos são opcionais. Você pode incluir mais de um arquivo por seção.</p>
    {tipoCalculo === 'substituicao' && <p className="help-text">Documentos do titular podem apoiar este processo. Confira o papel de cada pessoa na revisão; o cálculo é do substituto.</p>}
    <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 18rem), 1fr))' }}>
      {attachmentSections[tipoCalculo].map(section => {
        const files = attachments.filter(item => item.category === section.id);
        const inputId = `${id}-${section.id}`;
        return <fieldset key={section.id} disabled={disabled} className="min-w-0 rounded-lg border border-outline p-4 space-y-3" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); event.stopPropagation(); add(section.id, Array.from(event.dataTransfer.files)); }}>
          <legend className="px-1 font-semibold text-ink">{section.title}</legend>
          <p id={`${inputId}-help`} className="help-text">{section.description}</p>
          <label htmlFor={inputId} className="field-label">Selecionar PDFs — {section.title}</label>
          <input id={inputId} type="file" multiple accept=".pdf,application/pdf" aria-describedby={`${inputId}-help`} className="block w-full min-w-0 text-sm text-ink file:mr-2 file:rounded file:border-0 file:bg-panel file:px-3 file:py-2 file:text-ink" onChange={event => { add(section.id, Array.from(event.target.files ?? [])); event.target.value = ''; }} />
          <p className="help-text">Opcional · Também é possível arrastar os PDFs para esta seção.</p>
          {files.length > 0 && <ul className="space-y-2" aria-label={`Selecionados — ${section.title}`}>
            {files.map(item => <li key={fileKey(item.file)} className="flex items-center gap-2 rounded bg-panel p-2 text-sm">
              <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="min-w-0 flex-1 break-words">{item.file.name}</span>
              <button type="button" aria-label={`Remover ${item.file.name} de ${section.title}`} onClick={() => { onChange(attachments.filter(candidate => candidate !== item)); setNotice(''); }} className="rounded p-1 text-danger hover:bg-danger-soft disabled:opacity-40"><X className="h-4 w-4" aria-hidden="true" /></button>
            </li>)}
          </ul>}
        </fieldset>;
      })}
    </div>
    {notice && <p role="status" className="help-text">{notice}</p>}
  </section>;
}
