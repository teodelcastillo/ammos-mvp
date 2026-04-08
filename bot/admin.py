"""
Panel de administración web para Estudio Del Castillo.
Rutas bajo /admin — protegidas con HTTP Basic Auth.
"""

import os
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from db import get_conn, rows_to_list, row_to_dict
from import_causas import run_import

router = APIRouter(prefix="/admin")
security = HTTPBasic()

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "delcastillo")


# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────

def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username.encode(), ADMIN_USER.encode())
    ok_pass = secrets.compare_digest(credentials.password.encode(), ADMIN_PASSWORD.encode())
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
    .sidebar {{ min-height: 100vh; background: #1a2744; }}
    .sidebar .nav-link {{ color: #adb5bd; border-radius: 6px; margin: 2px 8px; }}
    .sidebar .nav-link:hover, .sidebar .nav-link.active {{ background: #2d4a8a; color: #fff; }}
    .sidebar .brand {{ color: #fff; font-weight: 700; font-size: 1.1rem; }}
    .card {{ border: none; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    .badge-activo {{ background:#198754; }} .badge-cerrado {{ background:#6c757d; }}
    .badge-archivado {{ background:#ffc107; color:#000; }}
    table {{ font-size:.9rem; }}
  </style>
</head>
<body>
<div class="d-flex">
  <!-- Sidebar -->
  <div class="sidebar d-flex flex-column p-3" style="width:220px;min-width:220px">
    <div class="brand mb-4 px-2 pt-2">
      <i class="bi bi-briefcase-fill me-2"></i>Del Castillo
    </div>
    <nav class="nav flex-column gap-1">
      <a href="/admin" class="nav-link"><i class="bi bi-speedometer2 me-2"></i>Dashboard</a>
      <a href="/admin/clientes" class="nav-link"><i class="bi bi-people-fill me-2"></i>Clientes</a>
      <a href="/admin/casos" class="nav-link"><i class="bi bi-folder2-open me-2"></i>Casos</a>
      <a href="/admin/tiempo" class="nav-link"><i class="bi bi-clock-history me-2"></i>Tiempo</a>
      <a href="/admin/notas" class="nav-link"><i class="bi bi-journal-text me-2"></i>Notas</a>
      <hr style="border-color:#2d4a8a;margin:8px">
      <a href="/admin/import" class="nav-link"><i class="bi bi-cloud-download me-2"></i>Importar</a>
    </nav>
  </div>

  <!-- Main -->
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


def _select_clientes(selected_id=None) -> str:
    with get_conn() as conn:
        rows = rows_to_list(conn.execute("SELECT id, nombre FROM clientes ORDER BY nombre").fetchall())
    opts = '<option value="">— Sin cliente —</option>'
    for r in rows:
        sel = "selected" if str(r["id"]) == str(selected_id) else ""
        opts += f'<option value="{r["id"]}" {sel}>{r["nombre"]}</option>'
    return opts


# ──────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
def dashboard(user=Depends(require_auth)):
    with get_conn() as conn:
        n_clientes = conn.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
        n_casos = conn.execute("SELECT COUNT(*) FROM casos WHERE estado='activo'").fetchone()[0]
        n_horas = conn.execute("SELECT COALESCE(SUM(horas),0) FROM registros_tiempo").fetchone()[0]
        n_notas = conn.execute("SELECT COUNT(*) FROM notas_reunion").fetchone()[0]
        casos_recientes = rows_to_list(
            conn.execute("""
                SELECT c.id, c.caratula, c.estado, c.materia, cl.nombre AS cliente
                FROM casos c LEFT JOIN clientes cl ON cl.id=c.cliente_id
                ORDER BY c.creado_en DESC LIMIT 5
            """).fetchall()
        )

    cards = f"""
    <div class="row g-3 mb-4">
      <div class="col-md-3">
        <div class="card p-3 text-center">
          <div class="fs-1 text-primary"><i class="bi bi-people-fill"></i></div>
          <div class="fs-3 fw-bold">{n_clientes}</div>
          <div class="text-muted">Clientes</div>
        </div>
      </div>
      <div class="col-md-3">
        <div class="card p-3 text-center">
          <div class="fs-1 text-success"><i class="bi bi-folder2-open"></i></div>
          <div class="fs-3 fw-bold">{n_casos}</div>
          <div class="text-muted">Casos activos</div>
        </div>
      </div>
      <div class="col-md-3">
        <div class="card p-3 text-center">
          <div class="fs-1 text-warning"><i class="bi bi-clock-history"></i></div>
          <div class="fs-3 fw-bold">{n_horas:.1f}h</div>
          <div class="text-muted">Horas registradas</div>
        </div>
      </div>
      <div class="col-md-3">
        <div class="card p-3 text-center">
          <div class="fs-1 text-info"><i class="bi bi-journal-text"></i></div>
          <div class="fs-3 fw-bold">{n_notas}</div>
          <div class="text-muted">Notas de reunión</div>
        </div>
      </div>
    </div>"""

    rows_html = "".join(
        f"""<tr>
          <td><a href="/admin/casos/{r['id']}">{r['caratula']}</a></td>
          <td>{r.get('cliente') or '—'}</td>
          <td>{r.get('materia') or '—'}</td>
          <td>{_badge_estado(r['estado'])}</td>
        </tr>"""
        for r in casos_recientes
    )
    table = f"""
    <div class="card">
      <div class="card-header fw-semibold">Casos recientes</div>
      <table class="table table-hover mb-0">
        <thead class="table-light"><tr><th>Carátula</th><th>Cliente</th><th>Materia</th><th>Estado</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>"""

    return _page("Dashboard", cards + table)


# ──────────────────────────────────────────────
# CLIENTES
# ──────────────────────────────────────────────

@router.get("/clientes", response_class=HTMLResponse)
def clientes_list(user=Depends(require_auth)):
    with get_conn() as conn:
        rows = rows_to_list(conn.execute("SELECT * FROM clientes ORDER BY nombre").fetchall())

    rows_html = "".join(
        f"""<tr>
          <td><a href="/admin/clientes/{r['id']}">{r['nombre']}</a></td>
          <td>{r.get('cuit') or '—'}</td>
          <td>{r.get('email') or '—'}</td>
          <td>{r.get('telefono') or '—'}</td>
        </tr>"""
        for r in rows
    )
    body = f"""
    <div class="mb-3 text-end">
      <a href="/admin/clientes/nuevo" class="btn btn-primary">
        <i class="bi bi-plus-lg me-1"></i>Nuevo cliente
      </a>
    </div>
    <div class="card">
      <table class="table table-hover mb-0">
        <thead class="table-light"><tr><th>Nombre</th><th>CUIT</th><th>Email</th><th>Teléfono</th></tr></thead>
        <tbody>{rows_html or '<tr><td colspan="4" class="text-center text-muted py-3">Sin clientes</td></tr>'}</tbody>
      </table>
    </div>"""
    return _page("Clientes", body)


@router.get("/clientes/nuevo", response_class=HTMLResponse)
def clientes_nuevo(user=Depends(require_auth)):
    return _page("Nuevo cliente", _form_cliente(), "Nuevo")


@router.get("/clientes/{cid}", response_class=HTMLResponse)
def clientes_ver(cid: int, user=Depends(require_auth)):
    with get_conn() as conn:
        c = row_to_dict(conn.execute("SELECT * FROM clientes WHERE id=?", (cid,)).fetchone())
        casos = rows_to_list(conn.execute("SELECT id, caratula, estado FROM casos WHERE cliente_id=?", (cid,)).fetchall())
    if not c:
        raise HTTPException(404)
    casos_html = "".join(
        f'<li class="list-group-item d-flex justify-content-between align-items-center">'
        f'<a href="/admin/casos/{r["id"]}">{r["caratula"]}</a>'
        f'{_badge_estado(r["estado"])}</li>'
        for r in casos
    ) or '<li class="list-group-item text-muted">Sin casos asociados</li>'
    body = f"""
    {_form_cliente(c)}
    <div class="card mt-4">
      <div class="card-header fw-semibold">Casos asociados</div>
      <ul class="list-group list-group-flush">{casos_html}</ul>
    </div>"""
    return _page(c["nombre"], body, "Editar")


@router.post("/clientes/nuevo")
def clientes_crear(
    nombre: str = Form(...), cuit: str = Form(""), email: str = Form(""),
    telefono: str = Form(""), domicilio: str = Form(""), notas: str = Form(""),
    user=Depends(require_auth)
):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO clientes (nombre,cuit,email,telefono,domicilio,notas) VALUES (?,?,?,?,?,?)",
            (nombre, cuit, email, telefono, domicilio, notas)
        )
    return RedirectResponse("/admin/clientes", status_code=303)


@router.post("/clientes/{cid}")
def clientes_actualizar(
    cid: int,
    nombre: str = Form(...), cuit: str = Form(""), email: str = Form(""),
    telefono: str = Form(""), domicilio: str = Form(""), notas: str = Form(""),
    user=Depends(require_auth)
):
    with get_conn() as conn:
        conn.execute(
            "UPDATE clientes SET nombre=?,cuit=?,email=?,telefono=?,domicilio=?,notas=? WHERE id=?",
            (nombre, cuit, email, telefono, domicilio, notas, cid)
        )
    return RedirectResponse(f"/admin/clientes/{cid}", status_code=303)


def _form_cliente(c: dict = None) -> str:
    v = c or {}
    action = f"/admin/clientes/{v['id']}" if v.get("id") else "/admin/clientes/nuevo"
    return f"""
    <div class="card">
      <div class="card-body">
        <form method="post" action="{action}">
          <div class="row g-3">
            <div class="col-md-6">
              <label class="form-label">Nombre *</label>
              <input name="nombre" class="form-control" required value="{v.get('nombre','') or ''}">
            </div>
            <div class="col-md-6">
              <label class="form-label">CUIT</label>
              <input name="cuit" class="form-control" value="{v.get('cuit','') or ''}">
            </div>
            <div class="col-md-6">
              <label class="form-label">Email</label>
              <input name="email" type="email" class="form-control" value="{v.get('email','') or ''}">
            </div>
            <div class="col-md-6">
              <label class="form-label">Teléfono</label>
              <input name="telefono" class="form-control" value="{v.get('telefono','') or ''}">
            </div>
            <div class="col-12">
              <label class="form-label">Domicilio</label>
              <input name="domicilio" class="form-control" value="{v.get('domicilio','') or ''}">
            </div>
            <div class="col-12">
              <label class="form-label">Notas</label>
              <textarea name="notas" class="form-control" rows="3">{v.get('notas','') or ''}</textarea>
            </div>
            <div class="col-12">
              <button class="btn btn-primary" type="submit">
                <i class="bi bi-floppy-fill me-1"></i>Guardar
              </button>
              <a href="/admin/clientes" class="btn btn-outline-secondary ms-2">Cancelar</a>
            </div>
          </div>
        </form>
      </div>
    </div>"""


# ──────────────────────────────────────────────
# CASOS
# ──────────────────────────────────────────────

@router.get("/casos", response_class=HTMLResponse)
def casos_list(user=Depends(require_auth)):
    with get_conn() as conn:
        rows = rows_to_list(conn.execute("""
            SELECT c.id, c.numero, c.caratula, c.estado, c.materia, c.fuero,
                   cl.nombre AS cliente
            FROM casos c LEFT JOIN clientes cl ON cl.id=c.cliente_id
            ORDER BY c.creado_en DESC
        """).fetchall())

    rows_html = "".join(
        f"""<tr>
          <td>{r.get('numero') or '—'}</td>
          <td><a href="/admin/casos/{r['id']}">{r['caratula']}</a></td>
          <td>{r.get('cliente') or '—'}</td>
          <td>{r.get('materia') or '—'}</td>
          <td>{r.get('fuero') or '—'}</td>
          <td>{_badge_estado(r['estado'])}</td>
        </tr>"""
        for r in rows
    )
    body = f"""
    <div class="mb-3 text-end">
      <a href="/admin/casos/nuevo" class="btn btn-primary">
        <i class="bi bi-plus-lg me-1"></i>Nuevo caso
      </a>
    </div>
    <div class="card">
      <table class="table table-hover mb-0">
        <thead class="table-light">
          <tr><th>Nro</th><th>Carátula</th><th>Cliente</th><th>Materia</th><th>Fuero</th><th>Estado</th></tr>
        </thead>
        <tbody>{rows_html or '<tr><td colspan="6" class="text-center text-muted py-3">Sin casos</td></tr>'}</tbody>
      </table>
    </div>"""
    return _page("Casos", body)


@router.get("/casos/nuevo", response_class=HTMLResponse)
def casos_nuevo(user=Depends(require_auth)):
    return _page("Nuevo caso", _form_caso(), "Nuevo")


@router.get("/casos/{cid}", response_class=HTMLResponse)
def casos_ver(cid: int, user=Depends(require_auth)):
    with get_conn() as conn:
        c = row_to_dict(conn.execute("SELECT * FROM casos WHERE id=?", (cid,)).fetchone())
        tiempos = rows_to_list(conn.execute(
            "SELECT * FROM registros_tiempo WHERE caso_id=? ORDER BY fecha DESC", (cid,)
        ).fetchall())
        notas = rows_to_list(conn.execute(
            "SELECT * FROM notas_reunion WHERE caso_id=? ORDER BY fecha DESC", (cid,)
        ).fetchall())
    if not c:
        raise HTTPException(404)

    t_html = "".join(
        f"<tr><td>{t['fecha']}</td><td>{t['abogado']}</td><td>{t['horas']}h</td><td>{t.get('descripcion') or '—'}</td></tr>"
        for t in tiempos
    ) or '<tr><td colspan="4" class="text-muted text-center">Sin registros</td></tr>'

    n_html = "".join(
        f"<tr><td>{n['fecha'][:10]}</td><td>{n.get('participantes') or '—'}</td>"
        f"<td>{(n.get('contenido') or '')[:80]}…</td></tr>"
        for n in notas
    ) or '<tr><td colspan="3" class="text-muted text-center">Sin notas</td></tr>'

    horas_total = sum(t["horas"] for t in tiempos)
    extra = f"""
    <div class="row g-3 mt-1">
      <div class="col-md-6">
        <div class="card">
          <div class="card-header fw-semibold d-flex justify-content-between">
            Tiempo registrado <span class="badge bg-secondary">{horas_total:.1f}h</span>
          </div>
          <table class="table table-sm mb-0">
            <thead class="table-light"><tr><th>Fecha</th><th>Abogado</th><th>Horas</th><th>Descripción</th></tr></thead>
            <tbody>{t_html}</tbody>
          </table>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header fw-semibold">Notas de reunión</div>
          <table class="table table-sm mb-0">
            <thead class="table-light"><tr><th>Fecha</th><th>Participantes</th><th>Contenido</th></tr></thead>
            <tbody>{n_html}</tbody>
          </table>
        </div>
      </div>
    </div>"""
    return _page(c["caratula"], _form_caso(c) + extra, "Editar")


@router.post("/casos/nuevo")
def casos_crear(
    numero: str = Form(""), caratula: str = Form(...), cliente_id: str = Form(""),
    materia: str = Form(""), fuero: str = Form(""), juzgado: str = Form(""),
    estado: str = Form("activo"), fecha_inicio: str = Form(""),
    abogado: str = Form(""), notas: str = Form(""),
    user=Depends(require_auth)
):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO casos (numero,caratula,cliente_id,materia,fuero,juzgado,
               estado,fecha_inicio,abogado,notas) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (numero, caratula, cliente_id or None, materia, fuero, juzgado,
             estado, fecha_inicio or None, abogado, notas)
        )
    return RedirectResponse("/admin/casos", status_code=303)


@router.post("/casos/{cid}")
def casos_actualizar(
    cid: int,
    numero: str = Form(""), caratula: str = Form(...), cliente_id: str = Form(""),
    materia: str = Form(""), fuero: str = Form(""), juzgado: str = Form(""),
    estado: str = Form("activo"), fecha_inicio: str = Form(""),
    abogado: str = Form(""), notas: str = Form(""),
    user=Depends(require_auth)
):
    with get_conn() as conn:
        conn.execute(
            """UPDATE casos SET numero=?,caratula=?,cliente_id=?,materia=?,fuero=?,juzgado=?,
               estado=?,fecha_inicio=?,abogado=?,notas=? WHERE id=?""",
            (numero, caratula, cliente_id or None, materia, fuero, juzgado,
             estado, fecha_inicio or None, abogado, notas, cid)
        )
    return RedirectResponse(f"/admin/casos/{cid}", status_code=303)


def _form_caso(c: dict = None) -> str:
    v = c or {}
    action = f"/admin/casos/{v['id']}" if v.get("id") else "/admin/casos/nuevo"
    estados = ["activo", "cerrado", "archivado"]
    opts_estado = "".join(
        f'<option {"selected" if v.get("estado")==e else ""}>{e}</option>' for e in estados
    )
    opts_cliente = _select_clientes(v.get("cliente_id"))
    return f"""
    <div class="card">
      <div class="card-body">
        <form method="post" action="{action}">
          <div class="row g-3">
            <div class="col-md-4">
              <label class="form-label">Número de expediente</label>
              <input name="numero" class="form-control" value="{v.get('numero','') or ''}">
            </div>
            <div class="col-md-8">
              <label class="form-label">Carátula *</label>
              <input name="caratula" class="form-control" required value="{v.get('caratula','') or ''}">
            </div>
            <div class="col-md-6">
              <label class="form-label">Cliente</label>
              <select name="cliente_id" class="form-select">{opts_cliente}</select>
            </div>
            <div class="col-md-6">
              <label class="form-label">Abogado responsable</label>
              <input name="abogado" class="form-control" value="{v.get('abogado','') or ''}">
            </div>
            <div class="col-md-4">
              <label class="form-label">Materia</label>
              <input name="materia" class="form-control" value="{v.get('materia','') or ''}">
            </div>
            <div class="col-md-4">
              <label class="form-label">Fuero</label>
              <input name="fuero" class="form-control" value="{v.get('fuero','') or ''}">
            </div>
            <div class="col-md-4">
              <label class="form-label">Juzgado</label>
              <input name="juzgado" class="form-control" value="{v.get('juzgado','') or ''}">
            </div>
            <div class="col-md-4">
              <label class="form-label">Fecha inicio</label>
              <input name="fecha_inicio" type="date" class="form-control" value="{v.get('fecha_inicio','') or ''}">
            </div>
            <div class="col-md-4">
              <label class="form-label">Estado</label>
              <select name="estado" class="form-select">{opts_estado}</select>
            </div>
            <div class="col-12">
              <label class="form-label">Notas</label>
              <textarea name="notas" class="form-control" rows="3">{v.get('notas','') or ''}</textarea>
            </div>
            <div class="col-12">
              <button class="btn btn-primary" type="submit">
                <i class="bi bi-floppy-fill me-1"></i>Guardar
              </button>
              <a href="/admin/casos" class="btn btn-outline-secondary ms-2">Cancelar</a>
            </div>
          </div>
        </form>
      </div>
    </div>"""


# ──────────────────────────────────────────────
# TIEMPO
# ──────────────────────────────────────────────

@router.get("/tiempo", response_class=HTMLResponse)
def tiempo_list(user=Depends(require_auth)):
    with get_conn() as conn:
        rows = rows_to_list(conn.execute("""
            SELECT rt.*, c.caratula
            FROM registros_tiempo rt
            LEFT JOIN casos c ON c.id=rt.caso_id
            ORDER BY rt.fecha DESC
        """).fetchall())
        total = sum(r["horas"] for r in rows)

    rows_html = "".join(
        f"""<tr>
          <td>{r['fecha']}</td>
          <td>{r.get('caratula') or '—'}</td>
          <td>{r['abogado']}</td>
          <td>{r['horas']}h</td>
          <td>{r.get('descripcion') or '—'}</td>
        </tr>"""
        for r in rows
    )
    body = f"""
    <div class="mb-3 d-flex justify-content-between align-items-center">
      <span class="badge bg-secondary fs-6">{total:.1f}h totales</span>
      <a href="/admin/tiempo/nuevo" class="btn btn-primary">
        <i class="bi bi-plus-lg me-1"></i>Registrar tiempo
      </a>
    </div>
    <div class="card">
      <table class="table table-hover mb-0">
        <thead class="table-light">
          <tr><th>Fecha</th><th>Caso</th><th>Abogado</th><th>Horas</th><th>Descripción</th></tr>
        </thead>
        <tbody>{rows_html or '<tr><td colspan="5" class="text-center text-muted py-3">Sin registros</td></tr>'}</tbody>
      </table>
    </div>"""
    return _page("Tiempo", body)


@router.get("/tiempo/nuevo", response_class=HTMLResponse)
def tiempo_nuevo(user=Depends(require_auth)):
    with get_conn() as conn:
        casos = rows_to_list(conn.execute("SELECT id, caratula FROM casos ORDER BY caratula").fetchall())
    opts = "".join(f'<option value="{c["id"]}">{c["caratula"]}</option>' for c in casos)
    form = f"""
    <div class="card"><div class="card-body">
      <form method="post" action="/admin/tiempo/nuevo">
        <div class="row g-3">
          <div class="col-md-6">
            <label class="form-label">Caso *</label>
            <select name="caso_id" class="form-select" required>{opts}</select>
          </div>
          <div class="col-md-6">
            <label class="form-label">Abogado *</label>
            <input name="abogado" class="form-control" required>
          </div>
          <div class="col-md-4">
            <label class="form-label">Fecha *</label>
            <input name="fecha" type="date" class="form-control" required>
          </div>
          <div class="col-md-4">
            <label class="form-label">Horas *</label>
            <input name="horas" type="number" step="0.25" min="0.25" class="form-control" required>
          </div>
          <div class="col-12">
            <label class="form-label">Descripción</label>
            <textarea name="descripcion" class="form-control" rows="2"></textarea>
          </div>
          <div class="col-12">
            <button class="btn btn-primary" type="submit"><i class="bi bi-floppy-fill me-1"></i>Guardar</button>
            <a href="/admin/tiempo" class="btn btn-outline-secondary ms-2">Cancelar</a>
          </div>
        </div>
      </form>
    </div></div>"""
    return _page("Registrar tiempo", form, "Nuevo")


@router.post("/tiempo/nuevo")
def tiempo_crear(
    caso_id: int = Form(...), abogado: str = Form(...),
    fecha: str = Form(...), horas: float = Form(...),
    descripcion: str = Form(""), user=Depends(require_auth)
):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO registros_tiempo (caso_id,abogado,fecha,horas,descripcion) VALUES (?,?,?,?,?)",
            (caso_id, abogado, fecha, horas, descripcion)
        )
    return RedirectResponse("/admin/tiempo", status_code=303)


# ──────────────────────────────────────────────
# NOTAS
# ──────────────────────────────────────────────

@router.get("/notas", response_class=HTMLResponse)
def notas_list(user=Depends(require_auth)):
    with get_conn() as conn:
        rows = rows_to_list(conn.execute("""
            SELECT nr.id, nr.fecha, nr.participantes, nr.contenido, nr.creado_por,
                   c.caratula, cl.nombre AS cliente
            FROM notas_reunion nr
            LEFT JOIN casos c ON c.id=nr.caso_id
            LEFT JOIN clientes cl ON cl.id=nr.cliente_id
            ORDER BY nr.fecha DESC
        """).fetchall())

    rows_html = "".join(
        f"""<tr>
          <td>{r['fecha'][:10]}</td>
          <td>{r.get('caratula') or '—'}</td>
          <td>{r.get('cliente') or '—'}</td>
          <td>{r.get('participantes') or '—'}</td>
          <td><a href="/admin/notas/{r['id']}">{(r.get('contenido') or '')[:60]}…</a></td>
        </tr>"""
        for r in rows
    )
    body = f"""
    <div class="mb-3 text-end">
      <a href="/admin/notas/nuevo" class="btn btn-primary">
        <i class="bi bi-plus-lg me-1"></i>Nueva nota
      </a>
    </div>
    <div class="card">
      <table class="table table-hover mb-0">
        <thead class="table-light">
          <tr><th>Fecha</th><th>Caso</th><th>Cliente</th><th>Participantes</th><th>Contenido</th></tr>
        </thead>
        <tbody>{rows_html or '<tr><td colspan="5" class="text-center text-muted py-3">Sin notas</td></tr>'}</tbody>
      </table>
    </div>"""
    return _page("Notas de reunión", body)


@router.get("/notas/nuevo", response_class=HTMLResponse)
def notas_nuevo(user=Depends(require_auth)):
    with get_conn() as conn:
        casos = rows_to_list(conn.execute("SELECT id, caratula FROM casos ORDER BY caratula").fetchall())
        clientes = rows_to_list(conn.execute("SELECT id, nombre FROM clientes ORDER BY nombre").fetchall())
    return _page("Nueva nota", _form_nota(casos=casos, clientes=clientes), "Nueva")


@router.get("/notas/{nid}", response_class=HTMLResponse)
def notas_ver(nid: int, user=Depends(require_auth)):
    with get_conn() as conn:
        n = row_to_dict(conn.execute("SELECT * FROM notas_reunion WHERE id=?", (nid,)).fetchone())
        casos = rows_to_list(conn.execute("SELECT id, caratula FROM casos ORDER BY caratula").fetchall())
        clientes = rows_to_list(conn.execute("SELECT id, nombre FROM clientes ORDER BY nombre").fetchall())
    if not n:
        raise HTTPException(404)
    return _page("Editar nota", _form_nota(n, casos, clientes), "Editar")


@router.post("/notas/nuevo")
def notas_crear(
    caso_id: str = Form(""), cliente_id: str = Form(""),
    fecha: str = Form(...), participantes: str = Form(""),
    contenido: str = Form(...), creado_por: str = Form(""),
    user=Depends(require_auth)
):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO notas_reunion (caso_id,cliente_id,fecha,participantes,contenido,creado_por) VALUES (?,?,?,?,?,?)",
            (caso_id or None, cliente_id or None, fecha, participantes, contenido, creado_por)
        )
    return RedirectResponse("/admin/notas", status_code=303)


@router.post("/notas/{nid}")
def notas_actualizar(
    nid: int,
    caso_id: str = Form(""), cliente_id: str = Form(""),
    fecha: str = Form(...), participantes: str = Form(""),
    contenido: str = Form(...), creado_por: str = Form(""),
    user=Depends(require_auth)
):
    with get_conn() as conn:
        conn.execute(
            "UPDATE notas_reunion SET caso_id=?,cliente_id=?,fecha=?,participantes=?,contenido=?,creado_por=? WHERE id=?",
            (caso_id or None, cliente_id or None, fecha, participantes, contenido, creado_por, nid)
        )
    return RedirectResponse(f"/admin/notas/{nid}", status_code=303)


def _form_nota(n: dict = None, casos: list = None, clientes: list = None) -> str:
    v = n or {}
    action = f"/admin/notas/{v['id']}" if v.get("id") else "/admin/notas/nuevo"
    opts_casos = '<option value="">— Sin caso —</option>' + "".join(
        f'<option value="{c["id"]}" {"selected" if str(v.get("caso_id",""))==str(c["id"]) else ""}>{c["caratula"]}</option>'
        for c in (casos or [])
    )
    opts_clientes = '<option value="">— Sin cliente —</option>' + "".join(
        f'<option value="{c["id"]}" {"selected" if str(v.get("cliente_id",""))==str(c["id"]) else ""}>{c["nombre"]}</option>'
        for c in (clientes or [])
    )
    fecha_val = (v.get("fecha") or "")[:16].replace(" ", "T")
    return f"""
    <div class="card"><div class="card-body">
      <form method="post" action="{action}">
        <div class="row g-3">
          <div class="col-md-6">
            <label class="form-label">Caso</label>
            <select name="caso_id" class="form-select">{opts_casos}</select>
          </div>
          <div class="col-md-6">
            <label class="form-label">Cliente</label>
            <select name="cliente_id" class="form-select">{opts_clientes}</select>
          </div>
          <div class="col-md-6">
            <label class="form-label">Fecha y hora *</label>
            <input name="fecha" type="datetime-local" class="form-control" required value="{fecha_val}">
          </div>
          <div class="col-md-6">
            <label class="form-label">Participantes</label>
            <input name="participantes" class="form-control" value="{v.get('participantes','') or ''}">
          </div>
          <div class="col-md-6">
            <label class="form-label">Creado por</label>
            <input name="creado_por" class="form-control" value="{v.get('creado_por','') or ''}">
          </div>
          <div class="col-12">
            <label class="form-label">Contenido *</label>
            <textarea name="contenido" class="form-control" rows="6" required>{v.get('contenido','') or ''}</textarea>
          </div>
          <div class="col-12">
            <button class="btn btn-primary" type="submit"><i class="bi bi-floppy-fill me-1"></i>Guardar</button>
            <a href="/admin/notas" class="btn btn-outline-secondary ms-2">Cancelar</a>
          </div>
        </div>
      </form>
    </div></div>"""


# ──────────────────────────────────────────────
# IMPORTAR CAUSAS
# ──────────────────────────────────────────────

@router.get("/import", response_class=HTMLResponse)
def import_page(user=Depends(require_auth)):
    body = """
    <div class="card mb-4">
      <div class="card-body">
        <p class="mb-1">Lee el sheet <strong>GENERAL DE CAUSAS</strong> y muestra una previsualización antes de importar.</p>
        <p class="text-muted small mb-3">Los casos que ya existen en la DB (por carátula) serán omitidos. Los clientes se crean si no existen.</p>
        <form method="post" action="/admin/import/preview">
          <button class="btn btn-outline-primary" type="submit">
            <i class="bi bi-eye me-1"></i>Previsualizar importación
          </button>
        </form>
      </div>
    </div>"""
    return _page("Importar causas", body)


@router.post("/import/preview", response_class=HTMLResponse)
def import_preview(user=Depends(require_auth)):
    try:
        stats = run_import(dry_run=True)
    except Exception as e:
        return _page("Error", f'<div class="alert alert-danger">{e}</div>')

    if "error" in stats:
        return _page("Error", f'<div class="alert alert-danger">{stats["error"]}</div>')

    to_import = [d for d in stats["detalles"] if d["accion"] == "importar"]
    to_skip   = [d for d in stats["detalles"] if d["accion"] == "omitido"]

    rows_new = "".join(
        f"<tr><td>{r['caratula']}</td><td>{r.get('cliente','—')}</td><td>{r.get('juzgado','—')}</td></tr>"
        for r in to_import
    ) or '<tr><td colspan="3" class="text-muted text-center">Sin casos nuevos</td></tr>'

    rows_skip = "".join(
        f"<tr><td>{r['caratula']}</td><td class='text-muted'>{r.get('razon','')}</td></tr>"
        for r in to_skip
    ) or '<tr><td colspan="2" class="text-muted text-center">Ninguno</td></tr>'

    body = f"""
    <div class="row g-3 mb-3">
      <div class="col-md-3"><div class="card p-3 text-center">
        <div class="fs-3 fw-bold text-primary">{stats['total_filas']}</div>
        <div class="text-muted">Filas en sheet</div>
      </div></div>
      <div class="col-md-3"><div class="card p-3 text-center">
        <div class="fs-3 fw-bold text-success">{stats['casos_nuevos']}</div>
        <div class="text-muted">Casos a importar</div>
      </div></div>
      <div class="col-md-3"><div class="card p-3 text-center">
        <div class="fs-3 fw-bold text-info">{stats['clientes_nuevos']}</div>
        <div class="text-muted">Clientes nuevos</div>
      </div></div>
      <div class="col-md-3"><div class="card p-3 text-center">
        <div class="fs-3 fw-bold text-secondary">{stats['casos_existentes'] + stats['omitidos']}</div>
        <div class="text-muted">Omitidos</div>
      </div></div>
    </div>

    <div class="card mb-3">
      <div class="card-header fw-semibold text-success">
        <i class="bi bi-check-circle me-1"></i>Se van a importar ({stats['casos_nuevos']})
      </div>
      <table class="table table-sm mb-0">
        <thead class="table-light"><tr><th>Carátula</th><th>Cliente</th><th>Juzgado</th></tr></thead>
        <tbody>{rows_new}</tbody>
      </table>
    </div>

    <div class="card mb-4">
      <div class="card-header fw-semibold text-secondary">
        <i class="bi bi-skip-forward me-1"></i>Se van a omitir ({stats['casos_existentes'] + stats['omitidos']})
      </div>
      <table class="table table-sm mb-0">
        <thead class="table-light"><tr><th>Carátula</th><th>Razón</th></tr></thead>
        <tbody>{rows_skip}</tbody>
      </table>
    </div>

    <form method="post" action="/admin/import/run">
      <button class="btn btn-success btn-lg" type="submit"
              onclick="return confirm('¿Confirmar importación de {stats[&quot;casos_nuevos&quot;]} casos?')">
        <i class="bi bi-cloud-download me-2"></i>Importar {stats['casos_nuevos']} casos
      </button>
      <a href="/admin/import" class="btn btn-outline-secondary ms-2">Cancelar</a>
    </form>"""

    return _page("Previsualización", body, "Importar")


@router.post("/import/run", response_class=HTMLResponse)
def import_run(user=Depends(require_auth)):
    try:
        stats = run_import(dry_run=False)
    except Exception as e:
        return _page("Error", f'<div class="alert alert-danger">{e}</div>')

    if "error" in stats:
        return _page("Error", f'<div class="alert alert-danger">{stats["error"]}</div>')

    body = f"""
    <div class="alert alert-success fs-5">
      <i class="bi bi-check-circle-fill me-2"></i>
      Importación completada: <strong>{stats['casos_nuevos']} casos</strong>
      y <strong>{stats['clientes_nuevos']} clientes</strong> nuevos.
    </div>
    <a href="/admin/casos" class="btn btn-primary">Ver casos</a>
    <a href="/admin/clientes" class="btn btn-outline-secondary ms-2">Ver clientes</a>"""

    return _page("Importación completada", body)
