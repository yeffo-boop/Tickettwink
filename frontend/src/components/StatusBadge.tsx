const STATUS_STYLES: Record<string, string> = {
  draft: "badge-gray",
  planned: "badge-blue",
  confirmed: "badge-green",
  showtime_changed: "badge-amber",
  cancelled: "badge-red",
  completed: "badge-gray",
};

export default function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_STYLES[status] ?? "badge-gray";
  return <span className={`badge ${cls}`}>{status.replace(/_/g, " ")}</span>;
}
