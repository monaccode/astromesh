import { CheckCircle2, XCircle, Info, AlertTriangle, X } from "lucide-react";
import { useToastStore, type Toast as ToastType } from "../../stores/toast";

const config: Record<
  ToastType["type"],
  { icon: typeof CheckCircle2; color: string; border: string }
> = {
  success: { icon: CheckCircle2, color: "text-green-400", border: "border-l-green-400" },
  error: { icon: XCircle, color: "text-red-400", border: "border-l-red-400" },
  info: { icon: Info, color: "text-cyan-400", border: "border-l-cyan-400" },
  warning: { icon: AlertTriangle, color: "text-yellow-400", border: "border-l-yellow-400" },
};

function Toast({ toast }: { toast: ToastType }) {
  const removeToast = useToastStore((s) => s.removeToast);
  const { icon: Icon, color, border } = config[toast.type];

  return (
    <div
      className={`flex items-center gap-3 bg-gray-800 border border-gray-700 ${border} border-l-2 rounded-lg px-4 py-3 shadow-lg animate-slide-in min-w-[280px] max-w-[400px]`}
    >
      <Icon size={18} className={`${color} flex-shrink-0`} />
      <span className="text-sm text-gray-200 flex-1">{toast.message}</span>
      <button
        onClick={() => removeToast(toast.id)}
        className="text-gray-500 hover:text-gray-300 transition-colors flex-shrink-0"
      >
        <X size={14} />
      </button>
    </div>
  );
}

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} />
      ))}
    </div>
  );
}
