import { apiBaseUrl } from '../utils/api';
/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect, useRef } from 'react';
import type { TipoCalculo } from '../types';
import { Button, Pagination, PagePanel, FilterBar, TableViewport, TextField, SelectField, SortableHeader } from './ui';
import { pageTitles, calculationLabels, calculationLabel, formatDate, formatHistoryTotal } from '../utils/presentation';
import { Clock, RefreshCw, FileText } from 'lucide-react';

import type { Feedback } from './ActionFeedback';

interface HistoricoRecord {
  id: number;
  data_calculo: string;
  tipo_calculo: string;
  matricula: string;
  classe: string;
  nivel: number | null;
  titulacao: string;
  resultado_json: string;
  substituido_por?: number | null;
}

interface Memory { id: number; tipo_calculo: TipoCalculo; anterior_id: number | null; substituido_por: number | null; pode_recalcular: boolean; entradas_recalculo?: Record<string, unknown> | null; snapshot: { versao?: number; dados_extraidos?: Record<string, unknown>; resultado_calculo?: Record<string, unknown>; rastreabilidade?: Record<string, unknown>; [key: string]: unknown } }

export function Historico({ onRecalculate }: { onRecalculate?: (type: TipoCalculo, data: Record<string, unknown>, id: number) => boolean | void }) {
  const [memory, setMemory] = useState<Memory | null>(null);
  const [reading, setReading] = useState(false);
  const action = useRef<AbortController | null>(null);
  useEffect(() => () => { action.current?.abort(); }, []);
  const openMemory = async (id: number) => {
    action.current?.abort(); const controller = new AbortController(); action.current = controller;
    setReading(true); setMemory(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/historico/${id}`, { credentials: 'include', signal: controller.signal });
      if (!response.ok) throw new Error('Não foi possível consultar a memória.');
      const value = await response.json();
      if (!controller.signal.aborted) setMemory(value);
    } catch { if (!controller.signal.aborted) setFeedback({ tone: 'error', message: 'Não foi possível consultar a memória.' }); }
    finally { if (!controller.signal.aborted) setReading(false); }
  };
  const exportMemory = async () => {
    if (!memory) return;
    action.current?.abort(); const controller = new AbortController(); action.current = controller; setReading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/exportar-pdf`, { credentials: 'include', signal: controller.signal, method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ historico_id: memory.id }) });
      if (!response.ok) throw new Error('Falha na exportação');
      const blob = await response.blob();
      const { default: saveAs } = await import('file-saver');
      if (!controller.signal.aborted) saveAs(blob, `Historico_${memory.id}.pdf`);
    } catch { if (!controller.signal.aborted) setFeedback({ tone: 'error', message: 'Não foi possível exportar este histórico.' }); }
    finally { if (!controller.signal.aborted) setReading(false); }
  };
  const [registros, setRegistros] = useState<HistoricoRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  // Pagination states
  const [paginaAtual, setPaginaAtual] = useState(1);
  const itensPorPagina = 10;

  // Filters and Sorting
  const [tipoCalculoFiltro, setTipoCalculoFiltro] = useState<string>('');
  const [matriculaFiltro, setMatriculaFiltro] = useState<string>('');
  const [classeFiltro, setClasseFiltro] = useState<string>('');
  const [titulacaoFiltro, setTitulacaoFiltro] = useState<string>('');
  const [sortConfig, setSortConfig] = useState<{ key: keyof HistoricoRecord, direction: 'asc'|'desc' } | null>({ key: 'data_calculo', direction: 'desc' });

  const [total, setTotal] = useState(0);
  const [refreshCount, setRefreshCount] = useState(0);

  useEffect(() => {
    action.current?.abort(); setMemory(null); setReading(false);
    const controller = new AbortController();
    let current = true;
    const params = new URLSearchParams({
      pagina: String(paginaAtual), tamanho_pagina: String(itensPorPagina),
      busca: matriculaFiltro, tipo_calculo: tipoCalculoFiltro,
      classe: classeFiltro, titulacao: titulacaoFiltro,
      ordenar_por: sortConfig?.key ?? 'data_calculo', ordem: sortConfig?.direction ?? 'desc',
    });
    setLoading(true);
    setFeedback({ tone: 'loading', message: 'Carregando o histórico de cálculos...' });
    void (async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/api/historico?${params}`, { credentials: 'include', signal: controller.signal });
        if (!response.ok) throw new Error('Falha ao carregar histórico');
        const data = await response.json();
        if (!Array.isArray(data.itens) || !Number.isInteger(data.total) || data.total < 0) throw new Error('Histórico inválido');
        if (!current) return;
        setRegistros(data.itens);
        setTotal(data.total);
        const lastPage = Math.max(1, Math.ceil(data.total / itensPorPagina));
        if (paginaAtual > lastPage) setPaginaAtual(lastPage);
        setFeedback(refreshCount ? { tone: 'success', message: 'Histórico atualizado.' } : null);
      } catch {
        if (!current) return;
        setRegistros([]);
        setFeedback({ tone: 'error', message: 'Não foi possível carregar o histórico.', detail: 'Selecione Atualizar registros para tentar novamente.' });
      } finally {
        if (current) setLoading(false);
      }
    })();
    return () => { current = false; controller.abort(); };
  }, [paginaAtual, matriculaFiltro, tipoCalculoFiltro, classeFiltro, titulacaoFiltro, sortConfig, refreshCount]);

  const totalPaginas = Math.max(1, Math.ceil(total / itensPorPagina));
  const indiceInicial = (paginaAtual - 1) * itensPorPagina;
  const temFiltro = Boolean(matriculaFiltro || tipoCalculoFiltro || classeFiltro || titulacaoFiltro);
  const handleSort = (key: keyof HistoricoRecord) => {
    setSortConfig({ key, direction: sortConfig?.key === key && sortConfig.direction === 'asc' ? 'desc' : 'asc' });
    setPaginaAtual(1);
  };

  return (
    <div className="page-layout">

        <PagePanel feedback={feedback} title={pageTitles.historico} icon={Clock} description="Consulte registros e memórias de cálculo." actions={
          <Button variant="secondary"
            onClick={() => setRefreshCount(count => count + 1)}
            disabled={loading}
            className="cursor-pointer"
          >
            <RefreshCw className={`w-5 h-5 shrink-0 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" />
            {loading ? 'Atualizando...' : 'Atualizar registros'}
          </Button>
        } >

        <FilterBar>
          <SelectField label="Tipo de cálculo" value={tipoCalculoFiltro} onChange={e => { setTipoCalculoFiltro(e.target.value); setPaginaAtual(1); }}>
            <option value="">Todos os tipos</option>
            {Object.entries(calculationLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </SelectField>
          <SelectField label="Classe" value={classeFiltro} onChange={e => { setClasseFiltro(e.target.value); setPaginaAtual(1); }}>
            <option value="">Todas as classes</option>
            <option value="Auxiliar">Auxiliar</option><option value="Assistente">Assistente</option><option value="Adjunto">Adjunto</option><option value="Associado">Associado</option><option value="Titular">Titular</option><option value="Técnico Administrativo">Técnico Administrativo</option>
          </SelectField>
          <SelectField label="Titulação" value={titulacaoFiltro} onChange={e => { setTitulacaoFiltro(e.target.value); setPaginaAtual(1); }}>
            <option value="">Todas as titulações</option>
            <option value="Especialização">Especialização</option><option value="Mestrado">Mestrado</option><option value="Doutorado">Doutorado</option>
          </SelectField>
          <TextField label="Matrícula" type="search" placeholder="Buscar matrícula" value={matriculaFiltro} onChange={e => { setMatriculaFiltro(e.target.value); setPaginaAtual(1); }} />
        </FilterBar>

        {loading && registros.length === 0 ? (
          <div className="flex justify-center items-center py-20 text-accent-ink">
            <RefreshCw className="w-10 h-10 animate-spin opacity-50" />
          </div>
        ) : feedback?.tone === 'error' && registros.length === 0 ? null : registros.length === 0 ? (
          <div className="text-center py-20 text-muted">
            <FileText className="w-16 h-16 mx-auto mb-4 opacity-20" />
            <p className="text-lg">{temFiltro ? 'Nenhum cálculo encontrado para os filtros selecionados.' : 'Nenhum cálculo registrado ainda.'}</p>
          </div>
        ) : (
          <>
            <TableViewport label="Registros de cálculos">
              <table aria-busy={loading} className="rhythm-table w-full text-left text-sm text-muted">
                <thead className="bg-slate-50 dark:bg-slate-900/20 text-ink font-semibold border-b border-slate-200 dark:border-slate-700/30 select-none">
                  <tr>
                    <SortableHeader direction={sortConfig?.key === 'data_calculo' ? sortConfig.direction : undefined} onSort={() => handleSort('data_calculo')}>Data</SortableHeader>
                    <SortableHeader direction={sortConfig?.key === 'matricula' ? sortConfig.direction : undefined} onSort={() => handleSort('matricula')}>Matrícula</SortableHeader>
                    <SortableHeader direction={sortConfig?.key === 'tipo_calculo' ? sortConfig.direction : undefined} onSort={() => handleSort('tipo_calculo')}>Tipo de cálculo</SortableHeader>
                    <SortableHeader direction={sortConfig?.key === 'classe' ? sortConfig.direction : undefined} onSort={() => handleSort('classe')}>Servidor (classe e titulação)</SortableHeader>
                    <th className="p-4 text-right">Valor consolidado</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {loading ? <tr><td colSpan={5} className="p-8 text-center">Atualizando registros...</td></tr> : registros.map((r) => (
                    <tr key={r.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50 transition-colors">
                      <td className="p-4 text-muted">{formatDate(r.data_calculo, true)}<span className="block help-text">Histórico #{r.id}{r.substituido_por ? ` · Substituído pelo #${r.substituido_por}` : ''}</span></td>
                      <td className="p-4 tabular-nums text-ink">{r.matricula}</td>
                      <td className="p-4 font-medium text-accent-ink text-sm">
                        {calculationLabel(r.tipo_calculo)}
                      </td>
                      <td className="p-4">
                        {r.classe} - {r.nivel == null ? 'Nível não informado' : `L${r.nivel}`} <br />
                        <span className="help-text">{r.titulacao}</span>
                      </td>
                      <td className="p-4 text-right font-semibold tabular-nums text-ink">
                        {formatHistoryTotal(r.resultado_json)}
                        <Button variant="quiet" disabled={reading} onClick={() => void openMemory(r.id)}>Ver memória #{r.id}</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableViewport>

            {/* Pagination Controls */}
            <Pagination page={paginaAtual} pageCount={totalPaginas} onPageChange={setPaginaAtual} label="do histórico" disabled={loading} summary={loading ? 'Atualizando registros...' : <>Mostrando {indiceInicial + 1} a {Math.min(indiceInicial + itensPorPagina, total)} de {total} registros</>} />
          </>
        )}
      {memory && <section className="space-y-4 mt-5" aria-label={`Memória do histórico ${memory.id}`}>
        <h3 className="subsection-title">Histórico #{memory.id} · Motor {String(memory.snapshot.rastreabilidade?.versao_motor ?? 'não registrado')}</h3>
        <p>{memory.anterior_id ? `Recálculo do #${memory.anterior_id}. ` : ''}{memory.substituido_por ? `Versão histórica substituída pelo #${memory.substituido_por}.` : 'Versão consultada.'}</p>
        <p>Valor consolidado: {formatHistoryTotal(JSON.stringify(memory.snapshot.resultado_calculo ?? memory.snapshot))}</p>
        {typeof memory.snapshot.resultado_calculo?.nota_arredondamento === 'string' && <p>{memory.snapshot.resultado_calculo.nota_arredondamento}</p>}
        {Object.entries(memory.snapshot).map(([key, value]) => <details key={key}><summary>{({ dados_extraidos: 'Entradas finais e fontes', dados_utilizados: 'Dados utilizados', resultado_calculo: 'Resultado salvo', rastreabilidade: 'Regras, tabelas e precisão', versao: 'Versão do snapshot' } as Record<string, string>)[key] ?? key}</summary><pre className="overflow-auto whitespace-pre-wrap text-sm">{JSON.stringify(value, null, 2)}</pre></details>)}
        {!memory.pode_recalcular && <p>Registro legado sem entradas completas. A memória original permanece disponível; não é convertida para as regras atuais.</p>}
        <Button disabled={reading || !memory.pode_recalcular} onClick={() => void exportMemory()}>Exportar versão #{memory.id}</Button>
        {onRecalculate && <Button variant="secondary" disabled={reading || !memory.pode_recalcular || !!memory.substituido_por} onClick={() => { if (onRecalculate(memory.tipo_calculo, memory.entradas_recalculo ?? memory.snapshot.dados_extraidos!, memory.id) === false) setFeedback({ tone: 'warning', message: 'Conclua ou descarte o rascunho atual antes de preparar outro recálculo.' }); }}>Preparar recálculo #{memory.id}</Button>}
        <Button variant="quiet" onClick={() => { action.current?.abort(); setReading(false); setMemory(null); }}>Fechar memória</Button>
      </section>}
      </PagePanel>
    </div>
  );
}
