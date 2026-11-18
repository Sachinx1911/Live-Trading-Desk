"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { ApiRequestError } from "@/lib/api/client";
import type { SavedScan, SavedScanIn, ScanFilters, ScanSort } from "@/lib/api/generated";
import { useCreateSavedScan, useDeleteSavedScan, useUpdateSavedScan } from "@/lib/api/scanner";

/**
 * Save / Update / Delete a scan. Presets are read-only: saving while a preset is active
 * creates a copy under the user's name.
 */
export function SaveScanDialog({
  open,
  onOpenChange,
  current,
  base,
  onSaved,
  onDeleted,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  current: { filters: ScanFilters; sort: ScanSort | null; columns: string[] };
  base: SavedScan | null;
  onSaved: (s: SavedScan) => void;
  onDeleted: () => void;
}) {
  const editable = base != null && !base.is_preset;
  const [name, setName] = useState(base ? (base.is_preset ? `${base.name} (copy)` : base.name) : "");
  const [desc, setDesc] = useState(base?.description ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const create = useCreateSavedScan();
  const update = useUpdateSavedScan();
  const del = useDeleteSavedScan();
  const pending = create.isPending || update.isPending || del.isPending;
  const error = [create.error, update.error, del.error].find((e) => e instanceof ApiRequestError) as ApiRequestError | undefined;

  const body = (): SavedScanIn => ({ name: name.trim(), description: desc.trim() || null, filters: current.filters, sort: current.sort, columns: current.columns });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="p-5">
        <SheetHeader className="p-0">
          <SheetTitle>{editable ? "Update scan" : "Save scan"}</SheetTitle>
          <SheetDescription className="text-text-3">
            {base?.is_preset ? "Presets cannot be changed; this saves a copy with your filters." : "Filters, sort and columns are saved together."}
          </SheetDescription>
        </SheetHeader>
        <form
          className="flex flex-col gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            const s = editable ? await update.mutateAsync({ id: base.id, ...body() }) : await create.mutateAsync(body());
            onSaved(s);
            onOpenChange(false);
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="scan-name">Name</Label>
            <Input id="scan-name" required value={name} onChange={(e) => setName(e.target.value)} className="h-8 text-[13px]" autoFocus />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="scan-desc">Description</Label>
            <Input id="scan-desc" value={desc} onChange={(e) => setDesc(e.target.value)} className="h-8 text-[13px]" />
          </div>
          <div className="text-[12px] text-text-3">
            {current.filters.all.length} all-of · {current.filters.any.length} any-of · {current.columns.length} columns · sort {current.sort ? `${current.sort.field} ${current.sort.dir}` : "default"}
          </div>
          {error && <div className="text-[12px] text-down">{error.message}</div>}
          <div className="flex items-center gap-2">
            <Button type="submit" variant="primary" size="sm" disabled={pending || !name.trim()}>
              {editable ? "Update" : base?.is_preset ? "Save copy" : "Save"}
            </Button>
            {editable && !confirmDelete && (
              <Button type="button" variant="ghost" size="sm" className="text-down" onClick={() => setConfirmDelete(true)}>Delete</Button>
            )}
            {editable && confirmDelete && (
              <Button
                type="button"
                variant="destructive"
                size="sm"
                disabled={pending}
                onClick={async () => {
                  await del.mutateAsync(base.id);
                  onDeleted();
                  onOpenChange(false);
                }}
              >
                Confirm delete
              </Button>
            )}
          </div>
        </form>
      </SheetContent>
    </Sheet>
  );
}
