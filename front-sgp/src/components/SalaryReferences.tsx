import { useCallback, useEffect, useState } from 'react';
import { Settings2 } from 'lucide-react';
import { Button, FilterBar, Modal, PagePanel, Pagination, SelectField, TableViewport, TextField } from './ui';
import { SalaryPositionFields } from './SalaryPositionFields';
import { emptySalaryPosition, serializeSalaryPosition } from '../utils/salaryReferences';
import type { SalaryPosition } from '../utils/salaryReferences';
import { ActionFeedback } from './ActionFeedback';
import type { Feedback } from './ActionFeedback';
import { apiBaseUrl } from '../utils/api';
import { formatCurrency } from '../utils/presentation';
import { OfficialSources } from './OfficialSources';

type Reference = {
  carreira: string; vinculo: string; jornada: string; versao_carreira: string;
  classificacao_tae: string | null; capacitacao_tae: string | null; padrao_tae: number | null;
  classe_docente: string | null; nivel_docente: number | null;
  estrutura_id: number; conferido_em: string | null; id: number; inicio_vigencia: string; fim_vigencia: string | null; fonte: string; estado: string; vencimento_basico: string; retribuicoes: { titulacao: string; valor: string }[] };
type Pending = { id: number; tabela_origem: string; id_origem: number; valor_original: string; motivo: string; referencia_id: number | null };
async function request(path: string, init?: RequestInit) {
  const response = await fetch(`${apiBaseUrl}/api/tabelas/${path}`, { ...init, credentials: 'include', headers: { 'Content-Type': 'application/json' } });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Confira os campos e tente novamente.');
  return result;
}
export function SalaryReferences() {
  const [references, setReferences] = useState<Reference[]>([]);
  const [pending, setPending] = useState<Pending[]>([]);
  const [view, setView] = useState('referencias');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [date, setDate] = useState('');
  const [state, setState] = useState('');
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [form, setForm] = useState<SalaryPosition | null>(null);
  const [rt, setRt] = useState<{ titulacao: string; valor: string }[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [link, setLink] = useState<{ id: number; referencia: string } | null>(null);
  const load = useCallback(async (signal?: AbortSignal) => {
    if (signal?.aborted) return;
    setBusy(true);
    try {
      const query = new URLSearchParams({ pagina: String(page), tamanho_pagina: '20' });
      if (view === 'referencias') { if (date) query.set('data_referencia', date); if (state) query.set('estado', state); }
      const result = await request(`${view}?${query}`, { signal });
      if (signal?.aborted) return;
      if (view === 'referencias') setReferences(result.itens); else setPending(result.itens);
      setTotal(result.total);
    } catch (error) { if (!signal?.aborted) setFeedback({ tone: 'error', message: (error as Error).message }); }
    finally { if (!signal?.aborted) setBusy(false); }
  }, [view, page, date, state]);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.resolve().then(() => load(controller.signal));
    return () => controller.abort();
  }, [load]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!form) return;
    setBusy(true); setFeedback(null);
    try {
      await request(editing ? `referencias/${editing}` : 'referencias', { method: editing ? 'PUT' : 'POST', body: JSON.stringify({
        ...serializeSalaryPosition(form), fim_vigencia: form.fim_vigencia || null, retribuicoes: form.carreira === 'TAE' ? [] : rt,
      }) });
      setForm(null); setFeedback({ tone: 'success', message: 'Referência salarial salva.' }); await load();
    } catch (error) { setFeedback({ tone: 'error', message: (error as Error).message }); }
    finally { setBusy(false); }
  }
  function edit(item?: Reference) {
    setEditing(item?.id ?? null); setRt(item?.retribuicoes ?? []);
    if (item) {
      const { id: _id, retribuicoes: _rt, estrutura_id: _structure, conferido_em: _checked, ...fields } = item;
      void _id; void _rt; void _structure; void _checked;
      setForm(fields);
    } else setForm({ ...emptySalaryPosition(), inicio_vigencia: '', fim_vigencia: '', vencimento_basico: '', fonte: '', estado: 'PENDENTE' });
  }
  async function bind(event: React.FormEvent) {
    event.preventDefault(); if (!link) return;
    setBusy(true);
    try {
      await request(`pendencias-legadas/${link.id}/vinculo`, { method: 'PUT', body: JSON.stringify({ referencia_id: Number(link.referencia) }) });
      setLink(null); setFeedback({ tone: 'success', message: 'Correspondência legada registrada.' }); await load();
    } catch (error) { setFeedback({ tone: 'error', message: (error as Error).message }); }
    finally { setBusy(false); }
  }
  return <PagePanel title="Referências salariais por vigência" icon={Settings2} feedback={feedback}
    description="Somente referências confirmadas são consultadas. A documentação e o direito são conferidos pelo RH."
    actions={<Button disabled={busy} onClick={() => edit()}>Nova referência salarial</Button>}>
    <details className="mb-6"><summary className="font-semibold cursor-pointer">Importar fontes oficiais e conferir cobertura</summary><div className="mt-6"><OfficialSources /></div></details>
    <FilterBar>
      <SelectField label="Consultar" value={view} onChange={e => { setView(e.target.value); setPage(1); }}><option value="referencias">Referências qualificadas</option><option value="pendencias-legadas">Pendências do cadastro legado</option></SelectField>
      {view === 'referencias' && <><TextField label="Vigente na data" type="date" value={date} onChange={e => { setDate(e.target.value); setPage(1); }} />
        <SelectField label="Estado da referência" value={state} onChange={e => { setState(e.target.value); setPage(1); }}><option value="">Todos</option>{['CONFIRMADA', 'PENDENTE', 'INATIVA'].map(s => <option key={s}>{s}</option>)}</SelectField></>}
      <Button variant="secondary" disabled={busy} onClick={() => void load()}>Atualizar referências</Button>
    </FilterBar>
    {busy && <p role="status">Carregando referências...</p>}
    <TableViewport label="Referências e pendências salariais"><table className="w-full text-sm"><thead><tr>{(view === 'referencias' ? ['ID / carreira', 'Vínculo / jornada', 'Posição / estrutura histórica', 'Vigência', 'VB / RT', 'Estado', 'Ação'] : ['ID / origem', 'Valor original', 'Pendência', 'Referência vinculada', 'Ação']).map(h => <th key={h} className="p-3 text-left">{h}</th>)}</tr></thead>
      <tbody>{view === 'referencias' ? references.map(item => <tr key={item.id} className="border-t border-outline">
        <td className="p-3">#{item.id} {item.carreira}</td><td>{item.vinculo} / {item.jornada}</td>
        <td>{item.carreira === 'TAE' ? `${item.classificacao_tae} / ${item.capacitacao_tae ?? '—'} / ${item.padrao_tae}` : `${item.classe_docente} / ${item.nivel_docente}`}<br />{item.versao_carreira}</td>
        <td>{item.inicio_vigencia} até {item.fim_vigencia ?? 'em aberto'}</td><td>VB {formatCurrency(Number(item.vencimento_basico))}{item.retribuicoes.map(r => <p key={r.titulacao}>{r.titulacao}: {formatCurrency(Number(r.valor))}</p>)}</td><td>{item.estado}</td>
        <td><Button variant="quiet" disabled={busy} onClick={() => edit(item)}>Editar referência {item.id}</Button></td>
      </tr>) : pending.map(item => <tr key={item.id} className="border-t border-outline"><td className="p-3">#{item.id} {item.tabela_origem} #{item.id_origem}</td><td>{item.valor_original}</td><td>{item.motivo}</td><td>{item.referencia_id ?? 'Pendente'}</td><td><Button variant="quiet" disabled={busy} onClick={() => setLink({ id: item.id, referencia: '' })}>Vincular pendência {item.id}</Button></td></tr>)}</tbody></table></TableViewport>
    {!busy && total === 0 && <p className="help-text mt-4">Nenhum registro encontrado.</p>}
    <Pagination page={page} pageCount={Math.ceil(total / 20)} label="referências" onPageChange={setPage} disabled={busy} />
    {form && <Modal title={editing ? 'Editar referência salarial' : 'Nova referência salarial'} size="medium" busy={busy} onClose={() => setForm(null)}>
      <form onSubmit={save} className="p-6 space-y-5">{feedback?.tone === 'error' && <ActionFeedback feedback={feedback} />}<SalaryPositionFields value={form} onChange={setForm} disabled={busy} />
        <div className="form-grid">{[['inicio_vigencia', 'Início da vigência', 'date'], ['fim_vigencia', 'Fim da vigência (opcional)', 'date'], ['vencimento_basico', 'Vencimento básico (decimal com ponto)', 'text'], ['fonte', 'Fonte e identificação da tabela conferida', 'text']].map(([key, label, type]) => <TextField key={key} label={label} type={type} required={key !== 'fim_vigencia'} disabled={busy} value={form[key] ?? ''} onChange={e => setForm({ ...form, [key]: e.target.value })} />)}</div>
        <SelectField label="Estado" disabled={busy} value={form.estado ?? 'PENDENTE'} onChange={e => setForm({ ...form, estado: e.target.value })}>{['PENDENTE', 'CONFIRMADA', 'INATIVA'].map(s => <option key={s}>{s}</option>)}</SelectField>
        <p className="help-text">Confirme somente após verificar a vigência, a posição e os valores na fonte. As datas inicial e final são inclusivas.</p>
        {form.carreira && form.carreira !== 'TAE' && <div className="space-y-4"><h3 className="subsection-title">RT da mesma referência</h3>{rt.map((r, index) => <div key={index} className="space-y-3"><TextField label={`Titulação ${index + 1}`} required value={r.titulacao} disabled={busy} onChange={e => setRt(rt.map((v, i) => i === index ? { ...v, titulacao: e.target.value } : v))} /><TextField label={`Valor da RT ${index + 1} (decimal com ponto)`} required disabled={busy} value={r.valor} onChange={e => setRt(rt.map((v, i) => i === index ? { ...v, valor: e.target.value } : v))} /><Button variant="quiet" disabled={busy} onClick={() => setRt(rt.filter((_, i) => i !== index))}>Remover RT {index + 1}</Button></div>)}<Button variant="secondary" disabled={busy || rt.length >= 20} onClick={() => setRt([...rt, { titulacao: '', valor: '' }])}>Adicionar RT</Button></div>}
        <Button type="submit" busy={busy} disabled={busy}>Salvar referência</Button>
      </form>
    </Modal>}
    {link && <Modal title="Conferir correspondência legada" busy={busy} onClose={() => setLink(null)}><form onSubmit={bind} className="p-6 space-y-4">{feedback?.tone === 'error' && <ActionFeedback feedback={feedback} />}<p className="help-text">Confira manualmente a posição e a vigência na fonte. Vincular não ativa o registro legado nem presume datas.</p><TextField label="ID da referência confirmada" type="number" min="1" required value={link.referencia} disabled={busy} onChange={e => setLink({ ...link, referencia: e.target.value })} /><Button type="submit" disabled={busy}>Registrar correspondência conferida</Button></form></Modal>}
  </PagePanel>;
}
