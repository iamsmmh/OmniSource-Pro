"""Admin API + dashboard for OmniSource.

JSON endpoints under ``/api/v1/admin`` (API-key protected via the router
dependency registered in ``api.main``) expose pipeline health, sync jobs,
and the quarantine review queue. ``GET /admin`` renders a small dependency-free
HTML dashboard consuming those endpoints.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnisource.api.dependencies import get_db
from omnisource.core.models.application import Application
from omnisource.core.models.quarantine import Quarantine, QuarantineStatus
from omnisource.core.models.repository import Repository
from omnisource.core.models.source import Source
from omnisource.core.models.sync import SyncJob, SyncJobStatus
from omnisource.core.repositories.sync import SyncRepository

router = APIRouter()


# --- JSON endpoints -------------------------------------------------------------


@router.get("/overview")
async def overview(session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """High-level pipeline counts for the dashboard header."""
    apps_total = (await session.execute(select(func.count()).select_from(Application))).scalar_one()
    repos_total = (await session.execute(select(func.count()).select_from(Repository))).scalar_one()
    sources_total = (await session.execute(select(func.count()).select_from(Source))).scalar_one()
    jobs_running = (
        await session.execute(
            select(func.count()).select_from(SyncJob).where(SyncJob.status == SyncJobStatus.RUNNING)
        )
    ).scalar_one()
    quarantined = (
        await session.execute(
            select(func.count())
            .select_from(Quarantine)
            .where(
                Quarantine.status.in_(
                    [QuarantineStatus.QUARANTINED, QuarantineStatus.REVIEW_PENDING]
                )
            )
        )
    ).scalar_one()

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "applications": int(apps_total),
        "repositories": int(repos_total),
        "sources": int(sources_total),
        "jobs_running": int(jobs_running),
        "quarantined_open": int(quarantined),
    }


@router.get("/jobs")
async def jobs(limit: int = 25, session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Most recent sync jobs with status."""
    recent = (
        await session.execute(
            select(SyncJob).order_by(desc(SyncJob.created_at)).limit(min(limit, 100))
        )
    ).scalars()
    return {
        "jobs": [
            {
                "id": str(job.id),
                "type": str(getattr(job, "job_type", "")),
                "status": str(getattr(job, "status", "")),
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.completed_at.isoformat() if job.completed_at else None,
                "error": getattr(job, "error_message", None),
            }
            for job in recent
        ]
    }


@router.get("/quarantine")
async def quarantine_queue(session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Assets/apps currently quarantined pending review."""
    rows = (
        (
            await session.execute(
                select(Quarantine)
                .where(
                    Quarantine.status.in_(
                        [QuarantineStatus.QUARANTINED, QuarantineStatus.REVIEW_PENDING]
                    )
                )
                .order_by(desc(Quarantine.quarantined_at))
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": str(q.id),
                "reason": str(q.reason) if q.reason else None,
                "description": q.description,
                "details": q.details if isinstance(q.details, dict) else {},
                "asset_id": str(q.asset_id) if q.asset_id else None,
                "status": str(q.status),
                "quarantined_at": q.quarantined_at.isoformat() if q.quarantined_at else None,
            }
            for q in rows
        ]
    }


@router.get("/sources")
async def sources_health(session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Per-source repository counts and sync cursors."""
    rows = (await session.execute(select(Source).order_by(Source.name))).scalars().all()
    count_rows = await session.execute(
        select(Repository.source_id, func.count()).group_by(Repository.source_id)
    )
    repo_counts: dict[UUID, int] = dict(count_rows.all())  # type: ignore[arg-type]
    return {
        "sources": [
            {
                "id": str(s.id),
                "name": s.name,
                "type": str(s.source_type),
                "base_url": s.base_url,
                "is_active": s.is_active,
                "repositories": int(repo_counts.get(s.id, 0)),
            }
            for s in rows
        ]
    }


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Re-enqueue a failed job by id."""
    from omnisource.automation.queue import enqueue_job

    sync_repo = SyncRepository(session)
    job = await session.get(SyncJob, job_id)
    if job is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Job not found")

    new_job = await sync_repo.create_job(
        job_type=job.job_type,
        source_id=job.source_id,
        repository_id=job.repository_id,
        application_id=job.application_id,
    )
    await session.commit()
    await enqueue_job(
        {
            "type": str(job.job_type),
            "job_id": str(new_job.id),
        }
    )
    return {"status": "requeued", "original_job_id": job_id, "new_job_id": str(new_job.id)}


# --- HTML dashboard ---------------------------------------------------------------

_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>OmniSource Admin</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { --bg:#0f1117; --card:#181b23; --fg:#e6e6e6; --muted:#8b93a7; --accent:#4f8cff; --ok:#3fb96f; --warn:#e0a53c; --err:#e05c5c; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--fg); }
  header { padding:20px 28px; border-bottom:1px solid #262a35; display:flex; justify-content:space-between; align-items:center; }
  header h1 { font-size:18px; margin:0; }
  header span { color:var(--muted); font-size:13px; }
  main { padding:24px 28px; max-width:1200px; margin:0 auto; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin-bottom:24px; }
  .card { background:var(--card); border-radius:10px; padding:16px; }
  .card .value { font-size:28px; font-weight:700; }
  .card .label { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }
  section { background:var(--card); border-radius:10px; padding:18px; margin-bottom:20px; }
  section h2 { font-size:15px; margin:0 0 12px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; color:var(--muted); font-weight:600; padding:6px 8px; border-bottom:1px solid #262a35; }
  td { padding:6px 8px; border-bottom:1px solid #20242f; }
  .pill { display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:600; }
  .ok { background:#123824; color:var(--ok); }
  .run { background:#152a45; color:var(--accent); }
  .fail { background:#3a1a1a; color:var(--err); }
  .warn { background:#3a2d12; color:var(--warn); }
  button { background:var(--accent); border:0; color:#fff; border-radius:6px; padding:4px 12px; font-size:12px; cursor:pointer; }
  .error { color:var(--err); font-size:12px; }
</style>
</head>
<body>
<header><h1>OmniSource Admin</h1><span id="ts"></span></header>
<main>
  <div class="cards" id="cards"></div>
  <section><h2>Recent sync jobs</h2><table id="jobs"><thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Created</th><th></th></tr></thead><tbody></tbody></table></section>
  <section><h2>Quarantine queue</h2><table id="quarantine"><thead><tr><th>Reason</th><th>Details</th><th>Status</th><th>Created</th></tr></thead><tbody></tbody></table></section>
  <section><h2>Sources</h2><table id="sources"><thead><tr><th>Name</th><th>Type</th><th>Active</th><th>Repositories</th></tr></thead><tbody></tbody></table></section>
</main>
<script>
const esc = s => s == null ? "" : String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const pill = s => s === "completed" ? '<span class="pill ok">completed</span>'
             : s === "running" ? '<span class="pill run">running</span>'
             : s === "failed" ? '<span class="pill fail">failed</span>'
             : '<span class="pill warn">' + esc(s || "unknown") + '</span>';
let KEY = localStorage.getItem("omnisource_key");
async function j(url, opts) {
  const r = await fetch(url, Object.assign({headers: {"X-API-Key": KEY || ""}}, opts || {}));
  if (r.status === 401) {
    KEY = prompt("Admin API key:");
    localStorage.setItem("omnisource_key", KEY || "");
    if (KEY) return j(url, opts);
    throw new Error("unauthorized");
  }
  if (!r.ok) throw new Error(url + ": " + r.status);
  return r.json();
}
async function refresh() {
  try {
    const [ov, jobs, q, src] = await Promise.all([
      j("/api/v1/admin/overview"), j("/api/v1/admin/jobs?limit=15"),
      j("/api/v1/admin/quarantine"), j("/api/v1/admin/sources"),
    ]);
    document.getElementById("ts").textContent = "updated " + new Date(ov.timestamp).toLocaleTimeString();
    document.getElementById("cards").innerHTML = [
      ["Applications", ov.applications], ["Repositories", ov.repositories],
      ["Sources", ov.sources], ["Running jobs", ov.jobs_running],
      ["Quarantined", ov.quarantined_open],
    ].map(([l, v]) => '<div class="card"><div class="value">' + v + '</div><div class="label">' + l + '</div></div>').join("");
    document.querySelector("#jobs tbody").innerHTML = jobs.jobs.map(jd =>
      '<tr><td>' + esc(jd.id.slice(0, 8)) + '</td><td>' + esc(jd.type) + '</td><td>' + pill(jd.status) + '</td>' +
      '<td>' + esc(jd.created_at ? jd.created_at.slice(0, 19).replace("T", " ") : "") + '</td>' +
      '<td>' + (jd.status === "failed" ? '<button onclick="retry(\'' + jd.id + '\')">Retry</button>' : "") + '</td></tr>').join("");
    document.querySelector("#quarantine tbody").innerHTML = q.items.length
      ? q.items.map(i => '<tr><td>' + esc(i.reason) + '</td><td class="error">' + esc(i.description) + '</td><td>' + pill(i.status) + '</td><td>' + esc(i.quarantined_at ? i.quarantined_at.slice(0, 19) : "") + '</td></tr>').join("")
      : '<tr><td colspan="4" style="color:var(--muted)">Nothing quarantined</td></tr>';
    document.querySelector("#sources tbody").innerHTML = src.sources.map(s =>
      '<tr><td>' + esc(s.name) + '</td><td>' + esc(s.type) + '</td><td>' + (s.is_active ? "yes" : "no") + '</td><td>' + s.repositories + '</td></tr>').join("");
  } catch (e) {
    document.getElementById("ts").textContent = String(e);
  }
}
async function retry(id) {
  await j("/api/v1/admin/jobs/" + id + "/retry", {method: "POST"});
  refresh();
}
refresh();
setInterval(refresh, 15000);
</script>
</body>
</html>"""


def admin_dashboard_html() -> str:
    """Return the dashboard HTML (served without auth at /admin)."""
    return _DASHBOARD


__all__ = ["admin_dashboard_html", "router"]
