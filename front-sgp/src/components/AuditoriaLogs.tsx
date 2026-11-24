import { apiBaseUrl } from '../utils/api';
/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect } from 'react';
import { Button, Pagination, PagePanel, TableViewport } from './ui';
import { pageTitles, formatDate } from '../utils/presentation';
import { ShieldAlert, Activity, CheckCircle, CircleAlert, Info } from 'lucide-react';



interface AuditLog {
  id: number;
  user_id: number | null;
  action: string;
  target: string | null;
  timestamp: string;
  ip_address: string | null;
}

export function AuditoriaLogs() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pagination states
  const [paginaAtual, setPaginaAtual] = useState(1);
  const itensPorPagina = 10;

  const carregarLogs = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/auth/audit-logs`, {
        credentials: 'include'
      });
      if (!response.ok) throw new Error('Falha ao carregar logs de auditoria');
      const data = await response.json();
      setLogs(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err instanceof Error ? err.message : String(err) : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    carregarLogs();
  }, []);

  const totalPaginas = Math.ceil(logs.length / itensPorPagina);

  useEffect(() => {
    if (paginaAtual > totalPaginas && totalPaginas > 0) {
      setPaginaAtual(totalPaginas);
    }
  }, [logs, totalPaginas, paginaAtual]);

  const indiceInicial = (paginaAtual - 1) * itensPorPagina;
  const logsPaginados = logs.slice(indiceInicial, indiceInicial + itensPorPagina);

  const getActionBadge = (action: string) => {
    switch (action) {
      case 'LOGIN_SUCCESS':
        return <span className="feedback-success inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-semibold"><CheckCircle className="h-3.5 w-3.5" aria-hidden="true" />Acesso realizado</span>;
      case 'LOGIN_FAILED_LOCKED':
      case 'ACCOUNT_LOCKED':
        return <span className="feedback-error inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-semibold"><CircleAlert className="h-3.5 w-3.5" aria-hidden="true" />Bloqueado</span>;
      case 'USER_CREATED':
        return <span className="feedback-success inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-semibold"><CheckCircle className="h-3.5 w-3.5" aria-hidden="true" />Usuário criado</span>;
      case 'PASSWORD_RESET':
        return <span className="feedback-success inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-semibold"><CheckCircle className="h-3.5 w-3.5" aria-hidden="true" />Senha redefinida</span>;
      case 'USER_DELETED':
        return <span className="neutral-badge inline-flex items-center gap-1.5"><Info className="h-3.5 w-3.5" aria-hidden="true" />Usuário excluído</span>;
      default:
        return <span className="neutral-badge">{action}</span>;
    }
  };

  return (
    <div className="page-layout">
        <PagePanel title={pageTitles.auditoria} icon={ShieldAlert} description="Consulte as ações registradas e seus responsáveis." feedback={error ? { tone: 'error', message: error } : undefined} actions={
          <Button variant="secondary"
            onClick={carregarLogs}
            disabled={isLoading}
            className="cursor-pointer"
          >
            <Activity className="w-4 h-4" />
            Atualizar registros
          </Button>
        } >

        <TableViewport label="Registros de auditoria">
          <table className="rhythm-table w-full text-left border-collapse">
            <thead>
              <tr className="bg-panel/50 text-muted text-sm border-b border-slate-200 dark:border-slate-700/50">
                <th className="p-4 font-semibold rounded-tl-xl w-16">ID</th>
                <th className="p-4 font-semibold">Data e hora</th>
                <th className="p-4 font-semibold">Ação</th>
                <th className="p-4 font-semibold">Alvo</th>
                <th className="p-4 font-semibold">IP de origem</th>
                <th className="p-4 font-semibold text-right rounded-tr-xl">Responsável (ID)</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 && !isLoading ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-muted">
                    Nenhum registro de auditoria encontrado.
                  </td>
                </tr>
              ) : (
                logsPaginados.map(log => (
                  <tr key={log.id} className="border-b border-slate-100 dark:border-slate-800/50 hover:bg-slate-50/50 dark:hover:bg-slate-800/30 transition-colors">
                    <td className="p-4 text-muted tabular-nums text-sm">#{log.id}</td>
                    <td className="p-4 text-ink text-sm whitespace-nowrap">{formatDate(log.timestamp, true)}</td>
                    <td className="p-4">{getActionBadge(log.action)}</td>
                    <td className="p-4 text-slate-800 dark:text-slate-200 font-medium">{log.target || '-'}</td>
                    <td className="p-4 text-muted text-sm tabular-nums">{log.ip_address || '-'}</td>
                    <td className="p-4 text-muted text-sm text-right tabular-nums">{log.user_id ? `#${log.user_id}` : 'Sistema / Falha'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </TableViewport>

        <Pagination page={paginaAtual} pageCount={totalPaginas} onPageChange={setPaginaAtual} label="da auditoria" summary={<>Mostrando {indiceInicial + 1} a {Math.min(indiceInicial + itensPorPagina, logs.length)} de {logs.length} registros</>} />
      </PagePanel>
    </div>
  );
}
