#!/usr/bin/env python3
"""
Power BI MCP Deploy — CLI
Prueba todas las operaciones del servidor MCP directamente desde la terminal,
con salida progresiva paso a paso y spinner mientras espera respuestas.

Uso:
  python pbi_cli.py auth
  python pbi_cli.py workspaces [--filter "name eq 'Dev'"]
  python pbi_cli.py contents <workspace>  [--type SemanticModel|Report|Dashboard]
  python pbi_cli.py models <workspace>
  python pbi_cli.py download-model <workspace> <model> <ruta_destino>
  python pbi_cli.py upload-model <workspace> <ruta_origen> [--name <nombre>] [--folder "Ruta/Carpeta"]
  python pbi_cli.py download-workspace <workspace> <carpeta_destino>
  python pbi_cli.py download-report <workspace> <report> <ruta_destino>
  python pbi_cli.py upload-report <workspace> <ruta_origen> [--name <nombre>] [--rebind <modelo>] [--folder "Ruta/Carpeta"]
  python pbi_cli.py history <artefacto> [--type SemanticModel|Report]
  python pbi_cli.py deployments <workspace>
  python pbi_cli.py config-model <model> <workspace_destino> [--auto] [--profile <entorno>]
  python pbi_cli.py config-report <report> <workspace_destino> [--model <modelo>] [--auto] [--profile <entorno>]
  python pbi_cli.py list-configs [--type SemanticModel|Report]
  python pbi_cli.py setup-env <workspace> [--models M1,M2] [--reports "R1=M1,R2=M2"]
  python pbi_cli.py download-definitions <workspace> <carpeta_destino>

  # Entornos y proyectos (despliegue multi-artefacto con jerarquía)
  python pbi_cli.py env-create <alias> <workspace> --stage-order <N> [--type <tipo>] [--description <desc>]
  python pbi_cli.py env-list
  python pbi_cli.py project-create <nombre> [--description <desc>]
  python pbi_cli.py project-add-artifact <proyecto> model|report <nombre> [--rebind <modelo>] [--order N] [--notes N] [--folder "Ruta/Carpeta"]
  python pbi_cli.py project-remove-artifact <proyecto> model|report <nombre>
  python pbi_cli.py project-show <nombre>
  python pbi_cli.py project-list
  python pbi_cli.py project-structure <nombre>                      # artefactos + carpetas + estado por entorno
  python pbi_cli.py project-tree [nombre]                           # árbol ASCII (todos los proyectos si se omite)
  python pbi_cli.py deploy <proyecto> <entorno> <carpeta_local> [--respect-local-structure]   # explícito, salta la cadena (hotfix)
  python pbi_cli.py promote <proyecto> <entorno> [--yes]            # por defecto, entorno anterior -> entorno

  # Creación de workspaces
  python pbi_cli.py capacities                                                          # listar capacidades de Fabric
  python pbi_cli.py project-provision-workspaces <proyecto> [--capacity-id ID]           # modo automático (dev/acc/prod)
  python pbi_cli.py project-set-workspace <proyecto> <entorno> <workspace> [--type model|report] [--capacity-id ID]  # modo manual
"""

import argparse
import asyncio
import base64
import json
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# ── logging silencioso (el CLI tiene su propia salida) ──────────────────────
import logging
logging.disable(logging.CRITICAL)

# ── módulos del servidor ─────────────────────────────────────────────────────
from powerbi_mcp_server.auth.device_flow import (
    try_silent_auth, initiate_device_flow, complete_device_flow_sync, azure_cli_authenticate
)
from powerbi_mcp_server.auth.token_manager import AuthenticationStateManager
from powerbi_mcp_server.api.client import PowerBIClient
from powerbi_mcp_server.api.semantic_models import SemanticModelOperations
from powerbi_mcp_server.api.reports import ReportOperations
from powerbi_mcp_server.metadata import MetadataManager
from powerbi_mcp_server.metadata.deployment_config import DeploymentConfigManager
from powerbi_mcp_server.metadata.project_manager import ProjectManager


# ─────────────────────────────────────────────────────────────────────────────
# Salida con efecto de streaming
# ─────────────────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
RED    = "\033[31m"
DIM    = "\033[2m"


def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def c(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if _supports_color() else text


def step(msg: str):
    """Imprime un paso de progreso."""
    print(c(f"  → {msg}", CYAN), flush=True)


def ok(msg: str):
    print(c(f"  ✓ {msg}", GREEN), flush=True)


def warn(msg: str):
    print(c(f"  ⚠ {msg}", YELLOW), flush=True)


def err(msg: str):
    print(c(f"  ✗ {msg}", RED), flush=True)


def header(title: str):
    bar = "─" * (len(title) + 4)
    print(f"\n{c(bar, BOLD)}")
    print(f"{c(f'  {title}', BOLD)}")
    print(f"{c(bar, BOLD)}")


def stream_lines(lines: list[str], delay: float = 0.04):
    """Imprime líneas con un pequeño retardo para efecto de streaming."""
    for line in lines:
        print(line, flush=True)
        time.sleep(delay)


def clean_path(s: str) -> Path:
    """Strip stray quotes PowerShell sometimes appends when a path ends with backslash."""
    return Path(s.strip('"\''))


def confirm(msg: str) -> bool:
    try:
        answer = input(f"  {msg} [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes", "s", "si", "sí")


class Spinner:
    """Spinner en hilo separado mientras se espera una operación."""
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, msg: str):
        self.msg = msg
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        i = 0
        while not self._stop.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            print(f"\r  {c(frame, CYAN)} {self.msg}...", end="", flush=True)
            time.sleep(0.1)
            i += 1

    def __enter__(self):
        if _supports_color():
            self._thread.start()
        else:
            print(f"  {self.msg}...", flush=True)
        return self

    def __exit__(self, *_):
        self._stop.set()
        if _supports_color():
            self._thread.join()
            print("\r" + " " * (len(self.msg) + 10) + "\r", end="", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Autenticación CLI (interactiva — bloquea hasta completar)
# ─────────────────────────────────────────────────────────────────────────────

def get_token() -> str:
    state = AuthenticationStateManager()

    # 1. DPAPI cache
    with Spinner("Buscando sesión guardada"):
        token = state.get_current_token()
    if token:
        info = state.get_user_info() or {}
        ok(f"Sesión activa: {info.get('user_name')} <{info.get('user_email')}>")
        return token

    # 2. MSAL silent
    step("Sin sesión en caché, intentando renovación silenciosa...")
    try:
        result = try_silent_auth()
        if result:
            state.update_state(result)
            ok(f"Renovado silenciosamente: {result['user_name']} <{result['user_email']}>")
            return result["powerbi"]
    except Exception:
        pass

    # 3. Sesión az login existente
    step("Sin renovación silenciosa disponible, probando sesión Azure CLI (az login)...")
    with Spinner("Comprobando az login"):
        try:
            result = azure_cli_authenticate()
        except Exception:
            result = None
    if result:
        state.update_state(result)
        ok(f"Sesión Azure CLI reutilizada: {result['user_name']} <{result['user_email']}>")
        return result["powerbi"]

    # 4. Device Flow interactivo
    step("Iniciando Device Flow...")
    app, flow, message = initiate_device_flow()

    print()
    print(c("  ┌─────────────────────────────────────────────────────────┐", YELLOW))
    for line in message.strip().splitlines():
        print(c(f"  │  {line:<55} │", YELLOW))
    print(c("  └─────────────────────────────────────────────────────────┘", YELLOW))
    print()

    with Spinner("Esperando autenticación en el navegador"):
        result = complete_device_flow_sync(app, flow)

    state.update_state(result)
    ok(f"Autenticado: {result['user_name']} <{result['user_email']}>")
    return result["powerbi"]


def get_client() -> tuple[PowerBIClient, MetadataManager]:
    token = get_token()
    client = PowerBIClient(token)
    metadata = MetadataManager()
    asyncio.run(metadata.initialize())
    return client, metadata


# ─────────────────────────────────────────────────────────────────────────────
# Comandos
# ─────────────────────────────────────────────────────────────────────────────

def cmd_auth(_args):
    header("Autenticación")
    get_token()


def cmd_workspaces(args):
    header("Workspaces")
    client, _ = get_client()

    with Spinner("Consultando workspaces"):
        workspaces = client.list_workspaces(filter_query=getattr(args, "filter", None))

    ok(f"{len(workspaces)} workspace(s) encontrados")
    print()
    lines = []
    for ws in workspaces:
        lines.append(f"  {c(ws.get('name','?'), BOLD)}  {c(ws.get('id',''), DIM)}")
        if ws.get('type'):
            lines.append(f"    tipo: {ws['type']}")
    stream_lines(lines)


def cmd_contents(args):
    header(f"Contenido de '{args.workspace}'")
    client, _ = get_client()

    step(f"Buscando workspace '{args.workspace}'...")
    ws = client.get_workspace_by_name(args.workspace)
    if not ws:
        err(f"Workspace no encontrado: {args.workspace}")
        sys.exit(1)
    ok(f"ID: {ws['id']}")

    item_type = getattr(args, "type", None)
    label = item_type or "todos los elementos"
    with Spinner(f"Cargando {label}"):
        items = client.list_workspace_items(ws['id'], item_type=item_type)

    ok(f"{len(items)} elemento(s)")
    print()
    lines = []
    for item in items:
        tipo = item.get('type', item.get('itemType', '?'))
        lines.append(f"  [{c(tipo, CYAN)}] {c(item.get('displayName','?'), BOLD)}")
        lines.append(f"    id: {c(item.get('id','?'), DIM)}")
    stream_lines(lines)


def cmd_models(args):
    header(f"Modelos semánticos en '{args.workspace}'")
    client, _ = get_client()

    step(f"Buscando workspace...")
    ws = client.get_workspace_by_name(args.workspace)
    if not ws:
        err(f"Workspace no encontrado: {args.workspace}")
        sys.exit(1)

    with Spinner("Cargando modelos semánticos"):
        models = client.list_workspace_items(ws['id'], item_type='SemanticModel')

    ok(f"{len(models)} modelo(s)")
    print()
    lines = [f"  {c(m.get('displayName','?'), BOLD)}  {c(m.get('id',''), DIM)}" for m in models]
    stream_lines(lines)


def cmd_download_model(args):
    header(f"Descargando modelo '{args.model}'")
    client, metadata = get_client()
    sm_ops = SemanticModelOperations(client, metadata)

    step(f"Buscando workspace '{args.workspace}'...")
    ws = client.get_workspace_by_name(args.workspace)
    if not ws:
        err(f"Workspace no encontrado")
        sys.exit(1)

    step(f"Buscando modelo '{args.model}'...")
    items = client.list_workspace_items(ws['id'], 'SemanticModel')
    dataset = next((i for i in items if i['displayName'] == args.model), None)
    if not dataset:
        err(f"Modelo no encontrado: {args.model}")
        sys.exit(1)
    ok(f"ID: {dataset['id']}")

    target = clean_path(args.path)
    step(f"Descargando como PBIP → {target}")

    with Spinner(f"Descargando {args.model}"):
        result = asyncio.run(sm_ops.download_pbip(
            ws['id'], args.workspace, dataset['id'], args.model, target
        ))

    ok(f"Carpeta modelo: {result.get('directory_path', str(target))}")
    ok(f"Partes: {result.get('parts_count', '?')}")
    if result.get('versioned'):
        ok(f"Versión anterior conservada con sufijo: {result['version_suffix']}")
    if result.get('pbip_path'):
        ok(f"Abrir en PBI Desktop: {result['pbip_path']}")


def cmd_upload_model(args):
    header(f"Subiendo modelo desde '{args.path}'")
    client, metadata = get_client()
    sm_ops = SemanticModelOperations(client, metadata)

    step(f"Buscando workspace '{args.workspace}'...")
    ws = client.get_workspace_by_name(args.workspace)
    if not ws:
        err(f"Workspace no encontrado")
        sys.exit(1)

    source = clean_path(args.path)
    fmt = sm_ops.detect_format(source)
    if not fmt:
        err(f"No se puede detectar el formato de: {source}")
        sys.exit(1)
    step(f"Formato detectado: {fmt.upper()}")

    dataset_name = getattr(args, "name", None) or (
        source.name[: -len('.SemanticModel')] if source.name.endswith('.SemanticModel') else source.stem
    )

    folder_path = getattr(args, "folder", None)

    with Spinner(f"Subiendo {dataset_name}"):
        if fmt == "pbix":
            result = asyncio.run(sm_ops.upload_pbix(
                ws['id'], args.workspace, source, dataset_name, folder_path=folder_path
            ))
        else:
            result = asyncio.run(sm_ops.upload_pbip(
                ws['id'], args.workspace, source, dataset_name, folder_path=folder_path
            ))

    op = result.get('operation', 'publicado')
    ok(f"{op.capitalize()}: {result.get('dataset_name', dataset_name)}")
    ok(f"ID: {result.get('dataset_id', '?')}")
    ok(f"Partes: {result.get('parts_count', '?')}")


def cmd_download_report(args):
    header(f"Descargando informe '{args.report}'")
    client, metadata = get_client()
    rep_ops = ReportOperations(client, metadata)

    step(f"Buscando workspace '{args.workspace}'...")
    ws = client.get_workspace_by_name(args.workspace)
    if not ws:
        err(f"Workspace no encontrado")
        sys.exit(1)

    step(f"Buscando informe '{args.report}'...")
    items = client.list_workspace_items(ws['id'], 'Report')
    report = next((i for i in items if i['displayName'] == args.report), None)
    if not report:
        err(f"Informe no encontrado: {args.report}")
        sys.exit(1)
    ok(f"ID: {report['id']}")

    target = clean_path(args.path)
    step(f"Descargando → {target}")

    with Spinner(f"Descargando {args.report}"):
        result = asyncio.run(rep_ops.download_pbir(
            ws['id'], args.workspace, report['id'], args.report, target
        ))

    ok(f"Carpeta informe: {result.get('directory_path', str(target))}")
    ok(f"Partes: {result.get('parts_count', '?')}")
    if result.get('pbip_path'):
        ok(f"Abrir en PBI Desktop: {result['pbip_path']}")


def cmd_upload_report(args):
    header(f"Subiendo informe desde '{args.path}'")
    client, metadata = get_client()
    rep_ops = ReportOperations(client, metadata)

    step(f"Buscando workspace '{args.workspace}'...")
    ws = client.get_workspace_by_name(args.workspace)
    if not ws:
        err(f"Workspace no encontrado")
        sys.exit(1)

    source = clean_path(args.path)
    report_name = getattr(args, "name", None) or (
        source.name[: -len('.Report')] if source.name.endswith('.Report') else source.name
    )
    rebind = getattr(args, "rebind", None)
    rebind_workspace = getattr(args, "rebind_workspace", None)

    semantic_model_id = None
    if rebind:
        model_ws = ws
        if rebind_workspace:
            step(f"Buscando workspace del modelo '{rebind_workspace}'...")
            model_ws = client.get_workspace_by_name(rebind_workspace)
            if not model_ws:
                err(f"Workspace no encontrado: {rebind_workspace}")
                sys.exit(1)

        step(f"Buscando modelo para rebind: '{rebind}'...")
        models = client.list_workspace_items(model_ws['id'], 'SemanticModel')
        model = next((m for m in models if m['displayName'] == rebind), None)
        if model:
            semantic_model_id = model['id']
        else:
            # Modelo aún no publicado: si existe la carpeta hermana del PBIP, desplegarlo primero
            sibling = source.parent / f"{rebind}.SemanticModel"
            if sibling.is_dir():
                warn(f"Modelo '{rebind}' no publicado aún — desplegando primero desde {sibling.name}")
                sm_ops = SemanticModelOperations(client, metadata)
                with Spinner(f"Subiendo modelo {rebind}"):
                    model_result = asyncio.run(sm_ops.upload_pbip(
                        model_ws['id'], model_ws.get('name', args.workspace), sibling, rebind
                    ))
                semantic_model_id = model_result['dataset_id']
                ok(f"Modelo desplegado: {rebind} ({semantic_model_id})")
            else:
                err(f"Modelo no encontrado para rebind: {rebind}")
                sys.exit(1)
        ok(f"Rebind a: {rebind} ({semantic_model_id})")

    with Spinner(f"Subiendo {report_name}"):
        result = asyncio.run(rep_ops.upload_pbir(
            ws['id'], args.workspace, source, report_name, semantic_model_id,
            semantic_model_workspace_id=(model_ws['id'] if rebind else None),
            folder_path=getattr(args, "folder", None)
        ))

    op = result.get('operation', 'publicado')
    ok(f"{op.capitalize()}: {result.get('report_name', report_name)}")
    ok(f"ID: {result.get('report_id', '?')}")
    ok(f"Partes: {result.get('parts_count', '?')}")


def cmd_rebind_report(args):
    header(f"Reenlazando informe '{args.report}'")
    client, metadata = get_client()
    rep_ops = ReportOperations(client, metadata)

    step(f"Buscando workspace '{args.workspace}'...")
    ws = client.get_workspace_by_name(args.workspace)
    if not ws:
        err("Workspace no encontrado")
        sys.exit(1)

    model_ws_name = getattr(args, "model_workspace", None) or args.workspace
    model_ws = ws
    if model_ws_name != args.workspace:
        step(f"Buscando workspace del modelo '{model_ws_name}'...")
        model_ws = client.get_workspace_by_name(model_ws_name)
        if not model_ws:
            err(f"Workspace no encontrado: {model_ws_name}")
            sys.exit(1)

    step(f"Buscando modelo '{args.model}'...")
    models = client.list_workspace_items(model_ws['id'], 'SemanticModel')
    model = next((m for m in models if m['displayName'] == args.model), None)
    if not model:
        err(f"Modelo no encontrado: {args.model}")
        sys.exit(1)
    ok(f"Modelo: {args.model} ({model['id']})")

    with Spinner(f"Reenlazando {args.report}"):
        result = asyncio.run(rep_ops.rebind_report(
            workspace_id=ws['id'],
            workspace_name=args.workspace,
            report_name=args.report,
            semantic_model_id=model['id'],
            semantic_model_name=model['displayName'],
            semantic_model_workspace_name=model_ws_name
        ))

    ok(f"Reenlazado: {result.get('report_name')} → {result.get('rebound_model_name')} ({model_ws_name})")


def cmd_download_workspace(args):
    header(f"Descargando workspace '{args.workspace}'")
    client, metadata = get_client()
    sm_ops = SemanticModelOperations(client, metadata)
    rep_ops = ReportOperations(client, metadata)

    step(f"Buscando workspace '{args.workspace}'...")
    ws = client.get_workspace_by_name(args.workspace)
    if not ws:
        err(f"Workspace no encontrado")
        sys.exit(1)
    ws_id = ws['id']
    ok(f"ID: {ws_id}")

    dest = clean_path(args.path)
    dest.mkdir(parents=True, exist_ok=True)
    step(f"Destino: {dest}")

    errors = []

    # Semantic models
    models = client.list_workspace_items(ws_id, 'SemanticModel')
    ok(f"{len(models)} modelo(s) semántico(s)")
    for m in models:
        name = m['displayName']
        step(f"Descargando modelo: {name}")
        try:
            with Spinner(name):
                result = asyncio.run(sm_ops.download_pbip(ws_id, args.workspace, m['id'], name, dest))
            ok(f"  {name} — {result['parts_count']} partes")
        except Exception as e:
            errors.append(f"[Modelo] {name}: {e}")
            err(f"  {name}: {e}")

    # Reports
    reports = client.list_workspace_items(ws_id, 'Report')
    ok(f"{len(reports)} informe(s)")
    for r in reports:
        name = r['displayName']
        step(f"Descargando informe: {name}")
        try:
            with Spinner(name):
                result = asyncio.run(rep_ops.download_pbir(ws_id, args.workspace, r['id'], name, dest))
            ok(f"  {name} — {result['parts_count']} partes")
        except Exception as e:
            errors.append(f"[Informe] {name}: {e}")
            err(f"  {name}: {e}")

    print()
    ok(f"Completado. Carpeta: {dest}")
    ok(f"Modelos: {len(models)}  Informes: {len(reports)}  Errores: {len(errors)}")
    if errors:
        warn("Errores:")
        for e in errors:
            print(f"    {e}")


def cmd_download_definitions(args):
    header(f"Descargando definiciones del workspace '{args.workspace}'")
    client, _ = get_client()

    step(f"Buscando workspace '{args.workspace}'...")
    ws = client.get_workspace_by_name(args.workspace)
    if not ws:
        err(f"Workspace no encontrado: {args.workspace}")
        sys.exit(1)
    ws_id = ws['id']
    ok(f"ID: {ws_id}")

    dest = clean_path(args.path)
    dest.mkdir(parents=True, exist_ok=True)
    step(f"Destino: {dest}")

    with Spinner("Listando elementos del workspace"):
        items = client.list_workspace_items(ws_id)
    ok(f"{len(items)} elemento(s) en el workspace")

    downloaded = []
    skipped = []
    errors = []

    for item in items:
        name = item.get('displayName', '?')
        item_type = item.get('type', '?')
        item_id = item.get('id', '')

        step(f"[{item_type}] {name}")
        try:
            with Spinner(f"getDefinition {name}"):
                definition = client.get_item_definition(ws_id, item_id)
            parts = (definition.get('definition') or {}).get('parts', [])
            if not parts:
                skipped.append(f"{name} ({item_type}) — definición vacía")
                warn(f"  Sin partes, omitido")
                continue

            item_dir = dest / f"{name}.{item_type}"
            item_dir.mkdir(parents=True, exist_ok=True)

            for part in parts:
                part_path = part.get('path')
                payload = part.get('payload')
                payload_type = part.get('payloadType')
                if not part_path or not payload:
                    continue
                if payload_type == 'InlineBase64':
                    content = base64.b64decode(payload)
                else:
                    content = payload.encode('utf-8')
                file_path = item_dir / part_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(content)

            downloaded.append(f"{name} ({item_type}) — {len(parts)} partes")
            ok(f"  {name} — {len(parts)} partes → {item_dir.name}")
        except Exception as e:
            msg = str(e)
            if any(k in msg for k in ("ItemNotFound", "404", "not supported", "NotSupported", "400")):
                skipped.append(f"{name} ({item_type}) — no soporta getDefinition")
                warn(f"  No soporta getDefinition, omitido")
            else:
                errors.append(f"{name} ({item_type}): {msg}")
                err(f"  {msg}")

    print()
    ok(f"Completado. Carpeta: {dest}")
    ok(f"Descargados: {len(downloaded)}  Omitidos: {len(skipped)}  Errores: {len(errors)}")
    if downloaded:
        print(c("  Descargados:", BOLD))
        for d in downloaded:
            print(f"    {d}")
    if skipped:
        print(c("  Omitidos:", DIM))
        for s in skipped:
            print(f"    {s}")
    if errors:
        warn("Errores:")
        for e in errors:
            print(f"    {e}")


def cmd_history(args):
    header(f"Historial de versiones: '{args.artifact}'")
    _, metadata = get_client()

    with Spinner("Consultando historial"):
        history = metadata.get_version_history(args.artifact, getattr(args, "type", None))

    ok(f"{len(history)} entrada(s)")
    print()
    lines = []
    for entry in history:
        lines.append(f"  {c(entry.get('downloaded_at','?'), CYAN)}  {c(entry.get('local_file_path','?'), DIM)}")
        if entry.get('version_suffix'):
            lines.append(f"    versión: {entry['version_suffix']}")
    stream_lines(lines)


def cmd_deployments(args):
    header(f"Despliegues en '{args.workspace}'")
    client, metadata = get_client()

    step(f"Buscando workspace...")
    ws = client.get_workspace_by_name(args.workspace)
    if not ws:
        err(f"Workspace no encontrado")
        sys.exit(1)

    with Spinner("Consultando despliegues"):
        deployments = metadata.get_workspace_deployments(ws['id'])

    ok(f"{len(deployments)} despliegue(s)")
    print()
    lines = []
    for d in deployments:
        lines.append(f"  {c(d.get('uploaded_at','?'), CYAN)}  {c(d.get('artifact_name','?'), BOLD)}")
        lines.append(f"    tipo: {d.get('artifact_type','?')}  |  op: {d.get('operation_type','?')}")
    stream_lines(lines)


def cmd_config_model(args):
    header(f"Configurar despliegue de modelo '{args.model}'")
    client, metadata = get_client()
    deploy_cfg = DeploymentConfigManager(metadata.database)

    step(f"Resolviendo workspace '{args.workspace_dest}'...")
    ws = client.get_workspace_by_name(args.workspace_dest)
    ws_id = ws['id'] if ws else ''
    if not ws:
        warn("Workspace no encontrado — guardando solo el nombre")

    profile_name = getattr(args, "profile", None)
    profile_id = deploy_cfg.resolve_profile_id(profile_name)
    auto = getattr(args, "auto", False)
    existing = deploy_cfg.db.get_semantic_model_config(args.model, profile_id=profile_id)

    with Spinner("Guardando configuración"):
        if existing:
            deploy_cfg.db.update_semantic_model_config(
                model_name=args.model,
                target_workspace_id=ws_id,
                target_workspace_name=args.workspace_dest,
                auto_deploy=auto,
                profile_id=profile_id
            )
            action = "actualizada"
        else:
            deploy_cfg.db.create_semantic_model_config(
                model_name=args.model,
                target_workspace_id=ws_id,
                target_workspace_name=args.workspace_dest,
                profile_id=profile_id,
                auto_deploy=auto
            )
            action = "creada"

    entorno = f" [{profile_name}]" if profile_name else ""
    ok(f"Configuración {action}: {args.model} → {args.workspace_dest}{entorno}  (auto={auto})")


def cmd_config_report(args):
    header(f"Configurar despliegue de informe '{args.report}'")
    client, metadata = get_client()
    deploy_cfg = DeploymentConfigManager(metadata.database)

    step(f"Resolviendo workspace '{args.workspace_dest}'...")
    ws = client.get_workspace_by_name(args.workspace_dest)
    ws_id = ws['id'] if ws else ''

    model_name = getattr(args, "model", None)
    model_id = None
    if model_name and ws:
        step(f"Buscando modelo '{model_name}'...")
        models = client.list_workspace_items(ws_id, 'SemanticModel')
        model = next((m for m in models if m['displayName'] == model_name), None)
        model_id = model['id'] if model else None
        if not model_id:
            warn(f"Modelo '{model_name}' no encontrado — guardando solo nombre")

    profile_name = getattr(args, "profile", None)
    profile_id = deploy_cfg.resolve_profile_id(profile_name)
    auto = getattr(args, "auto", False)
    existing = deploy_cfg.db.get_report_config(args.report, profile_id=profile_id)

    with Spinner("Guardando configuración"):
        if existing:
            deploy_cfg.db.update_report_config(
                report_name=args.report,
                target_workspace_id=ws_id,
                target_workspace_name=args.workspace_dest,
                target_semantic_model_name=model_name,
                target_model_workspace_name=args.workspace_dest,
                auto_deploy=auto,
                auto_rebind=True,
                profile_id=profile_id
            )
            action = "actualizada"
        else:
            deploy_cfg.db.create_report_config(
                report_name=args.report,
                target_workspace_id=ws_id,
                target_workspace_name=args.workspace_dest,
                target_semantic_model_id=model_id,
                target_semantic_model_name=model_name,
                target_model_workspace_id=ws_id,
                target_model_workspace_name=args.workspace_dest,
                profile_id=profile_id,
                auto_deploy=auto,
                auto_rebind=True
            )
            action = "creada"

    entorno = f" [{profile_name}]" if profile_name else ""
    ok(f"Configuración {action}: {args.report} → {args.workspace_dest}{entorno}  (rebind={model_name}, auto={auto})")


def cmd_list_configs(args):
    header("Configuraciones de despliegue")
    _, metadata = get_client()
    deploy_cfg = DeploymentConfigManager(metadata.database)

    artifact_type = getattr(args, "type", None)

    with Spinner("Cargando configuraciones"):
        if artifact_type == "SemanticModel":
            models = deploy_cfg.db.list_semantic_model_configs()
            reports = []
        elif artifact_type == "Report":
            models = []
            reports = deploy_cfg.db.list_report_configs()
        else:
            models = deploy_cfg.db.list_semantic_model_configs()
            reports = deploy_cfg.db.list_report_configs()

    print()
    if models:
        print(c("  Modelos semánticos:", BOLD))
        lines = []
        for m in models:
            lines.append(f"    {c(m.get('model_name','?'), CYAN)}  →  {m.get('target_workspace_name','?')}"
                         f"  auto={m.get('auto_deploy', False)}")
        stream_lines(lines, delay=0.03)

    if reports:
        print(c("\n  Informes:", BOLD))
        lines = []
        for r in reports:
            rebind = r.get('target_semantic_model_name', '-')
            lines.append(f"    {c(r.get('report_name','?'), CYAN)}  →  {r.get('target_workspace_name','?')}"
                         f"  rebind={rebind}  auto={r.get('auto_deploy', False)}")
        stream_lines(lines, delay=0.03)

    if not models and not reports:
        warn("No hay configuraciones guardadas aún. Usa config-model o config-report.")


def cmd_setup_env(args):
    header(f"Configurar entorno de desarrollo: '{args.workspace}'")
    client, metadata = get_client()
    deploy_cfg = DeploymentConfigManager(metadata.database)

    step(f"Resolviendo workspace...")
    ws = client.get_workspace_by_name(args.workspace)
    ws_id = ws['id'] if ws else None
    if not ws_id:
        warn("Workspace no encontrado — guardando solo nombre")

    models_list = []
    if getattr(args, "models", None):
        models_list = [m.strip() for m in args.models.split(",")]

    report_map = {}
    if getattr(args, "reports", None):
        for pair in args.reports.split(","):
            if "=" in pair:
                r, m = pair.split("=", 1)
                report_map[r.strip()] = m.strip()

    with Spinner("Configurando entorno"):
        result = deploy_cfg.setup_development_environment(
            workspace_name=args.workspace,
            workspace_id=ws_id,
            semantic_models=models_list,
            reports=report_map,
        )

    ok(f"Entorno configurado: {len(result.get('semantic_models', []))} modelos, "
       f"{len(result.get('reports', []))} informes")


def cmd_env_create(args):
    header(f"Configurar entorno '{args.alias}'")
    client, metadata = get_client()
    deploy_cfg = DeploymentConfigManager(metadata.database)

    step(f"Resolviendo workspace '{args.workspace}'...")
    ws = client.get_workspace_by_name(args.workspace)
    ws_id = ws['id'] if ws else ''
    if not ws:
        warn("Workspace no encontrado — guardando solo el nombre")

    with Spinner("Guardando entorno"):
        result = deploy_cfg.configure_environment(
            profile_name=args.alias,
            target_workspace_name=args.workspace,
            target_workspace_id=ws_id,
            stage_order=getattr(args, "stage_order", None),
            environment_type=getattr(args, "type", None) or "development",
            description=getattr(args, "description", None)
        )

    orden = f" (stage_order={result['stage_order']})" if result['stage_order'] is not None else ""
    ok(f"Entorno {result['action']}: {args.alias} → {args.workspace}{orden}")


def cmd_env_list(_args):
    header("Entornos configurados")
    _, metadata = get_client()
    deploy_cfg = DeploymentConfigManager(metadata.database)

    with Spinner("Consultando entornos"):
        environments = deploy_cfg.list_environments()

    if not environments:
        warn("No hay entornos configurados aún. Usa env-create.")
        return

    print()
    chain = " → ".join(
        f"{e['profile_name']} ({e['stage_order']})" if e.get('stage_order') is not None else f"{e['profile_name']} (sin orden)"
        for e in environments
    )
    ok(chain)
    print()
    lines = []
    for e in environments:
        lines.append(f"  {c(e['profile_name'], BOLD)}  →  {e.get('target_workspace_name', '?')}")
    stream_lines(lines)


def cmd_project_create(args):
    header(f"Crear proyecto '{args.name}'")
    _, metadata = get_client()
    pm = ProjectManager(metadata.database, DeploymentConfigManager(metadata.database), metadata, None, None, None)

    with Spinner("Creando proyecto"):
        result = pm.create_project(args.name, getattr(args, "description", None))

    ok(f"Proyecto creado: {result['project_name']} (ID: {result['id']})")


def cmd_project_add_artifact(args):
    header(f"Añadir artefacto a proyecto '{args.project}'")
    _, metadata = get_client()
    pm = ProjectManager(metadata.database, DeploymentConfigManager(metadata.database), metadata, None, None, None)

    artifact_type = "model" if args.type == "model" else "report"
    with Spinner("Guardando artefacto"):
        result = pm.add_project_artifact(
            project_name=args.project,
            artifact_type=artifact_type,
            artifact_name=args.artifact,
            rebind_to_artifact_name=getattr(args, "rebind", None),
            sequence_order=getattr(args, "order", None),
            notes=getattr(args, "notes", None),
            folder_path=getattr(args, "folder", None)
        )

    rebind = f"  (rebind → {result['rebind_to_artifact_name']})" if result.get('rebind_to_artifact_name') else ""
    folder = f"  [carpeta: {result['folder_path']}]" if result.get('folder_path') else ""
    ok(f"Añadido: {result['artifact_type']}/{result['artifact_name']} a '{args.project}'{rebind}{folder}")


def cmd_project_remove_artifact(args):
    header(f"Quitar artefacto de proyecto '{args.project}'")
    _, metadata = get_client()
    pm = ProjectManager(metadata.database, DeploymentConfigManager(metadata.database), metadata, None, None, None)

    artifact_type = "model" if args.type == "model" else "report"
    with Spinner("Quitando artefacto"):
        removed = pm.remove_project_artifact(args.project, artifact_type, args.artifact)

    if removed:
        ok(f"Quitado: {args.artifact} de '{args.project}'")
    else:
        warn(f"No estaba en el proyecto: {args.artifact}")


def cmd_project_show(args):
    header(f"Proyecto '{args.name}'")
    _, metadata = get_client()
    pm = ProjectManager(metadata.database, DeploymentConfigManager(metadata.database), metadata, None, None, None)

    with Spinner("Consultando proyecto"):
        project = pm.get_project(args.name)

    ok(f"{project['project_name']}  ({len(project['artifacts'])} artefacto(s))")
    print()
    lines = []
    for a in project['artifacts']:
        rebind = f"  → rebind: {a['rebind_to_artifact_name']}" if a.get('rebind_to_artifact_name') else ""
        folder = f"  carpeta: {a['folder_path']}" if a.get('folder_path') else ""
        lines.append(f"  [{c(a['artifact_type'], CYAN)}] {c(a['artifact_name'], BOLD)}{rebind}{folder}")
    stream_lines(lines)


def cmd_project_list(_args):
    header("Proyectos")
    _, metadata = get_client()
    pm = ProjectManager(metadata.database, DeploymentConfigManager(metadata.database), metadata, None, None, None)

    with Spinner("Consultando proyectos"):
        projects = pm.list_projects()

    ok(f"{len(projects)} proyecto(s)")
    print()
    lines = [f"  {c(p['project_name'], BOLD)}" + (f"  — {p['description']}" if p.get('description') else "")
             for p in projects]
    stream_lines(lines)


def cmd_project_structure(args):
    header(f"Estructura de despliegue: proyecto '{args.name}'")
    _, metadata = get_client()
    pm = ProjectManager(metadata.database, DeploymentConfigManager(metadata.database), metadata, None, None, None)

    with Spinner("Consultando estructura"):
        structure = pm.get_deployment_structure(args.name)

    if structure.get('description'):
        print(f"  {c(structure['description'], DIM)}")
    print()

    if not structure['environments']:
        warn("No hay entornos configurados aún. Usa env-create.")
        return

    for env in structure['environments']:
        orden = f" (stage_order={env['stage_order']})" if env.get('stage_order') is not None else ""
        print(c(f"  {env['profile_name']}{orden} → {env.get('target_workspace_name', '?')}", BOLD))
        lines = []
        for a in env['artifacts']:
            folder = a['target_folder_path'] or "(raíz del workspace)"
            state = a.get('current_state')
            if state:
                origen = f" desde {state['promoted_from']}" if state.get('promoted_from') else ""
                estado = f"ya desplegado — {state.get('last_operation')}{origen} ({state.get('updated_at')})"
            else:
                estado = "sin desplegar todavía"
            lines.append(
                f"    [{c(a['artifact_type'], CYAN)}] {a['artifact_name']}  →  {folder}  —  {estado}"
            )
        stream_lines(lines, delay=0.02)
        print()


def cmd_project_set_workspace(args):
    header(f"Configurar workspace de '{args.project}' para el entorno '{args.environment}'")
    client, metadata = get_client()
    pm = _build_project_manager(client, metadata)

    with Spinner(f"Resolviendo/creando workspace '{args.workspace}'"):
        result = asyncio.run(pm.configure_project_workspace(
            args.project, args.environment, args.workspace,
            artifact_type=getattr(args, "type", None), capacity_id=getattr(args, "capacity_id", None)
        ))

    accion = "creado" if result['created'] else "reutilizado"
    ok(f"Workspace {accion}: {result['workspace_name']}  [{result['artifact_type']}]  "
       f"para '{args.project}' en '{args.environment}'")


def cmd_project_provision_workspaces(args):
    header(f"Aprovisionando workspaces (modo automático): proyecto '{args.project}'")
    client, metadata = get_client()
    pm = _build_project_manager(client, metadata)

    with Spinner("Creando entornos y workspaces"):
        result = asyncio.run(pm.auto_provision_project_workspaces(
            args.project, capacity_id=getattr(args, "capacity_id", None)
        ))

    if result['environments_created']:
        ok(f"Entornos creados: {', '.join(result['environments_created'])}")
    print()
    lines = []
    for w in result['workspaces']:
        accion = "creado" if w['created'] else "reutilizado"
        lines.append(f"  [{w['environment']}] {w['artifact_type']}: {w['workspace_name']}  ({accion})")
    stream_lines(lines)


def cmd_capacities(_args):
    header("Capacidades de Fabric")
    client, _ = get_client()

    with Spinner("Consultando capacidades"):
        capacities = client.list_capacities()

    ok(f"{len(capacities)} capacidad(es)")
    print()
    lines = [
        f"  {c(cap.get('displayName', '?'), BOLD)}  {c(cap.get('id', ''), DIM)}  "
        f"sku={cap.get('sku', '?')}  estado={cap.get('state', '?')}"
        for cap in capacities
    ]
    stream_lines(lines)


def cmd_project_tree(args):
    header("Árbol de despliegue")
    _, metadata = get_client()
    pm = ProjectManager(metadata.database, DeploymentConfigManager(metadata.database), metadata, None, None, None)

    with Spinner("Construyendo árbol"):
        tree = pm.render_deployment_tree(getattr(args, "project", None))

    print()
    print(tree)


def _build_project_manager(client, metadata) -> ProjectManager:
    deploy_cfg = DeploymentConfigManager(metadata.database)
    sm_ops = SemanticModelOperations(client, metadata)
    rep_ops = ReportOperations(client, metadata)
    return ProjectManager(metadata.database, deploy_cfg, metadata, client, sm_ops, rep_ops)


def cmd_deploy(args):
    header(f"Deploy explícito: proyecto '{args.project}' → entorno '{args.environment}'")
    warn("Esto sube directamente desde tu carpeta local, saltándose la cadena de promoción. "
         "Úsalo solo para casos de emergencia/hotfix; para el flujo normal usa 'promote'.")
    client, metadata = get_client()
    pm = _build_project_manager(client, metadata)

    source = clean_path(args.source_dir)
    respect_local_structure = getattr(args, "respect_local_structure", False)
    if respect_local_structure:
        step("Respetando estructura de carpetas local")

    with Spinner(f"Desplegando {args.project}"):
        result = asyncio.run(pm.deploy_project(
            args.project, args.environment, source, respect_local_structure=respect_local_structure
        ))

    ok(f"Modelos desplegados: {len(result.get('semantic_models', []))}")
    ok(f"Informes desplegados: {len(result.get('reports', []))}")


def cmd_promote(args):
    header(f"Promote: proyecto '{args.project}' → entorno '{args.environment}'")
    client, metadata = get_client()
    pm = _build_project_manager(client, metadata)

    with Spinner(f"Comprobando divergencia (drift)"):
        result = asyncio.run(pm.promote_project(args.project, args.environment, confirm_drift=False))

    if result.get('needs_confirmation'):
        warn(f"Divergencia detectada respecto al entorno origen ({result.get('source_environment', '?')}):")
        for d in result.get('drift', []):
            print(f"    [{d['artifact_type']}] {d['artifact_name']}:")
            for reason in d['reasons']:
                print(f"      - {reason}")
        proceed = getattr(args, "yes", False) or confirm("¿Confirmas la sobrescritura?")
        if not proceed:
            warn("Promoción cancelada.")
            return
        with Spinner(f"Promocionando {args.project} (confirmado)"):
            result = asyncio.run(pm.promote_project(args.project, args.environment, confirm_drift=True))

    if not result.get('success'):
        err(f"No se pudo promocionar: {result.get('message', result)}")
        sys.exit(1)

    ok(f"Promocionado desde '{result.get('source_environment')}' a '{result.get('target_environment')}'")
    ok(f"Modelos: {len(result.get('semantic_models', []))}  Informes: {len(result.get('reports', []))}")


# ─────────────────────────────────────────────────────────────────────────────
# Parser principal
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pbi",
        description="Power BI MCP Deploy — CLI de pruebas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", metavar="comando")

    # auth
    sub.add_parser("auth", help="Autenticar con Microsoft")

    # workspaces
    pw = sub.add_parser("workspaces", help="Listar workspaces")
    pw.add_argument("--filter", help="Filtro OData (ej: \"name eq 'Dev'\")")

    # contents
    pc = sub.add_parser("contents", help="Contenido de un workspace")
    pc.add_argument("workspace")
    pc.add_argument("--type", choices=["SemanticModel", "Report", "Dashboard"])

    # models
    pm = sub.add_parser("models", help="Modelos semánticos en un workspace")
    pm.add_argument("workspace")

    # download-workspace
    pdw = sub.add_parser("download-workspace", help="Descargar todo el workspace (modelos + informes)")
    pdw.add_argument("workspace")
    pdw.add_argument("path", help="Carpeta destino")

    # download-definitions
    pdd = sub.add_parser("download-definitions", help="Descargar todos los artefactos que soporten getDefinition")
    pdd.add_argument("workspace")
    pdd.add_argument("path", help="Carpeta destino")

    # download-model
    pdm = sub.add_parser("download-model", help="Descargar modelo semántico")
    pdm.add_argument("workspace")
    pdm.add_argument("model")
    pdm.add_argument("path", help="Carpeta base del proyecto PBIP (ej: D:\\Demo\\)")

    # upload-model
    pum = sub.add_parser("upload-model", help="Subir modelo semántico")
    pum.add_argument("workspace")
    pum.add_argument("path", help="Ruta origen (.pbix o carpeta PBIP)")
    pum.add_argument("--name", help="Nombre en el servicio")
    pum.add_argument("--folder", help="Ruta de carpeta dentro del workspace, ej. 'Ventas/Modelos' (se crea si no existe)")

    # download-report
    pdr = sub.add_parser("download-report", help="Descargar informe")
    pdr.add_argument("workspace")
    pdr.add_argument("report")
    pdr.add_argument("path", help="Carpeta base del proyecto PBIP (ej: D:\\Demo\\)")

    # upload-report
    pur = sub.add_parser("upload-report", help="Subir informe")
    pur.add_argument("workspace")
    pur.add_argument("path", help="Carpeta PBIR o fichero JSON")
    pur.add_argument("--name", help="Nombre en el servicio")
    pur.add_argument("--rebind", help="Modelo semántico al que reenlazar")
    pur.add_argument("--rebind-workspace", help="Workspace donde buscar el modelo de --rebind (si es distinto al de destino)")
    pur.add_argument("--folder", help="Ruta de carpeta dentro del workspace, ej. 'Ventas/Informes' (se crea si no existe)")

    # rebind-report
    prr = sub.add_parser("rebind-report", help="Reenlazar un informe ya publicado a otro modelo semántico")
    prr.add_argument("workspace")
    prr.add_argument("report")
    prr.add_argument("model", help="Nombre del modelo semántico destino")
    prr.add_argument("--model-workspace", help="Workspace del modelo destino (si es distinto al del informe)")

    # history
    ph = sub.add_parser("history", help="Historial de versiones de un artefacto")
    ph.add_argument("artifact")
    ph.add_argument("--type", choices=["SemanticModel", "Report"])

    # deployments
    pde = sub.add_parser("deployments", help="Historial de despliegues en un workspace")
    pde.add_argument("workspace")

    # config-model
    pcm = sub.add_parser("config-model", help="Configurar despliegue de modelo")
    pcm.add_argument("model")
    pcm.add_argument("workspace_dest", metavar="workspace_destino")
    pcm.add_argument("--auto", action="store_true", help="Auto-deploy activado")
    pcm.add_argument("--profile", help="Entorno al que aplica esta configuración (alias de env-create)")

    # config-report
    pcr = sub.add_parser("config-report", help="Configurar despliegue de informe")
    pcr.add_argument("report")
    pcr.add_argument("workspace_dest", metavar="workspace_destino")
    pcr.add_argument("--model", help="Modelo semántico para rebind")
    pcr.add_argument("--auto", action="store_true")
    pcr.add_argument("--profile", help="Entorno al que aplica esta configuración (alias de env-create)")

    # list-configs
    plc = sub.add_parser("list-configs", help="Listar configuraciones de despliegue")
    plc.add_argument("--type", choices=["SemanticModel", "Report"])

    # setup-env
    pse = sub.add_parser("setup-env", help="Configurar entorno de desarrollo completo")
    pse.add_argument("workspace")
    pse.add_argument("--models", help="Modelos separados por coma: 'M1,M2'")
    pse.add_argument("--reports", help="Mapeo informe=modelo separados por coma: 'R1=M1,R2=M2'")

    # env-create
    pec = sub.add_parser("env-create", help="Crear/actualizar un entorno (alias + posición en la cadena de promoción)")
    pec.add_argument("alias", help="Nombre del entorno (ej: Desarrollo, Integración, Producción)")
    pec.add_argument("workspace", help="Workspace de Fabric asociado")
    pec.add_argument("--stage-order", type=int, dest="stage_order", help="Posición en la cadena de promoción (0,1,2...)")
    pec.add_argument("--type", help="Etiqueta de tipo de entorno (ej: development, production)")
    pec.add_argument("--description", help="Descripción opcional")

    # env-list
    sub.add_parser("env-list", help="Listar entornos ordenados por su posición en la cadena de promoción")

    # project-create
    ppc = sub.add_parser("project-create", help="Crear un proyecto (agrupación de modelos + informes)")
    ppc.add_argument("name")
    ppc.add_argument("--description", help="Descripción opcional")

    # project-add-artifact
    ppa = sub.add_parser("project-add-artifact", help="Añadir un modelo o informe a un proyecto")
    ppa.add_argument("project")
    ppa.add_argument("type", choices=["model", "report"])
    ppa.add_argument("artifact", help="Nombre del artefacto")
    ppa.add_argument("--rebind", help="Solo para report: nombre del modelo del proyecto al que reenlazar")
    ppa.add_argument("--order", type=int, help="Orden opcional dentro de su tipo")
    ppa.add_argument("--notes", help="Notas opcionales")
    ppa.add_argument("--folder", help="Ruta de carpeta dentro del workspace de destino, ej. 'Ventas/Modelos' (se crea si no existe)")

    # project-remove-artifact
    ppr = sub.add_parser("project-remove-artifact", help="Quitar un modelo o informe de un proyecto")
    ppr.add_argument("project")
    ppr.add_argument("type", choices=["model", "report"])
    ppr.add_argument("artifact")

    # project-show
    pps = sub.add_parser("project-show", help="Mostrar un proyecto y sus artefactos")
    pps.add_argument("name")

    # project-list
    sub.add_parser("project-list", help="Listar todos los proyectos")

    # project-structure
    pst = sub.add_parser("project-structure", help="Mostrar la estructura completa de despliegue de un proyecto (artefactos, carpetas, entornos, estado)")
    pst.add_argument("name")

    # project-set-workspace
    ppw = sub.add_parser("project-set-workspace", help="Modo manual: asigna (y crea si hace falta) el workspace de un proyecto para un entorno")
    ppw.add_argument("project")
    ppw.add_argument("environment")
    ppw.add_argument("workspace", help="Nombre del workspace a usar/crear")
    ppw.add_argument("--type", choices=["model", "report"], help="Limitar a modelos o a reports (si se omite, workspace combinado)")
    ppw.add_argument("--capacity-id", dest="capacity_id", help="ID de capacidad de Fabric a asignar si se crea el workspace (ver 'capacities')")

    # project-provision-workspaces
    ppp2 = sub.add_parser("project-provision-workspaces", help="Modo automático: crea entornos dev/acc/prod y workspaces separados de modelos/reports para un proyecto")
    ppp2.add_argument("project")
    ppp2.add_argument("--capacity-id", dest="capacity_id", help="ID de capacidad de Fabric a asignar a los workspaces creados")

    # capacities
    sub.add_parser("capacities", help="Listar capacidades de Fabric disponibles")

    # project-tree
    ptr = sub.add_parser("project-tree", help="Árbol de despliegue (proyectos/entornos/carpetas/artefactos)")
    ptr.add_argument("project", nargs="?", help="Nombre del proyecto (opcional; si se omite, muestra todos)")

    # deploy
    pdp = sub.add_parser("deploy", help="Deploy explícito: sube un proyecto desde una carpeta local a un entorno (hotfix/emergencia)")
    pdp.add_argument("project")
    pdp.add_argument("environment")
    pdp.add_argument("source_dir", help="Carpeta base con las subcarpetas .SemanticModel/.Report de cada artefacto")
    pdp.add_argument("--respect-local-structure", action="store_true", dest="respect_local_structure",
                      help="Replica la jerarquía de subcarpetas locales como carpetas en el workspace destino")

    # promote
    ppp = sub.add_parser("promote", help="Flujo por defecto: promociona un proyecto desde el entorno anterior de la cadena")
    ppp.add_argument("project")
    ppp.add_argument("environment")
    ppp.add_argument("--yes", action="store_true", help="Confirma automáticamente si hay divergencia (drift)")

    return p


COMMANDS = {
    "auth":               cmd_auth,
    "workspaces":         cmd_workspaces,
    "contents":           cmd_contents,
    "models":             cmd_models,
    "download-definitions": cmd_download_definitions,
    "download-workspace": cmd_download_workspace,
    "download-model":     cmd_download_model,
    "upload-model":   cmd_upload_model,
    "download-report":cmd_download_report,
    "upload-report":  cmd_upload_report,
    "rebind-report":  cmd_rebind_report,
    "history":        cmd_history,
    "deployments":    cmd_deployments,
    "config-model":   cmd_config_model,
    "config-report":  cmd_config_report,
    "list-configs":   cmd_list_configs,
    "setup-env":      cmd_setup_env,
    "env-create":             cmd_env_create,
    "env-list":               cmd_env_list,
    "project-create":         cmd_project_create,
    "project-add-artifact":   cmd_project_add_artifact,
    "project-remove-artifact": cmd_project_remove_artifact,
    "project-show":           cmd_project_show,
    "project-list":           cmd_project_list,
    "project-structure":      cmd_project_structure,
    "project-set-workspace":  cmd_project_set_workspace,
    "project-provision-workspaces": cmd_project_provision_workspaces,
    "capacities":             cmd_capacities,
    "project-tree":           cmd_project_tree,
    "deploy":                 cmd_deploy,
    "promote":                cmd_promote,
}


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        sys.exit(0)

    fn = COMMANDS.get(args.cmd)
    if not fn:
        err(f"Comando desconocido: {args.cmd}")
        sys.exit(1)

    try:
        fn(args)
        print()
    except KeyboardInterrupt:
        print()
        warn("Cancelado por el usuario.")
        sys.exit(130)
    except Exception as e:
        print()
        msg = str(e)
        # Append API response body for HTTP errors so we can diagnose 400s
        import requests as _req
        if isinstance(e, _req.exceptions.HTTPError) and hasattr(e, 'response') and e.response is not None:
            try:
                body = e.response.json()
                detail = body.get('message') or body.get('errorCode') or str(body)
            except Exception:
                detail = e.response.text[:400]
            if detail:
                msg = f"{msg}\n    API: {detail}"
        err(msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
