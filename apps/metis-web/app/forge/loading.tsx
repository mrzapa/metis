import { Loader2 } from "lucide-react";

export default function ForgeLoading() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <Loader2 className="size-6 animate-spin text-muted-foreground/50" />
    </div>
  );
}
