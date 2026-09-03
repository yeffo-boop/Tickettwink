import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Nav() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  if (!user) return null;

  return (
    <nav className="nav">
      <Link to="/" className="nav-brand">
        🎟️ Ticket Twink
      </Link>
      <div className="nav-links">
        {user.role === "admin" && <Link to="/admin">Admin</Link>}
        <span className="nav-user">{user.display_name}</span>
        <button
          className="btn-link"
          onClick={() => {
            logout();
            navigate("/login");
          }}
        >
          Sign out
        </button>
      </div>
    </nav>
  );
}
