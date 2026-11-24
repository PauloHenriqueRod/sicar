import { Calculator, ChevronLeft, ClipboardList, FileClock, Landmark, LayoutDashboard, Menu, Moon, ShieldCheck, Sun, TableProperties, Users } from 'lucide-react';
import { Button } from './ui';

import type { PageTab as Tab } from '../types';
import { pageTitles } from '../utils/presentation';
interface SidebarProps { isSidebarOpen: boolean; setIsSidebarOpen: (val: boolean) => void; activeTab: Tab; setActiveTab: (val: Tab) => void; userRole: string | null; isDarkMode: boolean; setIsDarkMode: (val: boolean) => void; resetAll: () => void; isBusy?: boolean; }
interface NavItem { id: Tab; label: string; icon: typeof LayoutDashboard; }

export function Sidebar({ isSidebarOpen, setIsSidebarOpen, activeTab, setActiveTab, userRole, isDarkMode, setIsDarkMode, resetAll, isBusy = false }: SidebarProps) {
  const isManager = userRole === 'admin' || userRole === 'dev';
  const navigate = (tab: Tab) => { setActiveTab(tab); if (window.innerWidth < 768) setIsSidebarOpen(false); };
  const renderItem = ({ id, label, icon: Icon }: NavItem) => (
    <button key={id} onClick={() => navigate(id)} className={`group relative flex w-full items-center gap-3 rounded-lg py-2.5 text-sm font-medium transition-colors ${isSidebarOpen ? 'px-3' : 'justify-center px-0'} ${activeTab === id ? 'bg-navigation-active text-navigation-active-ink' : 'text-navigation-ink hover:bg-white/10'}`} title={label} aria-label={label} aria-current={activeTab === id ? 'page' : undefined}>
      <Icon className={`h-[18px] w-[18px] shrink-0 ${activeTab === id ? 'text-navigation-active-ink' : 'text-navigation-muted'}`} />
      {isSidebarOpen && <span className="min-w-0 break-words text-left">{label}</span>}
    </button>
  );
  return <>
    {isSidebarOpen && <button aria-label="Fechar menu" className="fixed inset-0 z-40 bg-slate-950/50 md:hidden" onClick={() => setIsSidebarOpen(false)} />}
    <aside className={`fixed inset-y-0 left-0 z-50 flex max-w-full shrink-0 flex-col bg-navigation text-navigation-ink shadow-lg md:shadow-none transition-all duration-200 md:static md:translate-x-0 ${isSidebarOpen ? 'visible w-68 translate-x-0' : 'invisible w-18 -translate-x-full md:visible md:translate-x-0'}`}>
      <div className={`flex min-h-[4.75rem] shrink-0 items-center gap-2 border-b border-white/10 py-3 ${isSidebarOpen ? 'justify-between px-5' : 'justify-center px-2'}`}>
        {isSidebarOpen && <div className="flex min-w-0 items-center gap-3"><div className="grid h-7 w-7 shrink-0 place-items-center"><Landmark className="h-5 w-5 text-navigation-muted" /></div><div className="min-w-0 leading-tight"><p className="text-xs font-medium text-navigation-muted">Universidade Federal</p><p className="brand-title text-base">SICAR</p></div></div>}
        <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="shrink-0 rounded-md p-2 text-navigation-muted hover:bg-white/10 hover:text-navigation-ink" aria-label={isSidebarOpen ? 'Recolher menu' : 'Expandir menu'}>{isSidebarOpen ? <ChevronLeft className="h-5 w-5" /> : <Menu className="h-5 w-5" />}</button>
      </div>
      <nav className="custom-scrollbar flex-1 overflow-y-auto px-3 py-5">
        {isSidebarOpen && <p className="mb-2 px-3 text-sm font-semibold text-navigation-muted">Rotinas</p>}
        <div className="space-y-1">{renderItem({ id: 'dashboard', label: pageTitles.dashboard, icon: LayoutDashboard })}{renderItem({ id: 'calculo', label: pageTitles.calculo, icon: Calculator })}{renderItem({ id: 'historico', label: pageTitles.historico, icon: FileClock })}</div>
        {isManager && <><div className="my-5 border-t border-white/10" />{isSidebarOpen && <p className="mb-2 px-3 text-sm font-semibold text-navigation-muted">Administração</p>}<div className="space-y-1">{renderItem({ id: 'tabelas', label: pageTitles.tabelas, icon: TableProperties })}{renderItem({ id: 'usuarios', label: pageTitles.usuarios, icon: Users })}{userRole === 'dev' && renderItem({ id: 'auditoria', label: pageTitles.auditoria, icon: ShieldCheck })}</div></>}
      </nav>
      <div className="border-t border-white/10 p-3">
        <button onClick={() => setIsDarkMode(!isDarkMode)} className={`mb-2 flex w-full items-center rounded-lg py-2.5 text-sm text-navigation-ink hover:bg-white/10 ${isSidebarOpen ? 'justify-between px-3' : 'justify-center'}`} title={isDarkMode ? 'Usar tema claro' : 'Usar tema escuro'}>{isSidebarOpen && <span>Tema da interface</span>}{isDarkMode ? <Moon className="h-[18px] w-[18px]" /> : <Sun className="h-[18px] w-[18px]" />}</button>
        <Button disabled={isBusy} onClick={() => { resetAll(); navigate('calculo'); }} className={`w-full ${isSidebarOpen ? 'px-3 text-sm' : 'px-0'}`} title="Novo cálculo" aria-label="Novo cálculo"><ClipboardList className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />{isSidebarOpen && <span>Novo cálculo</span>}</Button>
      </div>
    </aside>
  </>;
}
