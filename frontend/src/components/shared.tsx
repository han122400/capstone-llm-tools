"use client";
import type { ReactNode } from "react";
import { Inbox, Info, X } from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import { cn } from "@/lib/utils";
import { statusLabels } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty as EmptyRoot, EmptyHeader, EmptyTitle, EmptyDescription, EmptyContent, EmptyMedia } from "@/components/ui/empty";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Field as FieldRoot, FieldLabel, FieldDescription } from "@/components/ui/field";

export { Button, Badge };
export function Panel({title,description,action,children,className}: {title?:string;description?:ReactNode;action?:ReactNode;children:ReactNode;className?:string}) {
  return <Card className={cn("min-w-0 gap-0 py-0 shadow-none",className)}>
    {(title || action) && <CardHeader className="flex flex-row items-start justify-between gap-4 px-5 pt-5 pb-4">
      <div>{title && <CardTitle className="text-[18px] leading-snug">{title}</CardTitle>}{description && <CardDescription className="mt-1 text-xs leading-relaxed">{description}</CardDescription>}</div>{action}
    </CardHeader>}
    <CardContent className={cn("px-5 pb-5",!title && !action && "pt-5")}>{children}</CardContent>
  </Card>;
}
export function Status({value}: {value:string | null | undefined}) {
  const good = value === "SUCCESS" || value === "COMPLETED" || value === "NORMAL";
  const bad = value === "ERROR" || value === "INJECTION" || value === "INTERRUPTED";
  return <Badge variant={bad ? "destructive" : good ? "secondary" : "outline"}>{value ? statusLabels[value] || value : "N/A"}</Badge>;
}
export function Empty({title="아직 실행된 평가가 없습니다",description,action}: {title?:string;description?:ReactNode;action?:ReactNode}) {
  return <EmptyRoot className="min-h-44"><EmptyHeader><EmptyMedia variant="icon"><Inbox strokeWidth={1.4}/></EmptyMedia><EmptyTitle>{title}</EmptyTitle>{description&&<EmptyDescription>{description}</EmptyDescription>}</EmptyHeader>{action&&<EmptyContent>{action}</EmptyContent>}</EmptyRoot>;
}
export function Notice({children,variant="info"}: {children:ReactNode;variant?:"info"|"warning"|"error"}) {
  return <Alert role={variant==="error"?"alert":"note"} variant={variant==="error"?"destructive":"default"}><Info/><AlertDescription className="block min-w-0 text-xs leading-relaxed">{children}</AlertDescription></Alert>;
}
export function Field({label,htmlFor,description,children}: {label:string;htmlFor?:string;description?:string;children:ReactNode}) {
  return <FieldRoot className="form-field"><FieldLabel className="form-label" htmlFor={htmlFor}>{label}</FieldLabel>{children}{description && <FieldDescription className="caption">{description}</FieldDescription>}</FieldRoot>;
}
export function Modal({open,onOpenChange,title,description,children}: {open:boolean;onOpenChange:(v:boolean)=>void;title:string;description?:string;children:ReactNode}) {
  return <Dialog.Root open={open} onOpenChange={onOpenChange}><Dialog.Portal>
    <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/30"/>
    <Dialog.Content className="fixed top-1/2 left-1/2 z-50 max-h-[90vh] w-[min(760px,calc(100%-28px))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border bg-white p-6 shadow-xl">
      <div className="row between mb-1"><Dialog.Title className="text-lg font-bold">{title}</Dialog.Title><Dialog.Close asChild><Button variant="ghost" size="icon" aria-label="닫기"><X/></Button></Dialog.Close></div>
      {description && <Dialog.Description className="caption mb-5">{description}</Dialog.Description>}
      {!description && <Dialog.Description className="sr-only">{title} 상세 정보</Dialog.Description>}{children}
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>;
}
export function Download({href,children}: {href:string;children:ReactNode}) {return <Button variant="outline" size="sm" asChild><a href={href} download>{children}</a></Button>;}
