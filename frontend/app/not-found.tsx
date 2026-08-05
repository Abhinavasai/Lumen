import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
      <h1 className="text-6xl font-bold gradient-text">404</h1>
      <p className="text-lg text-text-secondary">Page not found</p>
      <Link
        href="/"
        className="mt-4 inline-flex items-center gap-2 rounded-[10px] bg-indigo-50 border border-indigo-200 px-4 py-2 text-sm font-medium text-primary-light transition-colors hover:bg-primary/20"
      >
        Back to Dashboard
      </Link>
    </div>
  );
}
