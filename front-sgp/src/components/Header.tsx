import { useEffect, useId, useRef, useState } from 'react';
import type { Ref } from 'react';
import { ChevronDown, CircleHelp, KeyRound, LogOut, Menu } from 'lucide-react';
import { Button } from './ui';

import type { PageTab as Tab } from '../types';
import { pageTitles, roleLabel } from '../utils/presentation';
interface HeaderProps { isSidebarOpen: boolean; setIsSidebarOpen: (val: boolean) => void; activeTab: Tab; setShowAlterarSenha: (val: boolean) => void; handleLogout: () => void; onOpenGuide?: () => void; guideButtonRef?: Ref<HTMLButtonElement>; }

export function Header({ isSidebarOpen, setIsSidebarOpen, activeTab, setShowAlterarSenha, handleLogout, onOpenGuide, guideButtonRef }: HeaderProps) {
  const [isAccountOpen, setIsAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const accountId = useId();
  const username = localStorage.getItem('username') || 'Usuário';
  const role = localStorage.getItem('role');
  const currentRoleLabel = roleLabel(role || 'user');
  const initials = username.slice(0, 2).toUpperCase();

  useEffect(() => {
    if (!isAccountOpen) return;
    const handleOutsideClick = (event: PointerEvent) => {
      if (event.target instanceof Node && !accountRef.current?.contains(event.target)) setIsAccountOpen(false);
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsAccountOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('pointerdown', handleOutsideClick);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('pointerdown', handleOutsideClick);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [isAccountOpen]);

  return (
    <header className="app-header sticky top-0 z-30">
      <div className="flex min-h-[4.75rem] items-center justify-between gap-4 px-4 py-3 md:px-7">
        <div className="flex min-w-0 items-center gap-3">
          {!isSidebarOpen && <Button variant="icon" onClick={() => setIsSidebarOpen(true)} className="md:hidden" aria-label="Abrir menu"><Menu className="h-5 w-5" aria-hidden="true" /></Button>}
          <h1 className="page-title min-w-0 break-words">{pageTitles[activeTab]}</h1>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {onOpenGuide && <Button variant="quiet" ref={guideButtonRef} aria-label="Abrir guia rápido" title="Guia rápido" onClick={onOpenGuide}><CircleHelp aria-hidden="true" className="h-5 w-5" /><span className="hidden sm:inline">Guia rápido</span></Button>}
        <div ref={accountRef} className="relative" onBlur={event => {
          if (!event.currentTarget.contains(event.relatedTarget)) setIsAccountOpen(false);
        }}>
          <button ref={triggerRef} type="button" onClick={() => setIsAccountOpen(open => !open)} aria-label="Menu da conta" aria-expanded={isAccountOpen} aria-controls={accountId} className="flex items-center gap-3 rounded-lg border border-transparent px-2 py-1.5 text-left hover:border-slate-200 hover:bg-slate-50 dark:hover:border-slate-700 dark:hover:bg-slate-800">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-slate-100 text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">{initials}</span>
            <span className="hidden leading-tight sm:block"><span className="block max-w-36 truncate text-sm font-semibold text-ink">{username}</span><span className="block text-xs text-muted">{currentRoleLabel}</span></span>
            <ChevronDown className="h-4 w-4 text-muted" aria-hidden="true" />
          </button>
          <div id={accountId} hidden={!isAccountOpen} className={(isAccountOpen ? '' : 'hidden ') + 'absolute right-0 top-full z-50 mt-1 w-52 rounded-lg border border-slate-200 bg-white p-1 shadow-lg dark:border-slate-700 dark:bg-slate-900'}>
            <button onClick={() => { setIsAccountOpen(false); setShowAlterarSenha(true); }} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"><KeyRound className="h-4 w-4" /> Alterar senha</button>
            <button onClick={() => { setIsAccountOpen(false); handleLogout(); }} className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-ink hover:bg-panel"><LogOut className="h-4 w-4" /> Encerrar sessão</button>
          </div>
        </div>
        </div>
      </div>
    </header>
  );
}
