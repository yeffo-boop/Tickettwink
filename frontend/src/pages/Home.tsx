import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import StatusBadge from "../components/StatusBadge";

interface MovieNight {
  id: number;
  title: string;
  status: string;
  venue: string | null;
  scheduled_at: string | null;
  price_per_ticket_cents: number | null;
  tmdb_cache_stale: boolean;
}

export default function Home() {
  const [movieNights, setMovieNights] = useState<MovieNight[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<MovieNight[]>("/api/movie-nights")
      .then(setMovieNights)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load Movie Nights"));
  }, []);

  return (
    <div className="page">
      <h1>Movie Nights</h1>
      {error && <p className="error-text">{error}</p>}
      {movieNights === null && !error && <p>Loading…</p>}
      {movieNights?.length === 0 && <p className="hint">No Movie Nights yet.</p>}
      <div className="card-grid">
        {movieNights?.map((mn) => (
          <Link to={`/movie-nights/${mn.id}`} key={mn.id} className="card movie-night-card">
            <div className="card-header">
              <h3>{mn.title}</h3>
              <StatusBadge status={mn.status} />
            </div>
            <p>{mn.venue ?? "Venue TBD"}</p>
            <p>{mn.scheduled_at ? new Date(mn.scheduled_at).toLocaleString() : "Date TBD"}</p>
            {mn.tmdb_cache_stale && (
              <p className="hint-warning">⚠ Movie info pending — TMDB was unreachable when this was created</p>
            )}
          </Link>
        ))}
      </div>
    </div>
  );
}
