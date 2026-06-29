import { useState } from 'react';
import { Trash2, X } from 'lucide-react';

interface DeleteConfirmationModalProps {
  formTitle: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}

export const DeleteConfirmationModal = ({
  formTitle,
  onConfirm,
  onCancel,
  loading,
}: DeleteConfirmationModalProps) => {
  const [input, setInput] = useState('');
  const canDelete = input === formTitle;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl w-full max-w-md p-6 space-y-5">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-bold text-white">
            Delete &ldquo;{formTitle}&rdquo;?
          </h3>
          <button onClick={onCancel} className="text-slate-500 hover:text-slate-300 cursor-pointer">
            <X size={18} />
          </button>
        </div>

        <p className="text-xs text-slate-400">
          Type the form name exactly to confirm deletion. This will permanently remove the form and all associated leads.
        </p>

        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="w-full rounded-xl border border-slate-800 bg-slate-950 px-4 py-3 text-sm text-slate-200 focus:border-rose-600 focus:outline-none transition-all"
          placeholder={formTitle}
          autoFocus
          onKeyDown={(e) => {
            if (canDelete && e.key === 'Enter') onConfirm();
          }}
        />

        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2.5 text-xs font-semibold text-slate-400 hover:text-slate-200 rounded-xl hover:bg-slate-800 transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!canDelete || loading}
            className="flex items-center gap-2 px-4 py-2.5 bg-rose-600 text-xs font-semibold text-white rounded-xl hover:bg-rose-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            <Trash2 size={14} />
            {loading ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
};
