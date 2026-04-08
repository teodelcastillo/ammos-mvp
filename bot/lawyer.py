"""
Portal de abogados — acceso de solo lectura.
Rutas bajo /portal — protegidas con HTTP Basic Auth propio.
Pueden ver casos, clientes y eventos, y solicitar eliminaciones al admin.
"""

import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from db import get_conn, rows_to_list, row_to_dict

router = APIRouter(prefix="/portal")
security = HTTPBasic()

LAWYER_USER = os.getenv("LAWYER_USER", "abogado")
LAWYER_PASSWORD = os.getenv("LAWYER_PASSWORD", "lexia2024")


# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────

def require_lawyer(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username.encode(), LAWYER_USER.encode())
    ok_pass = secrets.compare_digest(credentials.password.encode(), LAWYER_PASSWORD.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ──────────────────────────────────────────────
# HTML helpers
# ──────────────────────────────────────────────

def _page(title: str, body: str, breadcrumb: str = "") -> HTMLResponse:
    crumb = f'<small class="text-muted ms-2">/ {breadcrumb}</small>' if breadcrumb else ""
    html = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — Estudio Del Castillo</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  <style>
    body {{ background: #f8f9fa; }}
    .sidebar {{ min-height: 100vh; background: #1a3a2a; }}
    .sidebar .nav-link {{ color: #adb5bd; border-radius: 6px; margin: 2px 8px; }}
    .sidebar .nav-link:hover, .sidebar .nav-link.active {{ background: #2d6a4a; color: #fff; }}
    .sidebar .brand {{ color: #fff; font-weight: 700; font-size: 1.1rem; }}
    .card {{ border: none; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    .badge-activo {{ background:#198754; }} .badge-cerrado {{ background:#6c757d; }}
    .badge-archivado {{ background:#ffc107; color:#000; }}
    table {{ font-size:.9rem; }}
    .readonly-badge {{ font-size:.7rem; }}
  </style>
</head>
<body>
<div class="d-flex">
  <div class="sidebar d-flex flex-column p-3" style="width:220px;min-width:220px">
    <div class="brand mb-1 px-2 pt-2">
      <i class="bi bi-briefcase-fill me-2"></i>Del Castillo
    </div>
    <div class="px-2 mb-4">
      <span class="badge bg-success readonly-badge">Portal Abogados</span>
    </div>
    <nav class="nav flex-column gap-1">
      <a href="/portal" class="nav-link"><i class="bi bi-speedometer2 me-2"></i>Inicio</a>
      <a href="/portal/casos" class="nav-link"><i class="bi bi-folder2-open me-2"></i>Causas</a>
      <a href="/portal/clientes" class="nav-link"><i class="bi bi-people-fill me-2"></i>Clientes</a>
      <a href="/portal/solicitudes" class="nav-link"><i class="bi bi-inbox me-2"></i>Mis solicitudes</a>
    </nav>
  </div>
  <div class="flex-grow-1 p-4">
    <div class="d-flex align-items-center mb-4">
      <h4 class="mb-0 fw-bold">{title}</h4>{crumb}
    </div>
    {body}
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body></html>"""
    return HTMLResponse(html)


def _badge_estado(estado: str) -> str:
    colors = {"activo": "success", "cerrado": "secondary", "archivado": "warning"}
    c = colors.get(estado, "secondary")
    return f'<span class="badge bg-{c}">{estado}</span>'


TIPO_ICONS = {
    "audiencia": "⚖️", "vencimiento": "⏰", "reunion": "🤝",
    "pericia": "🔬", "mediacion": "🕊️", "otro": "📌",
}


# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def portal_home(user=Depends(require_lawyer)):
    with get_conn() as conn:
        n_casos = conn.execute("SELECT COUNT(*) FROM casos WHERE estado='activo'").fetchone()[0]
        n_clientes = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
        proximos = rows_to_list(conn.execute("""
            SELECT e.titulo, e.fecha, e.tipo, c.caratula, c.id AS caso_id
            FROM eventos_caso e
            JOIN casos c ON c.id = e.caso_id
            WHERE e.fecha >= date('now')
            ORDER BY e.fecha ASC LIMIT 10
        """).fetchall())
        mis_solicitudes = conn.execute(
            "SELECT COUNT(*) FROM solicitudes_baja WHERE estado='pendiente'"
        ).fetchone()[0]

    eventos_html = ""
    for e in proximos:
        icon = TIPO_ICONS.get(e["tipo"], "📌")
        fecha = (e["fecha"] or "")[:10]
        eventos_html += f"""
        <tr>
          <td>{icon} {fecha}</td>
          <td>{e['titulo']}</td>
          <td><a href="/portal/casos/{e['caso_id']}">{e['caratula']}</a></td>
          <td><span class="badge bg-secondary">{e['tipo']}</span></td>
        </tr>"""

    body = f"""
    <div class="row g-3 mb-4">
      <div class="col-md-4">
        <div class="card p-3 text-center">
          <div class="fs-1 text-success"><i class="bi bi-folder2-open"></i></div>
          <div class="fs-3 fw-bold">{n_casos}</div>
          <div class="text-muted">Causas activas</div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="card p-3 text-center">
          <div class="fs-1 text-primary"><i class="bi bi-people-fill"></i></div>
          <div class="fs-3 fw-bold">{n_clientes}</div>
          <div class="text-muted">Clientes</div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="card p-3 text-center">
          <div class="fs-1 text-warning"><i class="bi bi-hourglass-split"></i></div>
          <div class="fs-3 fw-bold">{mis_solicitudes}</div>
          <div class="text-muted">Solicitudes pendientes</div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-header fw-semibold">
        <i class="bi bi-calendar-event me-1"></i>Próximos eventos
      </div>
      <table class="table table-hover mb-0">
        <thead class="table-light">
          <tr><th>Fecha</th><th>Evento</th><th>Causa</th><th>Tipo</th></tr>
        </thead>
        <tbody>
          {eventos_html or '<tr><td colspan="4" class="text-center text-muted py-3">Sin eventos próximos</td></tr>'}
        </tbody>
      </table>
    </div>"""
    return _page("Inicio", body)


# ──────────────────────────────────────────────
# CAUSAS (solo lectura)
# ──────────────────────────────────────────────

@router.get("/casos", response_class=HTMLResponse)
def casos_list(user=Depends(require_lawyer)):
    with get_conn() as conn:
        rows = rows_to_list(conn.execute("""
            SELECT c.id, c.caratula, c.estado, c.materia, c.juzgado,
                   cl.nombre AS cliente
            FROM casos c LEFT JOIN clientes cl ON cl.id=c.cliente_id
            ORDER BY c.caratula
        """).fetchall())

    rows_html = "".join(
        f"""<tr>
          <td><a href="/portal/casos/{r['id']}">{r['caratula']}</a></td>
          <td>{r.get('cliente') or '—'}</td>
          <td>{r.get('materia') or '—'}</td>
          <td>{r.get('juzgado') or '—'}</td>
          <td>{_badge_estado(r['estado'])}</td>
        </tr>"""
        for r in rows
    )
    body = f"""
    <div class="card">
      <table class="table table-hover mb-0">
        <thead class="table-light">
          <tr><th>Carátula</th><th>Cliente</th><th>Materia</th><th>Juzgado</th><th>Estado</th></tr>
        </thead>
        <tbody>
          {rows_html or '<tr><td colspan="5" class="text-center text-muted py-3">Sin causas</td></tr>'}
        </tbody>
      </table>
    </div>"""
    return _page("Causas", body)


@router.get("/casos/{cid}", response_class=HTMLResponse)
def casos_ver(cid: int, user=Depends(require_lawyer)):
    with get_conn() as conn:
        c = row_to_dict(conn.execute("""
            SELECT ca.*, cl.nombre AS cliente_nombre
            FROM casos ca LEFT JOIN clientes cl ON cl.id=ca.cliente_id
            WHERE ca.id=?
        """, (cid,)).fetchone())
        eventos = rows_to_list(conn.execute(
            "SELECT * FROM eventos_caso WHERE caso_id=? ORDER BY fecha DESC", (cid,)
        ).fetchall())

    if not c:
        raise HTTPException(404)

    eventos_html = ""
    for e in eventos:
        icon = TIPO_ICONS.get(e["tipo"], "📌")
        fecha = (e["fecha"] or "")[:10]
        cal_link = f'<a href="{e["calendar_link"]}" target="_blank" class="btn btn-outline-secondary btn-sm ms-2"><i class="bi bi-calendar2-event"></i></a>' if e.get("calendar_link") else ""
        eventos_html += f"""
        <tr>
          <td>{icon} {fecha}</td>
          <td>{e['titulo']}{cal_link}</td>
          <td><span class="badge bg-secondary">{e['tipo']}</span></td>
          <td class="text-muted small">{e.get('notas') or ''}</td>
        </tr>"""

    detail_rows = [
        ("Cliente", c.get("cliente_nombre") or "—"),
        ("N° expediente", c.get("numero") or "—"),
        ("Materia", c.get("materia") or "—"),
        ("Fuero", c.get("fuero") or "—"),
        ("Juzgado", c.get("juzgado") or "—"),
        ("Estado", _badge_estado(c["estado"])),
        ("Mediación", "Sí" if c.get("mediacion") else "No"),
        ("Abogado", c.get("abogado") or "—"),
        ("Notas", c.get("notas") or "—"),
    ]
    detail_html = "".join(
        f'<tr><th class="text-muted fw-normal" style="width:140px">{k}</th><td>{v}</td></tr>'
        for k, v in detail_rows
    )
    if c.get("drive_folder_url"):
        drive_btn = f'<a href="{c["drive_folder_url"]}" target="_blank" class="btn btn-outline-secondary btn-sm"><i class="bi bi-folder2 me-1"></i>Carpeta Drive</a>'
    else:
        drive_btn = ""

    body = f"""
    <div class="d-flex justify-content-between align-items-start mb-3">
      <div>{drive_btn}</div>
      <form method="post" action="/portal/solicitudes/nueva">
        <input type="hidden" name="tipo" value="caso">
        <input type="hidden" name="objeto_id" value="{cid}">
        <input type="hidden" name="objeto_descripcion" value="{c['caratula']}">
        <button type="button" class="btn btn-outline-danger btn-sm"
                data-bs-toggle="modal" data-bs-target="#modalSolicitud">
          <i class="bi bi-trash me-1"></i>Solicitar eliminación
        </button>
      </form>
    </div>

    <!-- Modal solicitud -->
    <div class="modal fade" id="modalSolicitud" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Solicitar eliminación de causa</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <form method="post" action="/portal/solicitudes/nueva">
            <div class="modal-body">
              <input type="hidden" name="tipo" value="caso">
              <input type="hidden" name="objeto_id" value="{cid}">
              <input type="hidden" name="objeto_descripcion" value="{c['caratula']}">
              <p class="text-muted small">La solicitud será enviada al administrador para su aprobación.</p>
              <label class="form-label">Motivo *</label>
              <textarea name="motivo" class="form-control" rows="3" required
                        placeholder="Ej: Causa archivada, expediente duplicado..."></textarea>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
              <button type="submit" class="btn btn-danger">Enviar solicitud</button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-header fw-semibold">{c['caratula']}</div>
      <div class="card-body p-0">
        <table class="table mb-0">{detail_html}</table>
      </div>
    </div>

    <div class="card">
      <div class="card-header fw-semibold">
        <i class="bi bi-clock-history me-1"></i>Historial de eventos
      </div>
      <table class="table table-hover mb-0">
        <thead class="table-light">
          <tr><th>Fecha</th><th>Evento</th><th>Tipo</th><th>Notas</th></tr>
        </thead>
        <tbody>
          {eventos_html or '<tr><td colspan="4" class="text-center text-muted py-3">Sin eventos registrados</td></tr>'}
        </tbody>
      </table>
    </div>"""
    return _page(c["caratula"], body, "Detalle")


# ──────────────────────────────────────────────
# CLIENTES (solo lectura)
# ──────────────────────────────────────────────

@router.get("/clientes", response_class=HTMLResponse)
def clientes_list(user=Depends(require_lawyer)):
    with get_conn() as conn:
        rows = rows_to_list(conn.execute("""
            SELECT c.id, c.nombre, c.cuit, c.email, c.telefono,
                   COUNT(ca.id) AS n_casos
            FROM clientes c
            LEFT JOIN casos ca ON ca.cliente_id=c.id
            GROUP BY c.id ORDER BY c.nombre
        """).fetchall())

    rows_html = "".join(
        f"""<tr>
          <td><a href="/portal/clientes/{r['id']}">{r['nombre']}</a></td>
          <td>{r.get('cuit') or '—'}</td>
          <td>{r.get('email') or '—'}</td>
          <td>{r.get('telefono') or '—'}</td>
          <td><span class="badge bg-secondary">{r['n_casos']}</span></td>
        </tr>"""
        for r in rows
    )
    body = f"""
    <div class="card">
      <table class="table table-hover mb-0">
        <thead class="table-light">
          <tr><th>Nombre</th><th>CUIT</th><th>Email</th><th>Teléfono</th><th>Causas</th></tr>
        </thead>
        <tbody>
          {rows_html or '<tr><td colspan="5" class="text-center text-muted py-3">Sin clientes</td></tr>'}
        </tbody>
      </table>
    </div>"""
    return _page("Clientes", body)


@router.get("/clientes/{cid}", response_class=HTMLResponse)
def clientes_ver(cid: int, user=Depends(require_lawyer)):
    with get_conn() as conn:
        c = row_to_dict(conn.execute("SELECT * FROM clientes WHERE id=?", (cid,)).fetchone())
        casos = rows_to_list(conn.execute(
            "SELECT id, caratula, estado FROM casos WHERE cliente_id=? ORDER BY caratula", (cid,)
        ).fetchall())
    if not c:
        raise HTTPException(404)

    casos_html = "".join(
        f"""<li class="list-group-item d-flex justify-content-between align-items-center">
          <a href="/portal/casos/{r['id']}">{r['caratula']}</a>
          {_badge_estado(r['estado'])}
        </li>"""
        for r in casos
    ) or '<li class="list-group-item text-muted">Sin causas asociadas</li>'

    fields = [
        ("CUIT", c.get("cuit") or "—"),
        ("Email", c.get("email") or "—"),
        ("Teléfono", c.get("telefono") or "—"),
        ("Domicilio", c.get("domicilio") or "—"),
        ("Notas", c.get("notas") or "—"),
    ]
    fields_html = "".join(
        f'<tr><th class="text-muted fw-normal" style="width:120px">{k}</th><td>{v}</td></tr>'
        for k, v in fields
    )
    safe_nombre = c["nombre"].replace("'", "")
    body = f"""
    <div class="d-flex justify-content-end mb-3">
      <button type="button" class="btn btn-outline-danger btn-sm"
              data-bs-toggle="modal" data-bs-target="#modalSolicitud">
        <i class="bi bi-trash me-1"></i>Solicitar eliminación
      </button>
    </div>

    <!-- Modal solicitud -->
    <div class="modal fade" id="modalSolicitud" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Solicitar eliminación de cliente</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <form method="post" action="/portal/solicitudes/nueva">
            <div class="modal-body">
              <input type="hidden" name="tipo" value="cliente">
              <input type="hidden" name="objeto_id" value="{cid}">
              <input type="hidden" name="objeto_descripcion" value="{safe_nombre}">
              <p class="text-muted small">La solicitud será enviada al administrador para su aprobación.</p>
              <label class="form-label">Motivo *</label>
              <textarea name="motivo" class="form-control" rows="3" required
                        placeholder="Ej: Cliente dado de baja, duplicado..."></textarea>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
              <button type="submit" class="btn btn-danger">Enviar solicitud</button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-header fw-semibold">{c['nombre']}</div>
      <div class="card-body p-0">
        <table class="table mb-0">{fields_html}</table>
      </div>
    </div>
    <div class="card">
      <div class="card-header fw-semibold">Causas asociadas</div>
      <ul class="list-group list-group-flush">{casos_html}</ul>
    </div>"""
    return _page(c["nombre"], body, "Detalle")


# ──────────────────────────────────────────────
# SOLICITUDES DE BAJA
# ──────────────────────────────────────────────

@router.post("/solicitudes/nueva")
def solicitud_crear(
    tipo: str = Form(...),
    objeto_id: int = Form(...),
    objeto_descripcion: str = Form(""),
    motivo: str = Form(""),
    user=Depends(require_lawyer),
):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO solicitudes_baja
               (tipo, objeto_id, objeto_descripcion, solicitante, motivo)
               VALUES (?,?,?,?,?)""",
            (tipo, objeto_id, objeto_descripcion, user, motivo),
        )
    redirect = "/portal/casos" if tipo == "caso" else "/portal/clientes"
    return RedirectResponse(f"{redirect}?solicitud=ok", status_code=303)


@router.get("/solicitudes", response_class=HTMLResponse)
def solicitudes_list(user=Depends(require_lawyer)):
    with get_conn() as conn:
        rows = rows_to_list(conn.execute(
            "SELECT * FROM solicitudes_baja WHERE solicitante=? ORDER BY creado_en DESC",
            (user,)
        ).fetchall())

    estado_badge = {
        "pendiente": '<span class="badge bg-warning text-dark">pendiente</span>',
        "aprobado": '<span class="badge bg-success">aprobado</span>',
        "rechazado": '<span class="badge bg-danger">rechazado</span>',
    }
    rows_html = "".join(
        f"""<tr>
          <td>{r['creado_en'][:10]}</td>
          <td><span class="badge bg-secondary">{r['tipo']}</span></td>
          <td>{r['objeto_descripcion'] or r['objeto_id']}</td>
          <td class="text-muted small">{r.get('motivo') or '—'}</td>
          <td>{estado_badge.get(r['estado'], r['estado'])}</td>
        </tr>"""
        for r in rows
    )
    body = f"""
    <div class="card">
      <table class="table table-hover mb-0">
        <thead class="table-light">
          <tr><th>Fecha</th><th>Tipo</th><th>Objeto</th><th>Motivo</th><th>Estado</th></tr>
        </thead>
        <tbody>
          {rows_html or '<tr><td colspan="5" class="text-center text-muted py-3">Sin solicitudes</td></tr>'}
        </tbody>
      </table>
    </div>"""
    return _page("Mis solicitudes", body)
