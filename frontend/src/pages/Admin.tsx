import { useEffect, useState } from "react";
import { api } from "../api/client";

interface DeadLetter {
  id: number;
  user_id: number | null;
  notification_type: string;
  attempt_count: number;
  error_message: string | null;
}

interface RefundDue {
  id: number;
  user_id: number;
  amount_received_cents: number;
  amount_expected_cents: number;
}

export default function Admin() {
  const [providerHealth, setProviderHealth] = useState<Record<string, string>>({});
  const [deadLetters, setDeadLetters] = useState<DeadLetter[]>([]);
  const [refundsDue, setRefundsDue] = useState<RefundDue[]>([]);

  async function loadAll() {
    setProviderHealth(await api.get("/api/admin/provider-health"));
    setDeadLetters(await api.get("/api/admin/notifications/dead-letter"));
    setRefundsDue(await api.get("/api/admin/payments/refunds-due"));
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function requeue(id: number) {
    await api.post(`/api/admin/notifications/${id}/requeue`);
    await loadAll();
  }

  async function markRefunded(id: number) {
    await api.post(`/api/admin/payments/${id}/mark-refunded`);
    await loadAll();
  }

  return (
    <div className="page">
      <h1>Admin Dashboard</h1>

      <section className="card">
        <h2>Provider Health</h2>
        {Object.keys(providerHealth).length === 0 && <p className="hint">No providers have made calls yet.</p>}
        {Object.entries(providerHealth).map(([name, state]) => (
          <div key={name} className="ticket-row">
            <span>{name}</span>
            <span className={`badge ${state === "open" ? "badge-red" : state === "half_open" ? "badge-amber" : "badge-green"}`}>
              {state}
            </span>
          </div>
        ))}
      </section>

      <section className="card">
        <h2>Failed Notifications ({deadLetters.length})</h2>
        {deadLetters.length === 0 && <p className="hint">Nothing stuck — all notifications delivered.</p>}
        {deadLetters.map((n) => (
          <div key={n.id} className="ticket-row">
            <span>
              {n.notification_type} → user #{n.user_id ?? "?"} ({n.attempt_count} attempts)
            </span>
            <span className="hint">{n.error_message}</span>
            <button className="btn" onClick={() => requeue(n.id)}>
              Retry
            </button>
          </div>
        ))}
      </section>

      <section className="card">
        <h2>Refunds Due ({refundsDue.length})</h2>
        {refundsDue.length === 0 && <p className="hint">No refunds pending.</p>}
        {refundsDue.map((p) => (
          <div key={p.id} className="ticket-row">
            <span>
              User #{p.user_id}: ${(p.amount_received_cents / 100).toFixed(2)} received (
              {(p.amount_received_cents - p.amount_expected_cents) >= 0 ? "+" : ""}
              ${((p.amount_received_cents - p.amount_expected_cents) / 100).toFixed(2)} vs. expected)
            </span>
            <button className="btn" onClick={() => markRefunded(p.id)}>
              Mark Refunded
            </button>
          </div>
        ))}
      </section>
    </div>
  );
}
