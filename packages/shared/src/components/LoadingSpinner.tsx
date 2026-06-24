export default function LoadingSpinner({ message = 'Loading...' }: { message?: string }) {
  return (
    <div className="flex h-64 items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-violet-500 border-t-transparent" />
      <span className="ml-3 text-slate-400 font-medium">{message}</span>
    </div>
  );
}
