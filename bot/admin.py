"""
Panel de administración web para Estudio Del Castillo.
Rutas bajo /admin — protegidas con HTTP Basic Auth.
"""

import os
import re
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from db import get_conn, rows_to_list, row_to_dict
import json as _json
from import_causas import run_import, build_client_map, _load_aliases, _read_sheet

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
      <a href="/admin/solicitudes" class="nav-link"><i class="bi bi-inbox me-2"></i>Solicitudes</a>
      <a href="/admin/import" class="nav-link"><i class="bi bi-cloud-download me-2"></i>Importar causas</a>
      <a href="/admin/import-calendar" class="nav-link"><i class="bi bi-calendar2-plus me-2"></i>Importar calendario</a>
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
        n_solicitudes = conn.execute(
            "SELECT COUNT(*) FROM solicitudes_baja WHERE estado='pendiente'"
        ).fetchone()[0]
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
    </div>
    { f'<div class="alert alert-warning d-flex align-items-center gap-2 mb-4"><i class="bi bi-inbox-fill fs-5"></i><div><strong>{n_solicitudes} solicitud(es) de baja pendiente(s)</strong> — <a href="/admin/solicitudes" class="alert-link">Revisar ahora</a></div></div>' if n_solicitudes else "" }"""

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
        rows = rows_to_list(conn.execute(
            "SELECT c.*, COUNT(ca.id) AS n_casos FROM clientes c "
            "LEFT JOIN casos ca ON ca.cliente_id=c.id GROUP BY c.id ORDER BY c.nombre"
        ).fetchall())

    rows_html = "".join(
        f"""<tr>
          <td><input type="checkbox" class="form-check-input client-cb" value="{r['id']}"></td>
          <td><a href="/admin/clientes/{r['id']}">{r['nombre']}</a></td>
          <td>{r.get('cuit') or '—'}</td>
          <td>{r.get('email') or '—'}</td>
          <td><span class="badge bg-secondary">{r['n_casos']}</span></td>
        </tr>"""
        for r in rows
    )
    rows_json = _json.dumps([{"id": r["id"], "nombre": r["nombre"]} for r in rows])
    body = f"""
    <!-- Modal fusionar -->
    <div class="modal fade" id="mergeModal" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header"><h5 class="modal-title">Fusionar clientes</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <form method="post" action="/admin/clientes/fusionar">
            <div class="modal-body">
              <p class="text-muted small">Se fusionarán los clientes seleccionados. Todos sus casos quedarán bajo el nombre canónico.</p>
              <div id="selectedNames" class="mb-3 text-muted small"></div>
              <label class="form-label fw-semibold">Nombre canónico del cliente fusionado *</label>
              <input name="nombre_canonico" id="nombreCanonico" class="form-control" required placeholder="Ej: Estudio O'Farrell - FORD">
              <input type="hidden" name="ids" id="mergeIds">
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
              <button type="submit" class="btn btn-warning">
                <i class="bi bi-people-fill me-1"></i>Fusionar
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <div class="mb-3 d-flex justify-content-between align-items-center">
      <button id="btnMerge" class="btn btn-warning d-none" onclick="openMerge()">
        <i class="bi bi-people-fill me-1"></i>Fusionar seleccionados
      </button>
      <a href="/admin/clientes/nuevo" class="btn btn-primary ms-auto">
        <i class="bi bi-plus-lg me-1"></i>Nuevo cliente
      </a>
    </div>
    <div class="card">
      <table class="table table-hover mb-0">
        <thead class="table-light">
          <tr><th style="width:36px"></th><th>Nombre</th><th>CUIT</th><th>Email</th><th>Causas</th></tr>
        </thead>
        <tbody>{rows_html or '<tr><td colspan="5" class="text-center text-muted py-3">Sin clientes</td></tr>'}</tbody>
      </table>
    </div>

    <script>
    const allRows = {rows_json};

    document.querySelectorAll('.client-cb').forEach(cb => {{
      cb.addEventListener('change', updateMergeBtn);
    }});

    function getSelected() {{
      return [...document.querySelectorAll('.client-cb:checked')].map(cb => parseInt(cb.value));
    }}

    function updateMergeBtn() {{
      const sel = getSelected();
      document.getElementById('btnMerge').classList.toggle('d-none', sel.length < 2);
    }}

    function openMerge() {{
      const ids = getSelected();
      const names = ids.map(id => allRows.find(r => r.id === id)?.nombre || id);
      document.getElementById('selectedNames').innerHTML = names.map(n => `<span class="badge bg-light text-dark border me-1">${{n}}</span>`).join('');
      document.getElementById('nombreCanonico').value = names[0];
      document.getElementById('mergeIds').value = ids.join(',');
      new bootstrap.Modal(document.getElementById('mergeModal')).show();
    }}
    </script>"""
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

    n_casos = len(casos)
    delete_warn = f"Este cliente tiene {n_casos} caso(s) asociado(s) que quedarán sin cliente asignado. " if n_casos else ""
    safe_nombre = c["nombre"].replace("'", "")
    body = f"""
    {_form_cliente(c)}
    <div class="card mt-4">
      <div class="card-header fw-semibold">Casos asociados</div>
      <ul class="list-group list-group-flush">{casos_html}</ul>
    </div>
    <div class="mt-4">
      <form method="post" action="/admin/clientes/{cid}/eliminar"
            onsubmit="return confirm('{delete_warn}¿Eliminar cliente {safe_nombre}?')">
        <button type="submit" class="btn btn-outline-danger btn-sm">
          <i class="bi bi-trash me-1"></i>Eliminar cliente
        </button>
      </form>
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


@router.post("/clientes/fusionar")
def clientes_fusionar(
    ids: str = Form(...),
    nombre_canonico: str = Form(...),
    user=Depends(require_auth)
):
    id_list = [int(i.strip()) for i in ids.split(",") if i.strip().isdigit()]
    if len(id_list) < 2:
        raise HTTPException(400, "Se necesitan al menos 2 clientes")
    with get_conn() as conn:
        # Crear o buscar el cliente canónico
        existing = conn.execute(
            "SELECT id FROM clientes WHERE LOWER(TRIM(nombre))=LOWER(TRIM(?))", (nombre_canonico,)
        ).fetchone()
        if existing:
            canonical_id = existing[0]
        else:
            cur = conn.execute("INSERT INTO clientes (nombre) VALUES (?)", (nombre_canonico,))
            canonical_id = cur.lastrowid
        # Reasignar todos los casos de los clientes a fusionar
        for old_id in id_list:
            if old_id == canonical_id:
                continue
            conn.execute("UPDATE casos SET cliente_id=? WHERE cliente_id=?", (canonical_id, old_id))
            conn.execute("DELETE FROM clientes WHERE id=?", (old_id,))
    return RedirectResponse(f"/admin/clientes/{canonical_id}", status_code=303)


@router.post("/clientes/{cid}/eliminar")
def clientes_eliminar(cid: int, user=Depends(require_auth)):
    with get_conn() as conn:
        conn.execute("UPDATE casos SET cliente_id=NULL WHERE cliente_id=?", (cid,))
        conn.execute("DELETE FROM clientes WHERE id=?", (cid,))
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


TIPO_ICONS = {
    "audiencia": "⚖️", "vencimiento": "⏰", "reunion": "🤝",
    "pericia": "🔬", "mediacion": "🕊️", "otro": "📌",
}

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
        eventos = rows_to_list(conn.execute(
            "SELECT * FROM eventos_caso WHERE caso_id=? ORDER BY fecha DESC", (cid,)
        ).fetchall())
    if not c:
        raise HTTPException(404)

    # Eventos / historial
    ev_html = ""
    for e in eventos:
        icon = TIPO_ICONS.get(e.get("tipo", "otro"), "📌")
        link = f'<a href="{e["calendar_link"]}" target="_blank" class="btn btn-sm btn-outline-primary py-0 ms-1"><i class="bi bi-calendar-check"></i></a>' if e.get("calendar_link") else ""
        nota = f'<div class="text-muted small">{e["notas"]}</div>' if e.get("notas") else ""
        ev_html += f"""
        <div class="d-flex gap-2 py-2 border-bottom">
          <div class="text-center" style="min-width:36px;font-size:1.2rem">{icon}</div>
          <div class="flex-grow-1">
            <div class="d-flex align-items-center">
              <span class="fw-semibold">{e['titulo']}</span>{link}
              <span class="badge bg-light text-dark border ms-2 small">{e.get('tipo','otro')}</span>
            </div>
            <div class="text-muted small">{e['fecha'][:16].replace('T',' ')}</div>
            {nota}
          </div>
        </div>"""
    ev_section = ev_html or '<div class="text-muted small p-3">Sin eventos registrados. Podés pedirle a Lexia que registre audiencias o vencimientos.</div>'

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
    <div class="card mt-4">
      <div class="card-header fw-semibold d-flex justify-content-between align-items-center">
        <span>📋 Historial de eventos <span class="badge bg-secondary ms-1">{len(eventos)}</span></span>
        <small class="text-muted">Registrá eventos con Lexia por WhatsApp</small>
      </div>
      <div class="card-body p-0 px-3">{ev_section}</div>
    </div>
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
    import traceback
    try:
        records   = _read_sheet()
        aliases   = _load_aliases()
        all_names = list(dict.fromkeys(
            r.get("cliente", "").strip() for r in records if r.get("cliente", "").strip()
        ))
        client_map = build_client_map(all_names, aliases)
        stats = run_import(dry_run=True, client_map_override=client_map)
    except Exception as e:
        detail = traceback.format_exc()
        return _page("Error", f'<div class="alert alert-danger"><strong>{type(e).__name__}: {e}</strong><pre class="mt-2 small">{detail}</pre></div>')

    if "error" in stats:
        return _page("Error", f'<div class="alert alert-danger"><pre class="mb-0" style="white-space:pre-wrap">{stats["error"]}</pre></div>')

    merged = stats.get("merged_groups", [])
    n_new  = stats["casos_nuevos"]

    # Construir cards editables para cada grupo
    group_cards = ""
    for g in merged:
        canonical = g["canonical"]
        variants  = g["variants"]
        safe_canonical = canonical.replace("'", "\\'")
        chips_parts = []
        for v in variants:
            safe_v = v.replace("'", "\\'")
            chips_parts.append(
                f'<span class="badge bg-secondary me-1 mb-1 variant-chip" style="font-size:.85rem">'
                f'{v}'
                f'<button type="button" class="btn-close btn-close-white ms-1" style="font-size:.6rem"'
                f" onclick=\"separateVariant(this, '{safe_canonical}', '{safe_v}')\">"
                f'</button></span>'
            )
        chips = "".join(chips_parts)
        group_cards += f"""
        <div class="card mb-2 group-card" data-canonical="{canonical}">
          <div class="card-body py-2">
            <div class="d-flex align-items-start gap-2">
              <div class="flex-grow-1">
                <strong class="text-warning">{canonical}</strong>
                <div class="mt-1">{chips}</div>
              </div>
            </div>
          </div>
        </div>"""

    merged_section = ""
    if merged:
        merged_section = f"""
        <div class="card mb-4">
          <div class="card-header fw-semibold">
            <i class="bi bi-people me-1 text-warning"></i>
            Clientes unificados — revisá y separé los que no corresponden
            <span class="badge bg-warning text-dark ms-2">{len(merged)} grupos</span>
          </div>
          <div class="card-body">
            <p class="text-muted small mb-3">
              Clickeá la ✕ de una variante para separarla como cliente independiente.
            </p>
            {group_cards}
          </div>
        </div>"""

    to_skip  = [d for d in stats["detalles"] if d["accion"] == "omitido"]
    rows_skip = "".join(
        f"<tr><td>{r['caratula']}</td><td class='text-muted'>{r.get('razon','')}</td></tr>"
        for r in to_skip
    ) or '<tr><td colspan="2" class="text-muted text-center">Ninguno</td></tr>'

    client_map_json = _json.dumps(client_map, ensure_ascii=False)

    body = f"""
    <div class="row g-3 mb-4">
      <div class="col-md-3"><div class="card p-3 text-center">
        <div class="fs-3 fw-bold text-primary">{stats['total_filas']}</div>
        <div class="text-muted">Filas en sheet</div>
      </div></div>
      <div class="col-md-3"><div class="card p-3 text-center">
        <div class="fs-3 fw-bold text-success">{n_new}</div>
        <div class="text-muted">Casos a importar</div>
      </div></div>
      <div class="col-md-3"><div class="card p-3 text-center">
        <div class="fs-3 fw-bold text-info">{stats['clientes_nuevos']}</div>
        <div class="text-muted">Clientes nuevos</div>
      </div></div>
      <div class="col-md-3"><div class="card p-3 text-center">
        <div class="fs-3 fw-bold text-warning">{len(merged)}</div>
        <div class="text-muted">Grupos unificados</div>
      </div></div>
    </div>

    {merged_section}

    <div class="card mb-4">
      <div class="card-header fw-semibold text-secondary">
        <i class="bi bi-skip-forward me-1"></i>Omitidos — ya existen en la DB ({stats['casos_existentes'] + stats['omitidos']})
      </div>
      <div style="max-height:200px;overflow-y:auto">
        <table class="table table-sm mb-0">
          <thead class="table-light"><tr><th>Carátula</th><th>Razón</th></tr></thead>
          <tbody>{rows_skip}</tbody>
        </table>
      </div>
    </div>

    <form method="post" action="/admin/import/run" id="importForm">
      <input type="hidden" name="client_map" id="clientMapInput" value="">
      <button class="btn btn-success btn-lg" type="submit" onclick="prepareSubmit()">
        <i class="bi bi-cloud-download me-2"></i>Importar {n_new} casos
      </button>
      <a href="/admin/import" class="btn btn-outline-secondary ms-2">Cancelar</a>
    </form>

    <script>
    // client_map mutable en JS
    let clientMap = {client_map_json};

    function separateVariant(btn, canonical, variant) {{
      // Sacar del grupo: la variante queda como su propio nombre
      clientMap[variant] = variant;
      // Remover el chip del DOM
      btn.closest('.variant-chip').remove();
    }}

    function prepareSubmit() {{
      document.getElementById('clientMapInput').value = JSON.stringify(clientMap);
    }}
    </script>"""

    return _page("Previsualización", body, "Importar")


@router.post("/import/run", response_class=HTMLResponse)
def import_run(client_map: str = Form(""), user=Depends(require_auth)):
    import traceback
    try:
        map_override = _json.loads(client_map) if client_map else None
        stats = run_import(dry_run=False, client_map_override=map_override)
    except Exception as e:
        detail = traceback.format_exc()
        return _page("Error", f'<div class="alert alert-danger"><strong>{type(e).__name__}: {e}</strong><pre class="mt-2 small">{detail}</pre></div>')

    if "error" in stats:
        return _page("Error", f'<div class="alert alert-danger"><pre class="mb-0" style="white-space:pre-wrap">{stats["error"]}</pre></div>')

    body = f"""
    <div class="alert alert-success fs-5">
      <i class="bi bi-check-circle-fill me-2"></i>
      Importación completada: <strong>{stats['casos_nuevos']} casos</strong>
      y <strong>{stats['clientes_nuevos']} clientes</strong> nuevos.
    </div>
    <a href="/admin/casos" class="btn btn-primary">Ver casos</a>
    <a href="/admin/clientes" class="btn btn-outline-secondary ms-2">Ver clientes</a>"""

    return _page("Importación completada", body)


# ──────────────────────────────────────────────
# SOLICITUDES DE BAJA
# ──────────────────────────────────────────────

@router.get("/solicitudes", response_class=HTMLResponse)
def solicitudes_list(user=Depends(require_auth)):
    with get_conn() as conn:
        rows = rows_to_list(conn.execute(
            "SELECT * FROM solicitudes_baja ORDER BY estado='pendiente' DESC, creado_en DESC"
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
          <td class="text-muted small">{r.get('solicitante') or '—'}</td>
          <td class="text-muted small">{r.get('motivo') or '—'}</td>
          <td>{estado_badge.get(r['estado'], r['estado'])}</td>
          <td>
            {"" if r['estado'] != 'pendiente' else f'''
            <form method="post" action="/admin/solicitudes/{r['id']}/aprobar" class="d-inline">
              <button class="btn btn-success btn-sm">Aprobar</button>
            </form>
            <form method="post" action="/admin/solicitudes/{r['id']}/rechazar" class="d-inline ms-1">
              <button class="btn btn-outline-danger btn-sm">Rechazar</button>
            </form>'''}
          </td>
        </tr>"""
        for r in rows
    )
    body = f"""
    <div class="card">
      <table class="table table-hover mb-0">
        <thead class="table-light">
          <tr><th>Fecha</th><th>Tipo</th><th>Objeto</th><th>Solicitante</th><th>Motivo</th><th>Estado</th><th>Acción</th></tr>
        </thead>
        <tbody>
          {rows_html or '<tr><td colspan="7" class="text-center text-muted py-3">Sin solicitudes</td></tr>'}
        </tbody>
      </table>
    </div>"""
    return _page("Solicitudes de baja", body)


@router.post("/solicitudes/{sid}/aprobar")
def solicitud_aprobar(sid: int, user=Depends(require_auth)):
    """Aprueba la solicitud: elimina el objeto y marca la solicitud como aprobada."""
    with get_conn() as conn:
        sol = row_to_dict(conn.execute(
            "SELECT * FROM solicitudes_baja WHERE id=?", (sid,)
        ).fetchone())
        if not sol or sol["estado"] != "pendiente":
            raise HTTPException(404)

        # Ejecutar la eliminación según el tipo
        if sol["tipo"] == "caso":
            conn.execute("DELETE FROM casos WHERE id=?", (sol["objeto_id"],))
        elif sol["tipo"] == "cliente":
            conn.execute("UPDATE casos SET cliente_id=NULL WHERE cliente_id=?", (sol["objeto_id"],))
            conn.execute("DELETE FROM clientes WHERE id=?", (sol["objeto_id"],))
        elif sol["tipo"] == "evento":
            conn.execute("DELETE FROM eventos_caso WHERE id=?", (sol["objeto_id"],))

        conn.execute(
            "UPDATE solicitudes_baja SET estado='aprobado', resuelto_en=datetime('now'), resuelto_por=? WHERE id=?",
            (user, sid)
        )
    return RedirectResponse("/admin/solicitudes", status_code=303)


@router.post("/solicitudes/{sid}/rechazar")
def solicitud_rechazar(sid: int, user=Depends(require_auth)):
    with get_conn() as conn:
        conn.execute(
            "UPDATE solicitudes_baja SET estado='rechazado', resuelto_en=datetime('now'), resuelto_por=? WHERE id=?",
            (user, sid)
        )
    return RedirectResponse("/admin/solicitudes", status_code=303)


# ──────────────────────────────────────────────
# IMPORTAR DESDE CALENDARIO
# ──────────────────────────────────────────────

# Eventos del calendario que NO son causas (se filtran en la importación)
_SKIP_KEYWORDS = [
    "home office", "vacaciones", "feriado", "feriados",
    "cumpleaños", "birthday", "franco", "licencia", "día libre",
]

def _should_skip_event(titulo: str) -> bool:
    t = titulo.lower()
    return any(kw in t for kw in _SKIP_KEYWORDS)


def _infer_tipo(titulo: str) -> str:
    t = titulo.lower()
    # Audiencias: "audiencia", "vista de causa", "oral" o abreviatura "aud"
    if any(w in t for w in ["audiencia", "vista", "oral"]) or re.search(r'\baud[\s\.\-]', t):
        return "audiencia"
    # Vencimientos: "vence", "vto", "vtto", "vencimiento", "plazo"
    if any(w in t for w in ["vencimiento", "vence", "vto.", "vtto", "plazo", "término", "termino"]):
        return "vencimiento"
    # Mediaciones
    if any(w in t for w in ["mediación", "mediacion"]):
        return "mediacion"
    # Pericias
    if any(w in t for w in ["pericia", "perito", "peritos"]):
        return "pericia"
    # Reuniones
    if any(w in t for w in ["reunión", "reunion", "entrevista"]):
        return "reunion"
    return "otro"


def _score_event_case(event_summary: str, caratula: str) -> int:
    """Puntaje de coincidencia entre título de evento y carátula de caso."""
    summary_lower = event_summary.lower()
    caratula_lower = caratula.lower()
    # Palabras significativas (> 3 chars, no stop words)
    stop = {"del", "los", "las", "con", "para", "por", "una", "uno", "que", "como"}
    words = [w for w in caratula_lower.split() if len(w) > 3 and w not in stop]
    return sum(1 for w in words if w in summary_lower)


@router.get("/import-calendar", response_class=HTMLResponse)
def import_calendar_get(user=Depends(require_auth)):
    body = """
    <div class="card mb-4">
      <div class="card-body">
        <p>Lee todos los eventos del calendario entre <strong>enero 2025</strong> y <strong>hoy</strong>
           e intenta asociarlos a causas existentes en la base de datos.</p>
        <p class="text-muted small mb-3">
          Podés ajustar la causa asignada en la previsualización antes de confirmar.
          Los eventos ya registrados (mismo ID de calendario) serán omitidos automáticamente.
        </p>
        <form method="post" action="/admin/import-calendar/preview">
          <button class="btn btn-outline-primary" type="submit">
            <i class="bi bi-eye me-1"></i>Cargar eventos del calendario
          </button>
        </form>
      </div>
    </div>"""
    return _page("Importar desde Calendario", body)


@router.post("/import-calendar/preview", response_class=HTMLResponse)
def import_calendar_preview(user=Depends(require_auth)):
    import traceback
    from datetime import datetime, timezone
    from googleapiclient.discovery import build
    from google_auth import get_credentials
    import os, base64

    try:
        creds = get_credentials()
        service = build("calendar", "v3", credentials=creds)

        raw_cal = os.getenv("CALENDAR_ID", "primary")
        if raw_cal and "@" not in raw_cal:
            try:
                padded = raw_cal + "=" * (4 - len(raw_cal) % 4)
                decoded = base64.b64decode(padded).decode()
                if "@" in decoded:
                    raw_cal = decoded
            except Exception:
                pass
        calendar_id = raw_cal

        time_min = "2025-01-01T00:00:00Z"
        time_max = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        events = []
        page_token = None
        while True:
            resp = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=500,
                pageToken=page_token,
            ).execute()
            events.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    except Exception as e:
        detail = traceback.format_exc()
        return _page("Error", f'<div class="alert alert-danger"><strong>{type(e).__name__}: {e}</strong><pre class="mt-2 small">{detail}</pre></div>')

    with get_conn() as conn:
        casos = rows_to_list(conn.execute(
            "SELECT id, caratula FROM casos ORDER BY caratula"
        ).fetchall())
        clientes = rows_to_list(conn.execute(
            "SELECT id, nombre FROM clientes ORDER BY nombre"
        ).fetchall())
        existing_ids = {
            r[0] for r in conn.execute(
                "SELECT calendar_event_id FROM eventos_caso WHERE calendar_event_id IS NOT NULL"
            ).fetchall()
        }

    clientes_opts = '<option value="">— Sin cliente —</option>' + "".join(
        f'<option value="{c["id"]}">{c["nombre"]}</option>' for c in clientes
    )

    rows_html = ""
    n_total = 0
    n_already = 0
    n_filtered = 0
    for ev in events:
        ev_id = ev.get("id", "")
        titulo = ev.get("summary", "(sin título)")
        start = ev.get("start", {})
        fecha = start.get("dateTime") or start.get("date") or ""
        fecha_short = fecha[:10]
        cal_link = ev.get("htmlLink", "")

        # Omitir ya registrados
        if ev_id in existing_ids:
            n_already += 1
            continue

        # Filtrar eventos no jurídicos (home office, vacaciones, etc.)
        if _should_skip_event(titulo):
            n_filtered += 1
            continue

        tipo_sugerido = _infer_tipo(titulo)

        # Buscar mejor caso sugerido por palabras clave
        best_caso_id = ""
        best_score = 0
        for c in casos:
            s = _score_event_case(titulo, c["caratula"])
            if s > best_score:
                best_score = s
                best_caso_id = str(c["id"])

        sel_opts = '<option value="">— Sin causa —</option>' + "".join(
            f'<option value="{c["id"]}" {"selected" if str(c["id"]) == best_caso_id and best_score > 0 else ""}>{c["caratula"]}</option>'
            for c in casos
        )
        score_badge = (
            f'<span class="badge bg-success ms-1" title="coincidencia automática">{best_score}✓</span>'
            if best_score > 0 else
            '<span class="badge bg-light text-muted border ms-1">sin match</span>'
        )
        safe_titulo = titulo.replace('"', '&quot;')

        rows_html += f"""
        <tr>
          <td><input type="checkbox" name="incluir" value="{ev_id}" class="form-check-input" {"checked" if best_score > 0 else ""}></td>
          <td class="small">{fecha_short}</td>
          <td>
            {titulo} {score_badge}
            {"" if not cal_link else f'<a href="{cal_link}" target="_blank" class="ms-1 text-muted"><i class="bi bi-box-arrow-up-right"></i></a>'}
            <input type="hidden" name="ev_id" value="{ev_id}">
            <input type="hidden" name="ev_titulo" value="{safe_titulo}">
            <input type="hidden" name="ev_fecha" value="{fecha}">
            <input type="hidden" name="ev_link" value="{cal_link}">
          </td>
          <td>
            <select name="caso_{ev_id}" class="form-select form-select-sm caso-sel"
                    data-evid="{ev_id}" onchange="toggleCliente(this)">{sel_opts}</select>
          </td>
          <td>
            <select name="cliente_{ev_id}" class="form-select form-select-sm"
                    {"style='display:none'" if best_score > 0 else ""}>{clientes_opts}</select>
          </td>
          <td>
            <select name="tipo_{ev_id}" class="form-select form-select-sm">
              {"".join(f'<option value="{t}" {"selected" if t == tipo_sugerido else ""}>{t}</option>' for t in ["audiencia","vencimiento","reunion","pericia","mediacion","otro"])}
            </select>
          </td>
        </tr>"""
        n_total += 1

    body = f"""
    <div class="row g-3 mb-4">
      <div class="col-md-3"><div class="card p-3 text-center">
        <div class="fs-3 fw-bold text-primary">{len(events)}</div>
        <div class="text-muted">Total en calendario</div>
      </div></div>
      <div class="col-md-3"><div class="card p-3 text-center">
        <div class="fs-3 fw-bold text-secondary">{n_already}</div>
        <div class="text-muted">Ya registrados</div>
      </div></div>
      <div class="col-md-3"><div class="card p-3 text-center">
        <div class="fs-3 fw-bold text-muted">{n_filtered}</div>
        <div class="text-muted">Filtrados (HO / Vac.)</div>
      </div></div>
      <div class="col-md-3"><div class="card p-3 text-center">
        <div class="fs-3 fw-bold text-success">{n_total}</div>
        <div class="text-muted">Para importar</div>
      </div></div>
    </div>

    <form method="post" action="/admin/import-calendar/run">
      <div class="card mb-4">
        <div class="card-header fw-semibold d-flex justify-content-between align-items-center">
          <span>Eventos nuevos — revisá y ajustá antes de confirmar</span>
          <div>
            <button type="button" class="btn btn-outline-secondary btn-sm me-1" onclick="toggleAll(true)">Marcar todos</button>
            <button type="button" class="btn btn-outline-secondary btn-sm" onclick="toggleAll(false)">Desmarcar todos</button>
          </div>
        </div>
        <div style="max-height:60vh;overflow-y:auto">
          <table class="table table-hover table-sm mb-0">
            <thead class="table-light sticky-top">
              <tr>
                <th style="width:30px"></th>
                <th style="width:90px">Fecha</th>
                <th>Título</th>
                <th style="width:220px">Causa</th>
                <th style="width:180px">Cliente <small class="text-muted">(si no hay causa)</small></th>
                <th style="width:120px">Tipo</th>
              </tr>
            </thead>
            <tbody>
              {rows_html or '<tr><td colspan="6" class="text-center text-muted py-3">Sin eventos nuevos para importar</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
      <button class="btn btn-success btn-lg" type="submit">
        <i class="bi bi-calendar-check me-2"></i>Registrar eventos seleccionados
      </button>
      <a href="/admin/import-calendar" class="btn btn-outline-secondary ms-2">Cancelar</a>
    </form>
    <script>
    function toggleAll(val) {{
      document.querySelectorAll('input[name="incluir"]').forEach(cb => cb.checked = val);
    }}
    // Mostrar selector de cliente solo cuando no hay causa seleccionada
    function toggleCliente(casoSel) {{
      const row = casoSel.closest('tr');
      const clienteSel = row.querySelector('select[name^="cliente_"]');
      if (clienteSel) {{
        clienteSel.style.display = casoSel.value ? 'none' : '';
        if (casoSel.value) clienteSel.value = '';
      }}
    }}
    </script>"""
    return _page("Previsualización calendario", body, "Importar calendario")


@router.post("/import-calendar/run", response_class=HTMLResponse)
async def import_calendar_run(request: Request, user=Depends(require_auth)):
    form = await request.form()
    incluidos = set(form.getlist("incluir"))
    ev_ids = form.getlist("ev_id")
    ev_titulos = form.getlist("ev_titulo")
    ev_fechas = form.getlist("ev_fecha")
    ev_links = form.getlist("ev_link")

    inserted = 0
    skipped = 0
    with get_conn() as conn:
        for i, ev_id in enumerate(ev_ids):
            if ev_id not in incluidos:
                skipped += 1
                continue
            titulo = ev_titulos[i] if i < len(ev_titulos) else ""
            fecha = ev_fechas[i] if i < len(ev_fechas) else ""
            link = ev_links[i] if i < len(ev_links) else ""
            caso_id_raw = form.get(f"caso_{ev_id}", "")
            cliente_id_raw = form.get(f"cliente_{ev_id}", "")
            tipo = form.get(f"tipo_{ev_id}", "otro")
            caso_id = int(caso_id_raw) if caso_id_raw else None
            cliente_id = int(cliente_id_raw) if cliente_id_raw else None

            # Skip si ya existe
            exists = conn.execute(
                "SELECT 1 FROM eventos_caso WHERE calendar_event_id=?", (ev_id,)
            ).fetchone()
            if exists:
                skipped += 1
                continue

            conn.execute(
                """INSERT INTO eventos_caso
                   (caso_id, cliente_id, calendar_event_id, calendar_link, titulo, fecha, tipo)
                   VALUES (?,?,?,?,?,?,?)""",
                (caso_id, cliente_id, ev_id, link, titulo, fecha, tipo)
            )
            inserted += 1

    body = f"""
    <div class="alert alert-success fs-5">
      <i class="bi bi-check-circle-fill me-2"></i>
      <strong>{inserted} eventos</strong> registrados correctamente.
      {f"({skipped} omitidos)" if skipped else ""}
    </div>
    <p class="text-muted">Los eventos sin causa asignada quedan registrados igual — podés vincularlos luego desde el detalle de cada causa.</p>
    <a href="/admin/casos" class="btn btn-primary">Ver causas</a>
    <a href="/admin/import-calendar" class="btn btn-outline-secondary ms-2">Importar más</a>"""
    return _page("Importación completada", body)
