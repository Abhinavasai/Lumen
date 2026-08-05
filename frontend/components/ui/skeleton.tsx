import { cn } from "@/lib/utils";

function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("bg-slate-100 rounded-md animate-pulse", className)}
      {...props}
    />
  );
}

export { Skeleton };
