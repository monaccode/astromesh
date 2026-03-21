interface SkeletonProps {
  className?: string;
  lines?: number;
}

const widths = ["w-full", "w-4/5", "w-3/5", "w-full", "w-4/5", "w-2/3"];

export function Skeleton({ className, lines }: SkeletonProps) {
  if (lines) {
    return (
      <div className="space-y-3">
        {Array.from({ length: lines }, (_, i) => (
          <div
            key={i}
            className={`h-4 bg-gray-700 animate-pulse rounded ${widths[i % widths.length]}`}
          />
        ))}
      </div>
    );
  }

  return <div className={`bg-gray-700 animate-pulse rounded ${className ?? "h-4 w-full"}`} />;
}
