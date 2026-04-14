"use client";

import { useEffect, useMemo, useState } from "react";

const ACTIVE_STATUSES = new Set(["queued", "in_progress"]);

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit"
  }).format(date);
}

function statusLabel(status) {
  if (status === "completed") return "Terminé";
  if (status === "failed") return "Échec";
  if (status === "in_progress") return "En cours";
  if (status === "queued") return "En file";
  return status || "Inconnu";
}

export default function HomePage() {
  const [promptText, setPromptText] = useState("");
  const [jobs, setJobs] = useState([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const hasActiveJobs = useMemo(
    () => jobs.some((job) => ACTIVE_STATUSES.has(job.status)),
    [jobs]
  );

  async function fetchJobs(refresh = false) {
    try {
      const url = refresh ? "/api/jobs?refresh=1" : "/api/jobs";
      const res = await fetch(url, { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Impossible de récupérer l'historique.");
      }
      setJobs(data.jobs || []);
    } catch (err) {
      setError(err.message || "Erreur réseau.");
    } finally {
      setLoadingJobs(false);
    }
  }

  useEffect(() => {
    fetchJobs(true);
  }, []);

  useEffect(() => {
    if (!hasActiveJobs) return;
    const timer = setInterval(() => {
      fetchJobs(true);
    }, 4000);
    return () => clearInterval(timer);
  }, [hasActiveJobs]);

  async function onSubmit(event) {
    event.preventDefault();
    setError("");

    const text = promptText.trim();
    if (!text) {
      setError("Ajoute un texte avant de lancer.");
      return;
    }

    try {
      setSubmitting(true);
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Impossible de créer la vidéo.");
      }
      setPromptText("");
      await fetchJobs(true);
    } catch (err) {
      setError(err.message || "Erreur pendant la génération.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page">
      <section className="shell">
        <header className="header">
          <h1>Glyce Video Studio</h1>
          <p>Dépose un texte, on le convertit en .md puis en .mp4.</p>
        </header>

        <form className="card composer" onSubmit={onSubmit}>
          <label htmlFor="prompt-input">Texte vidéo</label>
          <textarea
            id="prompt-input"
            value={promptText}
            onChange={(event) => setPromptText(event.target.value)}
            placeholder="Exemple : Les 3 erreurs du petit-déj qui te donnent faim avant 11h..."
            rows={8}
          />
          <button type="submit" disabled={submitting}>
            {submitting ? "Génération..." : "Créer la vidéo"}
          </button>
          <p className="hint">
            Historique conservé 24h. Les vidéos expirées sont supprimées automatiquement.
          </p>
        </form>

        {error ? <p className="error">{error}</p> : null}

        <section className="history">
          <div className="historyHead">
            <h2>Historique (24h)</h2>
            <button type="button" className="ghost" onClick={() => fetchJobs(true)}>
              Rafraîchir
            </button>
          </div>

          {loadingJobs ? <p className="hint">Chargement...</p> : null}

          {!loadingJobs && jobs.length === 0 ? (
            <p className="hint">Aucune vidéo pour le moment.</p>
          ) : null}

          <div className="list">
            {jobs.map((job) => (
              <article className="card item" key={job.id}>
                <div className="row">
                  <strong>#{job.id.slice(0, 8)}</strong>
                  <span className={`badge ${job.status || ""}`}>{statusLabel(job.status)}</span>
                </div>
                <p className="meta">Créé le {formatDate(job.createdAt)}</p>
                <p className="preview">{job.previewText || "Aperçu indisponible"}</p>
                <div className="actions">
                  {job.sourceMarkdownUrl ? (
                    <a href={job.sourceMarkdownUrl} target="_blank" rel="noreferrer">
                      Voir .md
                    </a>
                  ) : null}
                  {job.outputVideoUrl ? (
                    <a href={job.outputVideoUrl} target="_blank" rel="noreferrer">
                      Voir .mp4
                    </a>
                  ) : null}
                </div>
                {job.errorMessage ? <p className="error small">{job.errorMessage}</p> : null}
              </article>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}
