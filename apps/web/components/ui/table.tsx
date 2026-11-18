"use client"

import * as React from "react"
import { cn } from "cn"

/*
 * Tables per the TradingView screener measurements (§5): 50px bold header, 41px rows
 * (`dense` → 34px), cells `0 12px` (first `0 12px 0 20px`), 1px #1e1e1e row lines, hover
 * #1a1a1a, no zebra. Numeric cells opt in with `className="text-right tabular"`.
 */
function Table({
  className,
  dense = false,
  ...props
}: React.ComponentProps<"table"> & { dense?: boolean }) {
  return (
    <div
      data-slot="table-container"
      className="relative w-full overflow-x-auto"
    >
      <table
        data-slot="table"
        data-dense={dense ? "" : undefined}
        className={cn("group/table w-full caption-bottom text-[14px]", className)}
        {...props}
      />
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("[&_tr]:border-b [&_tr]:border-border [&_tr]:hover:bg-transparent", className)}
      {...props}
    />
  )
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  )
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t border-border font-medium [&>tr]:last:border-b-0",
        className
      )}
      {...props}
    />
  )
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "h-[var(--h-row)] border-b border-border-row transition-colors hover:bg-row-hover has-aria-expanded:bg-row-hover data-[state=selected]:bg-raised group-data-[dense]/table:h-[var(--h-row-dense)]",
        className
      )}
      {...props}
    />
  )
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "h-[var(--h-th)] px-3 text-left align-middle text-[13px] font-bold whitespace-nowrap text-text-2 first:pl-5 group-data-[dense]/table:h-9 [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "px-3 py-0 align-middle whitespace-nowrap first:pl-5 [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}

function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}
