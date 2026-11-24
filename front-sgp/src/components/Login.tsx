import { apiBaseUrl } from '../utils/api';
import { useId, useState } from 'react';
import { Button, TextField } from './ui';
import { ArrowLeft } from 'lucide-react';

interface LoginProps {
  onLogin: (role: string, username: string) => void;
  onBack?: () => void;
}

export function Login({ onLogin, onBack }: LoginProps) {
  const usernameId = useId();
  const passwordId = useId();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {

      const response = await fetch(`${apiBaseUrl}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username, password })
      });

      if (!response.ok) {
        throw new Error('Usuário ou senha inválidos');
      }

      const data = await response.json();
      onLogin(data.role, data.username);
    } catch (err: unknown) {
      setError(err instanceof Error ? err instanceof Error ? err.message : String(err) : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col justify-center items-center p-4">
      <div className="surface w-full max-w-md overflow-hidden">

        <div className="p-8 pb-6 flex flex-col items-center border-b border-slate-100 dark:border-slate-800/30">
          <h1 className="brand-title text-2xl text-ink">SICAR</h1>
          <p className="caption-text mt-1">Acesso Restrito</p>
        </div>

        <form onSubmit={handleSubmit} className="p-8 space-y-6">
          {error && (
            <div role="alert" className="feedback-error p-3 rounded-xl text-sm font-medium text-center">
              {error}
            </div>
          )}

          <TextField
                label="Usuário"
                id={usernameId}
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                type="text"
                placeholder="Digite seu usuário"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
          />

          <TextField
                label="Senha"
                id={passwordId}
                name="password"
                autoComplete="current-password"
                type="password"
                placeholder="Digite sua senha"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
          />

          <Button
            type="submit"
            busy={isLoading}
            disabled={isLoading || !username || !password}
            className="w-full py-3.5  cursor-pointer"
          >
            {isLoading ? 'Autenticando...' : 'Entrar no Sistema'}
          </Button>

          {onBack && (
            <Button variant="quiet"
              type="button"
              onClick={onBack}
              className="mt-4 w-full"
            >
              <ArrowLeft className="w-4 h-4" /> Voltar
            </Button>
          )}
        </form>
      </div>
    </div>
  );
}
