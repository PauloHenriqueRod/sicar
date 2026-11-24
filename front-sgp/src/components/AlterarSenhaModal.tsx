import { apiBaseUrl } from '../utils/api';
import { useState } from 'react';
import { Button, TextField, Modal } from './ui';
import { Eye, EyeOff, CheckCircle } from 'lucide-react';



interface Props {
  onClose: () => void;
}

const PASSWORD_REGEX = /(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&]).{8,}/;

export function AlterarSenhaModal({ onClose }: Props) {
  const [senhaAtual, setSenhaAtual] = useState('');
  const [novaSenha, setNovaSenha] = useState('');
  const [confirmaSenha, setConfirmaSenha] = useState('');

  const [showAtual, setShowAtual] = useState(false);
  const [showNova, setShowNova] = useState(false);
  const [showConfirma, setShowConfirma] = useState(false);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const senhaForte = PASSWORD_REGEX.test(novaSenha);
  const senhasIguais = novaSenha === confirmaSenha;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!senhasIguais) {
      setError('As senhas não coincidem.');
      return;
    }
    if (!senhaForte) {
      setError('A nova senha não atende aos requisitos de segurança.');
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/auth/me/alterar-senha`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          current_password: senhaAtual,
          new_password: novaSenha,
        }),
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Erro ao alterar senha');

      setSuccess(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err instanceof Error ? err.message : String(err) : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal title="Alterar senha" description="Informe a senha atual e escolha uma nova senha." onClose={onClose} busy={isLoading}>
      <div className="p-6">
        {success ? (
          <div role="status" className="feedback-success rounded-control flex flex-col items-center justify-center gap-4 px-4 py-6">
            <CheckCircle className="h-8 w-8" aria-hidden="true" />
            <div className="text-center">
              <h3 className="text-lg font-semibold leading-relaxed">Senha Alterada!</h3>
              <p className="text-sm mt-1">Sua senha foi atualizada com sucesso.</p>
            </div>
            <Button onClick={onClose}>Fechar</Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            {error && <div role="alert" className="feedback-error rounded-control p-3 text-sm">{error}</div>}
            <TextField label="Senha atual" type={showAtual ? 'text' : 'password'} autoComplete="current-password" value={senhaAtual} onChange={event => setSenhaAtual(event.target.value)} required disabled={isLoading}
              trailing={<Button variant="icon" disabled={isLoading} aria-label={showAtual ? 'Ocultar senha atual' : 'Mostrar senha atual'} aria-pressed={showAtual} onClick={() => setShowAtual(!showAtual)}>{showAtual ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}</Button>}
            />
            <TextField label="Nova senha" type={showNova ? 'text' : 'password'} autoComplete="new-password" value={novaSenha} onChange={event => setNovaSenha(event.target.value)} required disabled={isLoading}
              hint={senhaForte ? '✓ Senha forte' : 'Mínimo de 8 caracteres, 1 maiúscula, 1 número e 1 especial (@$!%*?&).'}
              error={novaSenha.length > 0 && !senhaForte ? 'A nova senha ainda não atende aos requisitos.' : undefined}
              className={novaSenha.length > 0 && senhaForte ? 'border-success' : ''}
              trailing={<Button variant="icon" disabled={isLoading} aria-label={showNova ? 'Ocultar nova senha' : 'Mostrar nova senha'} aria-pressed={showNova} onClick={() => setShowNova(!showNova)}>{showNova ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}</Button>}
            />
            <TextField label="Confirmar nova senha" type={showConfirma ? 'text' : 'password'} autoComplete="new-password" value={confirmaSenha} onChange={event => setConfirmaSenha(event.target.value)} required disabled={isLoading}
              error={confirmaSenha.length > 0 && !senhasIguais ? 'As senhas não coincidem.' : undefined}
              className={confirmaSenha.length > 0 && senhasIguais ? 'border-success' : ''}
              trailing={<Button variant="icon" disabled={isLoading} aria-label={showConfirma ? 'Ocultar confirmação de senha' : 'Mostrar confirmação de senha'} aria-pressed={showConfirma} onClick={() => setShowConfirma(!showConfirma)}>{showConfirma ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}</Button>}
            />
            <Button type="submit" busy={isLoading} disabled={!senhaAtual || !novaSenha || !confirmaSenha} className="w-full">{isLoading ? 'Salvando...' : 'Alterar Senha'}</Button>
          </form>
        )}
      </div>
    </Modal>
  );
}
