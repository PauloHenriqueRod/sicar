import { apiBaseUrl } from '../utils/api';
/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect, useId } from 'react';
import { Button, Pagination, TextField, SelectField, PagePanel, FilterBar, TableViewport, SortableHeader } from './ui';
import { pageTitles, roleLabel } from '../utils/presentation';
import { UserPlus, KeyRound, Users, ChevronRight } from 'lucide-react';

import type { Feedback } from './ActionFeedback';



export function GestaoUsuarios() {
  const formId = useId();
  const currentUserRole = localStorage.getItem('role');
  const [usuarios, setUsuarios] = useState<{id: number; username: string; role: string}[]>([]);
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('user');
  const [isLoading, setIsLoading] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  // Pagination states
  const [paginaAtual, setPaginaAtual] = useState(1);
  const itensPorPagina = 5;

  // Filters and Sorting
  const [roleFiltro, setRoleFiltro] = useState<string>('');
  const [usernameFiltro, setUsernameFiltro] = useState<string>('');
  const [sortConfig, setSortConfig] = useState<{ key: string, direction: 'asc'|'desc' } | null>({ key: 'id', direction: 'asc' });

  const carregarUsuarios = async () => {
    try {
      const response = await fetch(`${apiBaseUrl}/api/auth/usuarios`, {
        credentials: 'include'
      });
      if (!response.ok) throw new Error('Falha ao carregar usuários');
      const data = await response.json();
      setUsuarios(data);
      return true;
    } catch (err: unknown) {
      setError(err instanceof Error ? err instanceof Error ? err.message : String(err) : String(err));
      return false;
    }
  };

  useEffect(() => {
    carregarUsuarios();
  }, []);

  const filteredUsuarios = usuarios.filter(u => {
    const matchRole = roleFiltro === '' || u.role === roleFiltro;
    const matchUsername = usernameFiltro === '' || u.username.toLowerCase().includes(usernameFiltro.toLowerCase());
    return matchRole && matchUsername;
  });

  const sortedUsuarios = [...filteredUsuarios].sort((a, b) => {
    if (!sortConfig) return 0;
    const key = sortConfig.key as keyof typeof a;
    if (a[key] < b[key]) return sortConfig.direction === 'asc' ? -1 : 1;
    if (a[key] > b[key]) return sortConfig.direction === 'asc' ? 1 : -1;
    return 0;
  });

  const totalPaginas = Math.max(1, Math.ceil(sortedUsuarios.length / itensPorPagina));

  useEffect(() => {
    if (paginaAtual > totalPaginas && totalPaginas > 0) {
      setPaginaAtual(totalPaginas);
    }
  }, [sortedUsuarios, totalPaginas, paginaAtual]);

  const handleSort = (key: string) => {
    let direction: 'asc' | 'desc' = 'asc';
    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'asc') direction = 'desc';
    setSortConfig({ key, direction });
  };


  const handleCriarUsuario = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    setFeedback({ tone: 'loading', message: 'Criando o usuário...' });
    try {
      const response = await fetch(`${apiBaseUrl}/api/auth/usuarios`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify({ username: newUsername, password: newPassword, role: newRole })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Erro ao criar usuário');
      }

      setNewUsername('');
      setNewPassword('');
      if (await carregarUsuarios()) setFeedback({ tone: 'success', message: 'Usuário criado.', detail: 'O acesso está disponível na lista de usuários.' });
      else { setError(null); setFeedback({ tone: 'warning', message: 'Usuário criado. A lista não foi atualizada.', detail: 'Reabra esta tela para consultar o acesso. Não é necessário cadastrar novamente.' }); }
    } catch (err: unknown) {
      setFeedback(null);
      setError(err instanceof Error ? err instanceof Error ? err.message : String(err) : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handleResetSenha = async (userId: number) => {
    const novaSenha = prompt('Digite a nova senha para este usuário:');
    if (!novaSenha) return;

    setError(null);
    setIsResetting(true);
    setFeedback({ tone: 'loading', message: 'Redefinindo a senha do usuário...' });

    try {
      const response = await fetch(`${apiBaseUrl}/api/auth/usuarios/${userId}/reset-password`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        credentials: 'include',
        body: JSON.stringify({ new_password: novaSenha })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Erro ao redefinir senha');
      }
      setFeedback({ tone: 'success', message: 'Senha do usuário redefinida.' });
    } catch (err: unknown) {
      setFeedback(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsResetting(false);
    }
  };

  const indiceInicial = (paginaAtual - 1) * itensPorPagina;
  const usuariosPaginados = sortedUsuarios.slice(indiceInicial, indiceInicial + itensPorPagina);

  return (
    <div className="page-layout">

      <PagePanel title={pageTitles.usuarios} icon={Users} description="Consulte os acessos da equipe ou cadastre um usuário." feedback={error ? { tone: 'error', message: error } : feedback}>
      <details className="surface group mb-6 p-5">
        <summary className="disclosure-heading">
          <UserPlus className="h-5 w-5 shrink-0 text-accent-ink" aria-hidden="true" />
          <span className="flex-1">Cadastrar usuário</span>
          <ChevronRight className="disclosure-chevron" aria-hidden="true" />
        </summary>

        <form onSubmit={handleCriarUsuario} className="form-grid user-form-grid mt-6 border-t border-slate-200 pt-6 dark:border-slate-800">
          <div>
            <TextField label="Login" disabled={isLoading}
              id={`${formId}-username`}
              type="text"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              required
            />
          </div>
          <div>
            <TextField label="Senha inicial" disabled={isLoading} autoComplete="new-password"
              id={`${formId}-password`}
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={8}
            />
            <p hidden={newPassword.length === 0 || /(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).{8,}/.test(newPassword)} className="mt-2 max-w-full text-sm leading-relaxed text-danger">
              Use pelo menos 8 caracteres, uma letra maiúscula, um número e um caractere especial.
            </p>
          </div>
          <div>
            <SelectField label="Perfil de acesso" disabled={isLoading}
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
            >
              <option value="user">Usuário</option>
              <option value="admin">Administrador</option>
              {currentUserRole === 'dev' && (
                <option value="dev">Desenvolvedor</option>
              )}
            </SelectField>
          </div>
          <Button
            type="submit"
            busy={isLoading}
            disabled={isLoading || isResetting || !newUsername || !newPassword}
            className="w-full cursor-pointer"
          >
            {isLoading ? 'Criando...' : 'Cadastrar usuário'}
          </Button>
        </form>
      </details>

        <FilterBar>
          <SelectField label="Perfil" value={roleFiltro} onChange={e => { setRoleFiltro(e.target.value); setPaginaAtual(1); }}>
            <option value="">Todos os perfis</option><option value="user">Usuário</option><option value="admin">Administrador</option><option value="dev">Desenvolvedor</option>
          </SelectField>
          <TextField label="Usuário" type="search" placeholder="Buscar usuário" value={usernameFiltro} onChange={e => { setUsernameFiltro(e.target.value); setPaginaAtual(1); }} />
        </FilterBar>

        <TableViewport label="Usuários cadastrados">
          <table className="rhythm-table w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50 dark:bg-slate-900/20 text-muted text-sm border-b border-slate-200 dark:border-slate-700/30 select-none">
                <SortableHeader direction={sortConfig?.key === 'id' ? sortConfig.direction : undefined} onSort={() => handleSort('id')}>ID</SortableHeader>
                <SortableHeader direction={sortConfig?.key === 'username' ? sortConfig.direction : undefined} onSort={() => handleSort('username')}>Usuário</SortableHeader>
                <SortableHeader direction={sortConfig?.key === 'role' ? sortConfig.direction : undefined} onSort={() => handleSort('role')}>Perfil</SortableHeader>
                <th className="p-4 font-semibold text-right rounded-tr-xl">Ações</th>
              </tr>
            </thead>
            <tbody>
              {usuariosPaginados.map(u => (
                <tr key={u.id} className="border-b border-slate-100 dark:border-slate-800/30 hover:bg-slate-50/50 dark:hover:bg-slate-900/20 transition-colors">
                  <td className="p-4 text-muted tabular-nums text-sm">#{u.id}</td>
                  <td className="p-4 font-medium text-ink">{u.username}</td>
                  <td className="p-4">
                    <span className="neutral-badge">
                      {roleLabel(u.role)}
                    </span>
                  </td>
                  <td className="p-4 flex justify-end gap-2">
                    <button
                      onClick={() => handleResetSenha(u.id)}
                      disabled={isLoading || isResetting}
                      className="flex items-center gap-2 px-3 py-2 bg-panel hover:bg-blue-100 dark:hover:bg-slate-800/50 text-ink hover:text-accent-ink rounded-lg text-sm font-semibold transition-colors cursor-pointer"
                      title="Redefinir senha"
                    >
                      <KeyRound className="w-4 h-4" /> Redefinir senha
                    </button>
                  </td>
                </tr>
              ))}
              {usuariosPaginados.length === 0 && <tr><td colSpan={4} className="p-8 text-center text-muted">Nenhum usuário encontrado.</td></tr>}
            </tbody>
          </table>
        </TableViewport>

        {/* Pagination controls */}
        <Pagination page={paginaAtual} pageCount={totalPaginas} onPageChange={setPaginaAtual} label="dos usuários" summary={<>Mostrando {indiceInicial + 1} a {Math.min(indiceInicial + itensPorPagina, sortedUsuarios.length)} de {sortedUsuarios.length} usuários</>} />
      </PagePanel>

    </div>
  );
}
