import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

/*
 * Buttons per the TradingView reference (§5): 28px pills, tone shifts instead of outlines.
 *  default     raised #303030 pill, text-1
 *  primary     #2962ff pill, white text
 *  outline     transparent pill with a 1px #303030 border
 *  ghost       transparent, hover #2a2a2a
 *  destructive #f23645 tinted
 */
const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center border border-transparent bg-clip-padding text-[14px] font-normal whitespace-nowrap transition-colors outline-none select-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:text-text-disabled disabled:opacity-80 aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-raised text-text-1 hover:bg-[#3a3a3a] aria-expanded:bg-[#3a3a3a]",
        primary: "bg-primary text-primary-foreground hover:bg-accent-hover",
        outline:
          "border-border bg-transparent text-text-1 hover:bg-hover aria-expanded:bg-hover",
        secondary: "bg-raised text-text-1 hover:bg-[#3a3a3a] aria-expanded:bg-[#3a3a3a]",
        ghost: "text-text-2 hover:bg-hover hover:text-text-1 aria-expanded:bg-hover aria-expanded:text-text-1",
        destructive:
          "bg-down-soft text-down hover:bg-down hover:text-white focus-visible:ring-destructive",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-7 gap-1.5 rounded-[var(--r-pill)] px-[11px]",
        xs: "h-6 gap-1 rounded-[var(--r-pill)] px-2 text-xs [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-[var(--r-pill)] px-2.5 text-[13px] [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 rounded-[var(--r-pill)] px-4",
        chip: "h-[34px] gap-1.5 rounded-[var(--r-md)] px-3",
        icon: "size-7 rounded-[var(--r-sm)]",
        "icon-xs": "size-6 rounded-[var(--r-sm)] [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7 rounded-[var(--r-sm)]",
        "icon-lg": "size-9 rounded-[var(--r-sm)]",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
