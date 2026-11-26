import { CheckCircle, CircleAlert, Info, LoaderCircle, TriangleAlert } from 'lucide-react';

export interface Feedback {
  tone: 'loading' | 'success' | 'info' | 'warning' | 'error';
  message: string;
  detail?: string;
}

const appearance = {
  loading: { icon: LoaderCircle, classes: 'border-outline bg-accent-soft text-accent-ink' },
  success: { icon: CheckCircle, classes: 'feedback-success' },
  info: { icon: Info, classes: 'border-outline bg-panel text-ink' },
  warning: { icon: TriangleAlert, classes: 'feedback-warning' },
  error: { icon: CircleAlert, classes: 'feedback-error' },
};

export function ActionFeedback({ feedback, inline = false }: { feedback: Feedback | null; inline?: boolean }) {
  const style = feedback ? appearance[feedback.tone] : null;
  const Icon = style?.icon;
  return (
    <div role={feedback?.tone === 'error' ? 'alert' : 'status'} aria-atomic="true" className={style ? `${inline ? '' : 'sticky top-0 z-20'} flex w-full items-start gap-3 rounded-lg border p-4 ${style.classes}` : 'sr-only'}>
      {feedback && Icon && <>
        <Icon aria-hidden="true" className={`mt-0.5 h-5 w-5 shrink-0 ${feedback.tone === 'loading' ? 'animate-spin motion-reduce:animate-none' : ''}`} />
        <div className="min-w-0">
          <p className="break-words text-base font-semibold leading-relaxed">{feedback.message}</p>
          {feedback.detail && <p className="mt-1 break-words text-sm font-normal leading-relaxed">{feedback.detail}</p>}
        </div>
      </>}
    </div>
  );
}
