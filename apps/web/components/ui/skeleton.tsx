import { cn } from "cn"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-[var(--r-sm)] bg-app", className)}
      {...props}
    />
  )
}

export { Skeleton }
