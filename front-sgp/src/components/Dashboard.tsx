import { apiBaseUrl } from '../utils/api';
/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect } from 'react';
import { Button } from './ui';
import { Users, Calculator, History, ArrowRight, FileText } from 'lucide-react';
import type { ReactNode } from 'react';
import { pageTitles, calculationLabel, formatDate } from '../utils/presentation';
import { TableViewport } from './ui';

interface DashboardStats {
  total_calculos: number;
  total_usuarios: number;
  calculos_por_tipo: Record<string, number>;
  ultimos_calculos: { data_calculo: string; matricula: string; tipo_calculo: string; classe: string; }[];
}

interface DashboardProps {
  setActiveTab: (val: 'calculo' | 'historico' | 'usuarios' | 'auditoria' | 'tabelas') => void;
  userRole: string | null;
  hasActiveCalculation?: boolean;
  onboarding?: ReactNode;
}

const quickActions = [
  { tab: 'historico', title: pageTitles.historico, description: 'Consulte registros e memórias de cálculo.', icon: History, managerOnly: false },
  { tab: 'tabelas', title: pageTitles.tabelas, description: 'Consulte e atualize vencimentos e titulações.', icon: FileText, managerOnly: true },
  { tab: 'usuarios', title: pageTitles.usuarios, description: 'Gerencie os acessos da equipe.', icon: Users, managerOnly: true },
] as const;

export function Dashboard({ setActiveTab, userRole, hasActiveCalculation = false, onboarding }: DashboardProps) {
  const isManager = userRole === 'admin' || userRole === 'dev';
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState<string>('Usuário');

  useEffect(() => {
    const storedUsername = localStorage.getItem('username');
    if (storedUsername) setUsername(storedUsername);

    const fetchStats = async () => {
      try {

        const response = await fetch(`${apiBaseUrl}/api/dashboard/stats`, { credentials: 'include' });
        if (response.ok) {
          const data = await response.json();
          setStats(data);
        }
      } catch (error) {
        console.error('Erro ao carregar estatísticas do dashboard', error);
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
  }, []);


  return (
    <div className="page-layout">

      {/* Header Saudação */}
      <div className="surface">
        {/* Regra dos terços: saudação em dois terços, ação no terço direito. */}
        <div className="content-grid items-center p-6 sm:p-8 lg:p-10">
        <div className="grid-main">
          <h2 className="welcome-title mb-3 break-words">
            Bem-vindo, {username}
          </h2>
          <p className="body-text max-w-xl text-muted">
            {hasActiveCalculation ? 'Continue de onde parou. Os dados revisados estão preservados.' : 'Comece enviando os documentos para um novo cálculo.'}
          </p>
        </div>
        <Button
          onClick={() => setActiveTab('calculo')}
          className="grid-action w-full sm:w-fit max-w-full cursor-pointer"
        >
          <Calculator className="w-5 h-5 shrink-0" aria-hidden="true" />
          {hasActiveCalculation ? 'Continuar cálculo' : 'Novo cálculo'}
        </Button>
        </div>
      </div>

      {onboarding}

      {/* Acesso Rápido */}
      <div>
        <h3 className="subsection-title mb-5">
          Acesso rápido
        </h3>
        <div className="content-grid">
          {quickActions.filter(action => !action.managerOnly || isManager).map(({ tab, title, description, icon: Icon }) => (
            <button key={tab} type="button" aria-label={title} onClick={() => setActiveTab(tab)} className={`quick-access-card ${isManager ? 'grid-third' : 'grid-full'} cursor-pointer`}>
              <span className="flex w-full items-center gap-3">
                <span className="section-icon" aria-hidden="true"><Icon className="h-5 w-5" /></span>
                <span className="flex-1 text-base font-semibold text-ink">{title}</span>
                <ArrowRight className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
              </span>
              <span className="help-text mt-3">{description}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Métricas e Resumo */}
      {loading ? (
        <div className="flex justify-center p-10">
          <div className="animate-spin motion-reduce:animate-none rounded-full h-8 w-8 border-b-2 border-accent-ink" aria-hidden="true"></div>
        </div>
      ) : stats ? (
        <div className="content-grid items-start">

          {/* Card de Estatísticas Gerais */}
          <div className="surface grid-side p-6 sm:p-8">
             <h3 className="subsection-title mb-6 flex items-center gap-2">
                Resumo operacional
             </h3>
             <div className="space-y-6">
                <div className="flex flex-col gap-2 p-5 bg-panel/50 rounded-lg">
                  <span className="text-sm text-muted">Processos calculados</span>
                  <span className="text-4xl font-bold tracking-normal tabular-nums text-ink">{stats.total_calculos}</span>
                </div>
                {isManager && <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-panel/50 rounded-lg">
                  <span className="text-sm text-muted">Usuários ativos</span>
                  <span className="text-2xl font-semibold tabular-nums text-ink">{stats.total_usuarios}</span>
                </div>}

                <div className="pt-4 border-t border-slate-200 dark:border-slate-800">
                  <h4 className="text-sm font-semibold text-ink mb-4">
                    Processos por assunto
                  </h4>
                  <div className="space-y-3">
                    {Object.entries(stats.calculos_por_tipo)
                      .sort(([,a], [,b]) => b - a)
                      .slice(0, 4)
                      .map(([tipo, qtd]) => (
                      <div key={tipo} className="flex justify-between items-center text-sm">
                        <span className="text-ink">{calculationLabel(tipo)}</span>
                        <span className="bg-panel px-2 py-1 rounded text-muted font-medium">{qtd}</span>
                      </div>
                    ))}
                    {Object.keys(stats.calculos_por_tipo).length === 0 && (
                      <p className="help-text">Nenhum cálculo registrado.</p>
                    )}
                  </div>
                </div>
             </div>
          </div>

          {/* Cálculos Recentes */}
          <div className="surface grid-main p-6 sm:p-8">
             <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
               <h3 className="subsection-title flex items-center gap-2">
                  Atividade recente
               </h3>
               <Button variant="link"
                onClick={() => setActiveTab('historico')}
                className="cursor-pointer"
               >
                 Ver todos <ArrowRight className="w-4 h-4" />
               </Button>
             </div>

             {stats.ultimos_calculos.length === 0 ? (
               <div className="help-text text-center py-10">
                 Nenhum processo calculado ainda.
               </div>
             ) : (
               <TableViewport label="Atividade recente">
                 <table className="rhythm-table w-full text-left text-sm text-muted">
                   <thead className="bg-panel/50 text-muted font-semibold border-b border-slate-200 dark:border-slate-800">
                     <tr>
                       <th className="p-3 rounded-tl-lg">Data</th>
                       <th className="p-3">Matrícula</th>
                       <th className="p-3">Tipo</th>
                       <th className="p-3 rounded-tr-lg">Classe</th>
                     </tr>
                   </thead>
                   <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                     {stats.ultimos_calculos.map((calc, i) => (
                       <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                         <td className="p-3 whitespace-nowrap">{formatDate(calc.data_calculo)}</td>
                         <td className="p-3 tabular-nums text-ink">{calc.matricula}</td>
                         <td className="p-3 font-medium text-ink">{calculationLabel(calc.tipo_calculo)}</td>
                         <td className="p-3 text-muted">{calc.classe}</td>
                       </tr>
                     ))}
                   </tbody>
                 </table>
               </TableViewport>
             )}
          </div>

        </div>
      ) : (
        <div className="text-center py-10 text-danger">Erro ao carregar estatísticas.</div>
      )}
    </div>
  );
}
