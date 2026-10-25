"""Línea de comandos de Eidos. Pensada para CI y para el desarrollador."""
from __future__ import annotations

import argparse
import json
import sys

from .catalog import Catalog
from .config import settings
from .contracts import (
    ArtifactRecord,
    CommandSpec,
    CompiledSpec,
    EntitySpec,
    Finding,
    Intervention,
    Requirement,
    Route,
    RuleSpec,
    ViewSpec,
)
from .llm import LLMError
from .reconciler import BuildError, list_apps, render_markdown
from .service import Platform
from .specs import compile_spec, load_bundle


def _print_findings(findings: list[Finding]) -> None:
    for f in findings:
        print(f"  [{f.severity.value:9}] {f.code:22} {f.message}" + (f"  ({f.path})" if f.path else ""))


def cmd_validate(args: argparse.Namespace) -> int:
    from .reconciler import app_dir
    bundle, f0 = load_bundle(app_dir(args.app))
    print(f"G0 · Admisión de {args.app}: {'OK' if bundle else 'FALLA'}")
    _print_findings(f0)
    if not bundle:
        return 1
    spec, f1 = compile_spec(bundle)
    print(f"G1 · Compilación: {'OK' if spec else 'FALLA'}" + (f" · versión {spec.version}" if spec else ""))
    _print_findings(f1)
    return 0 if spec else 1


def cmd_build(args: argparse.Namespace) -> int:
    pf = Platform()
    apps = list_apps() if args.app == "all" else [args.app]
    code = 0
    for app in apps:
        try:
            report = pf.reconciler().run(app, Route(args.mode), actor="cli")
        except BuildError as e:
            print(f"✗ {app}: {e}")
            _print_findings(e.findings)
            code = 1
            continue
        print(render_markdown(report) if args.verbose else
              f"✓ {app} · versión {report['version']} ({report['spec_status']}) · {len(report['changes'])} cambio(s) · "
              f"{len(report['interventions'])} intervención(es) abierta(s)")
        if any(s["blocking"] for s in report["screens"].values()):
            code = 1
    return code


def cmd_interventions(args: argparse.Namespace) -> int:
    pf = Platform()
    if args.action == "list":
        for i in pf.store.interventions(args.app, "abierta"):
            print(f"#{i.id} {i.type.value} · {i.app} · {i.artifact} · {i.role}: {i.reason}")
        return 0
    if args.id == "all":
        ids = [i.id for i in pf.store.interventions(args.app, "abierta") if i.type.value in ("H1", "H4")]
    else:
        ids = [int(args.id)]
    for iid in ids:
        result = pf.reconciler().resolve(int(iid), args.action == "approve", args.motive or "", actor="cli")
        print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_schemas(args: argparse.Namespace) -> int:
    out = settings().contracts_dir
    out.mkdir(parents=True, exist_ok=True)
    docs = {
        "screen-document": Catalog().screen_schema(),
        "compiled-spec": CompiledSpec.model_json_schema(),
        "entity": EntitySpec.model_json_schema(), "view": ViewSpec.model_json_schema(), "command": CommandSpec.model_json_schema(),
        "rule": RuleSpec.model_json_schema(), "requirement": Requirement.model_json_schema(),
        "artifact": ArtifactRecord.model_json_schema(), "finding": Finding.model_json_schema(), "intervention": Intervention.model_json_schema(),
    }
    for name, schema in docs.items():
        (out / f"{name}.schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(docs)} esquemas en {out}")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    from .llm import profiles
    pf = Platform()
    if args.action == "use":
        pf.set_profile(args.id, actor="cli")
    if args.action == "test":
        print(json.dumps(pf.test_profile(args.id or pf.profile.id), ensure_ascii=False))
        return 0
    active = pf.profile.id
    for p in profiles().values():
        print(f"{'*' if p.id == active else ' '} {p.id:6} {p.label:40} {'configurado' if p.configured else 'sin configurar'}{' · externo' if p.external else ''}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api import create_app
    s = settings()
    uvicorn.run(create_app(), host=args.host or s.host, port=args.port or s.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="eidos", description="Plataforma Eidos")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="G0 + G1 de una aplicación")
    v.add_argument("app")
    v.set_defaults(fn=cmd_validate)
    b = sub.add_parser("build", help="Reconcilia una aplicación (o all)")
    b.add_argument("app")
    b.add_argument("--mode", default="lote", choices=[r.value for r in Route if r != Route.MANUAL])
    b.add_argument("-v", "--verbose", action="store_true", help="Imprime el informe de conformidad")
    b.set_defaults(fn=cmd_build)
    i = sub.add_parser("interventions", help="Lista o resuelve intervenciones")
    i.add_argument("action", choices=["list", "approve", "reject"])
    i.add_argument("id", nargs="?", default="all")
    i.add_argument("--app")
    i.add_argument("--motive", default="")
    i.set_defaults(fn=cmd_interventions)
    s = sub.add_parser("schemas", help="Exporta los contratos a JSON Schema")
    s.set_defaults(fn=cmd_schemas)
    pr = sub.add_parser("profile", help="Perfiles de modelo: list, use ID, test [ID]")
    pr.add_argument("action", choices=["list", "use", "test"], nargs="?", default="list")
    pr.add_argument("id", nargs="?")
    pr.set_defaults(fn=cmd_profile)
    sv = sub.add_parser("serve", help="Arranca la API y el cliente")
    sv.add_argument("--host")
    sv.add_argument("--port", type=int)
    sv.set_defaults(fn=cmd_serve)
    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (FileNotFoundError, ValueError) as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    except LLMError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
