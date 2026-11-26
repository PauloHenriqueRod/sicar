import { useEffect, useEffectEvent, useState } from 'react';
import { apiBaseUrl } from '../utils/api';
import type { SalaryPosition } from '../utils/salaryReferences';
import { formatCurrency } from '../utils/presentation';
import { Button, SelectField } from './ui';

interface Option { id: number; titulacao: string; posicao: SalaryPosition; vb: string; rt: string; fonte: string }
interface Page { itens: Option[]; total: number; tamanho_pagina: number }

export function DocentePositionLookup({ date, disabled, position, title, onApply, destination = false, base = '' }: {
  date: string; disabled: boolean; position: SalaryPosition; title: string;
  destination?: boolean; base?: string;
  onApply: (position: SalaryPosition, title: string, automatic?: boolean) => void;
}) {
  const [page, setPage] = useState(0);
  const [result, setResult] = useState<Page | null>(null);
  const [failed, setFailed] = useState(false);
  const [notice, setNotice] = useState('');
  const applyOrigin = useEffectEvent((value: SalaryPosition) => onApply(value, title, true));
  const { carreira, jornada, classe_docente, nivel_docente, versao_carreira, vinculo } = position;
  const [reference, setReference] = useState<{ key: string; item?: Option; note?: string }>();
  const targetKey = destination && date && carreira && jornada && classe_docente && nivel_docente && versao_carreira && vinculo && title.trim()
    ? new URLSearchParams({ data_referencia: date, carreira: String(carreira), jornada: String(jornada), classe_docente: String(classe_docente), nivel_docente: String(nivel_docente) }).toString() : '';
  const selectionKey = JSON.stringify([targetKey, versao_carreira, vinculo, title]);
  useEffect(() => {
    if (!targetKey) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(apiBaseUrl + '/api/tabelas/posicoes-docentes?' + targetKey, { credentials: 'include', signal: controller.signal });
        if (!response.ok) throw new Error();
        const data: Page = await response.json();
        const matches = data.itens.filter(r => r.posicao.versao_carreira === versao_carreira && r.posicao.vinculo === vinculo &&
          r.titulacao.trim().toLocaleLowerCase('pt-BR') === title.trim().toLocaleLowerCase('pt-BR'));
        if (!controller.signal.aborted) setReference({ key: selectionKey, ...(matches.length === 1 && data.itens.length === data.total
          ? { item: matches[0] } : { note: 'Confira o destino e a titulação. A busca não identificou uma única referência nessa data.' }) });
      } catch {
        if (!controller.signal.aborted) setReference({ key: selectionKey, note: 'Não foi possível consultar os valores de destino.' });
      }
    }, 300);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [targetKey, selectionKey, versao_carreira, vinculo, title]);
  useEffect(() => {
    if (destination || disabled || page || !date || (versao_carreira && vinculo) ||
        (!(classe_docente && nivel_docente) && !base)) return;
    const request = new AbortController();
    const params = new URLSearchParams({ data_referencia: date });
    for (const [key, value] of Object.entries({ carreira, jornada, classe_docente, nivel_docente })) {
      if (value) params.set(key, String(value));
    }
    if (!(classe_docente && nivel_docente)) params.set('vencimento_basico', base);
    async function resolve() {
      try {
        const response = await fetch(`${apiBaseUrl}/api/tabelas/posicoes-docentes?${params}`, { credentials: 'include', signal: request.signal });
        if (!response.ok) throw new Error();
        const data: Page = await response.json();
        if (request.signal.aborted) return;
        const candidates = data.itens.filter(row => (!vinculo || row.posicao.vinculo === vinculo) &&
          (!versao_carreira || row.posicao.versao_carreira === versao_carreira));
        const first = candidates[0]?.posicao;
        if (data.itens.length === data.total && first && candidates.every(row =>
          Object.keys(first).every(key => row.posicao[key] === first[key]))) {
          setNotice('');
          applyOrigin(first);
        } else setNotice('A tabela não identifica uma única posição para estes dados. Escolha a posição de origem.');
      } catch {
        if (!request.signal.aborted) setNotice('Não foi possível conferir a posição automaticamente. Consulte a tabela.');
      }
    }
    void resolve();
    return () => request.abort();
  }, [date, destination, disabled, page, carreira, jornada, classe_docente, nivel_docente, versao_carreira, vinculo, base]);
  useEffect(() => {
    if (!page || !date) return;
    const request = new AbortController();
    async function load() {
      try {
        const params = new URLSearchParams({ data_referencia: date, pagina: String(page) });
        const response = await fetch(`${apiBaseUrl}/api/tabelas/posicoes-docentes?${params}`, { credentials: 'include', signal: request.signal });
        if (!response.ok) throw new Error();
        const data: Page = await response.json();
        if (!Array.isArray(data.itens)) throw new Error();
        if (!request.signal.aborted) setResult(data);
      } catch {
        if (!request.signal.aborted) setFailed(true);
      }
    }
    void load();
    return () => request.abort();
  }, [page, date]);

  const show = (next: number) => { setFailed(false); setResult(null); setPage(next); };
  const matches = (current: unknown, proposed: unknown) => !String(current ?? '').trim() ||
    String(current).trim().toLocaleLowerCase('pt-BR') === String(proposed).trim().toLocaleLowerCase('pt-BR');
  const compatible = (item: Option) => matches(title, item.titulacao) && Object.entries(item.posicao).every(([key, v]) => matches(position[key], v));
  if (!page) return <>{notice && !versao_carreira && <p role="status" className="help-text">{notice}</p>}
    {reference?.key === selectionKey && <p role="status" className="help-text">{reference.item
      ? <>Destino em {date} · VB {formatCurrency(reference.item.vb)} · RT {formatCurrency(reference.item.rt)} ({reference.item.titulacao}) · {reference.item.fonte}</>
      : reference.note}</p>}
    <Button variant="quiet" disabled={disabled || !date} onClick={() => show(1)}>{destination ? 'Escolher referência de destino' : 'Consultar posições da tabela vigente'}</Button></>;
  return <div className="space-y-2">
    {failed ? <p role="alert">Não foi possível consultar a tabela. Feche a consulta e tente novamente.</p>
      : !result ? <p role="status">Consultando posições vigentes…</p>
      : !result.total ? <p role="status">Nenhuma posição docente com VB e RT confirmados nessa data. Confira o cadastro salarial.</p>
      : <><SelectField label={destination ? 'Referência de destino na data dos efeitos' : 'Completar posição e titulação pela tabela'} value="" disabled={disabled} onChange={event => {
        const item = result.itens.find(row => row.id === Number(event.target.value));
        if (!item || (destination && !matches(title, item.titulacao))) return;
        onApply({ ...item.posicao }, item.titulacao);
        show(0);
      }}><option value="">Escolha a posição conferida</option>{[...result.itens].sort((a, b) => Number(compatible(b)) - Number(compatible(a))).map(item => <option key={item.id} value={item.id} disabled={destination && !matches(title, item.titulacao)}>
          {item.posicao.carreira === 'EBTT' ? 'EBTT' : 'Magistério superior'} · {item.posicao.vinculo} · {item.posicao.jornada} · {item.posicao.versao_carreira} · {item.posicao.classe_docente} {item.posicao.nivel_docente} · {item.titulacao}
        </option>)}</SelectField>
        {result.total > result.tamanho_pagina && <div className="flex gap-2 items-center"><Button variant="quiet" disabled={disabled || page <= 1} onClick={() => show(page - 1)}>Anterior</Button><span>Página {page} de {Math.ceil(result.total / result.tamanho_pagina)}</span><Button variant="quiet" disabled={disabled || page * result.tamanho_pagina >= result.total} onClick={() => show(page + 1)}>Próxima</Button></div>}
      </>}
    <Button variant="quiet" onClick={() => show(0)}>Fechar consulta</Button>
  </div>;
}
