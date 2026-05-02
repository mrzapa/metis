import { DotMatrixLoader } from "@/components/brand";

export default function RootLoading() {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="status"
      aria-label="Loading"
    >
      <div className="flex flex-col items-center gap-4 text-cyan-400/80">
        <DotMatrixLoader name="breath" size={48} />
        <p className="text-xs text-muted-foreground tracking-widest uppercase">
          Loading
        </p>
      </div>
    </div>
  );
}
