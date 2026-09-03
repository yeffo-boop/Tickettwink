import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";
import StatusBadge from "../components/StatusBadge";

interface MovieNight {
  id: number;
  title: string;
  status: string;
  venue: string | null;
  scheduled_at: string | null;
  price_per_ticket_cents: number | null;
  cancellation_reason: string | null;
}

interface Ticket {
  id: number;
  status: string;
  original_filename: string | null;
  verification_notes: string | null;
}

export default function MovieNightDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [movieNight, setMovieNight] = useState<MovieNight | null>(null);
  const [myTickets, setMyTickets] = useState<Ticket[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadOk, setUploadOk] = useState<string | null>(null);
  const [instructions, setInstructions] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    if (!id) return;
    const mn = await api.get<MovieNight>(`/api/movie-nights/${id}`);
    setMovieNight(mn);
    const tickets = await api.get<Ticket[]>(`/api/tickets/mine/${id}`);
    setMyTickets(tickets);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    setUploadError(null);
    setUploadOk(null);
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;
    try {
      await api.upload(`/api/tickets/movie-nights/${id}/upload`, file);
      setUploadOk("Ticket uploaded! An organizer will verify it.");
      await load();
    } catch (err) {
      // Surfaces malformed-upload / duplicate-ticket errors from the API
      // directly — these are the exact failure scenarios the backend
      // guards against, so the user sees why, not a generic failure.
      setUploadError(err instanceof ApiError ? err.message : "Upload failed.");
    }
  }

  async function loadPaymentInstructions() {
    try {
      const data = await api.get<{ display_instructions: string }>(`/api/payments/movie-nights/${id}/instructions`);
      setInstructions(data.display_instructions);
    } catch (err) {
      setInstructions(err instanceof ApiError ? err.message : "Could not load payment instructions.");
    }
  }

  if (!movieNight) return <div className="page">Loading…</div>;

  return (
    <div className="page">
      <div className="detail-header">
        <h1>{movieNight.title}</h1>
        <StatusBadge status={movieNight.status} />
      </div>
      <p>{movieNight.venue ?? "Venue TBD"}</p>
      <p>{movieNight.scheduled_at ? new Date(movieNight.scheduled_at).toLocaleString() : "Date TBD"}</p>
      {movieNight.status === "cancelled" && (
        <p className="hint-warning">Cancelled: {movieNight.cancellation_reason}</p>
      )}

      <section className="card">
        <h2>Your Ticket</h2>
        {myTickets.length === 0 && <p className="hint">No ticket uploaded yet.</p>}
        {myTickets.map((t) => (
          <div key={t.id} className="ticket-row">
            <span>{t.original_filename ?? `Ticket #${t.id}`}</span>
            <StatusBadge status={t.status} />
            {t.verification_notes && <p className="hint">{t.verification_notes}</p>}
          </div>
        ))}
        <form onSubmit={handleUpload} className="upload-form">
          <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" />
          <button className="btn btn-primary" type="submit">
            Upload Ticket
          </button>
        </form>
        {uploadError && <p className="error-text">{uploadError}</p>}
        {uploadOk && <p className="success-text">{uploadOk}</p>}
      </section>

      {movieNight.price_per_ticket_cents != null && (
        <section className="card">
          <h2>Payment</h2>
          <p>${(movieNight.price_per_ticket_cents / 100).toFixed(2)} per ticket</p>
          <button className="btn" onClick={loadPaymentInstructions}>
            How do I pay?
          </button>
          {instructions && <p className="hint">{instructions}</p>}
        </section>
      )}

      {user?.role === "admin" && <AdminControls movieNightId={movieNight.id} onChange={load} />}
    </div>
  );
}

function AdminControls({ movieNightId, onChange }: { movieNightId: number; onChange: () => void }) {
  const [startsAt, setStartsAt] = useState("");
  const [cinemaName, setCinemaName] = useState("");
  const [cancelReason, setCancelReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  async function setShowtime(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.put(`/api/movie-nights/${movieNightId}/showtime`, {
        starts_at: new Date(startsAt).toISOString(),
        cinema_name: cinemaName,
      });
      setMessage("Showtime updated — attendees notified.");
      onChange();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Failed to update showtime.");
    }
  }

  async function cancelMovieNight() {
    if (!cancelReason) {
      setMessage("Please provide a cancellation reason.");
      return;
    }
    try {
      await api.post(`/api/movie-nights/${movieNightId}/cancel`, { reason: cancelReason });
      setMessage("Movie Night cancelled — attendees notified, refunds flagged.");
      onChange();
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "Failed to cancel.");
    }
  }

  return (
    <section className="card admin-panel">
      <h2>Admin Controls</h2>
      <form onSubmit={setShowtime} className="inline-form">
        <input type="datetime-local" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} required />
        <input
          type="text"
          placeholder="Cinema name"
          value={cinemaName}
          onChange={(e) => setCinemaName(e.target.value)}
          required
        />
        <button className="btn" type="submit">
          Set Showtime
        </button>
      </form>
      <div className="inline-form">
        <input
          type="text"
          placeholder="Cancellation reason"
          value={cancelReason}
          onChange={(e) => setCancelReason(e.target.value)}
        />
        <button className="btn btn-danger" onClick={cancelMovieNight} type="button">
          Cancel Movie Night
        </button>
      </div>
      {message && <p className="hint">{message}</p>}
    </section>
  );
}
