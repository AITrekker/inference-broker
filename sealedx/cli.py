"""sealedx CLI. The CLI never renders prompt bytes by default."""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional

import typer

from sealedx.broker import runtime
from sealedx.broker.errors import SealedxError
from sealedx.grants import manager as grants_mgr
from sealedx.packaging import builder as pkg_builder
from sealedx.packaging import registry as pkg_registry
from sealedx.receipts.verifier import verify_receipt
from sealedx.security.redaction import get_logger

app = typer.Typer(
    add_completion=False,
    help="sealedx — delegated private AI workflow execution.",
    pretty_exceptions_show_locals=False,
)
vendor_app = typer.Typer(help="Vendor-side commands.")
customer_app = typer.Typer(help="Customer-side commands.")
broker_app = typer.Typer(help="Broker-side commands.")
package_app = typer.Typer(help="Inspect local packages.")
grant_app = typer.Typer(help="Inspect local grants.")
receipt_app = typer.Typer(help="Receipt commands.")

app.add_typer(vendor_app, name="vendor")
app.add_typer(customer_app, name="customer")
app.add_typer(broker_app, name="broker")
app.add_typer(package_app, name="package")
app.add_typer(grant_app, name="grant")
app.add_typer(receipt_app, name="receipt")

log = get_logger("cli")


@app.callback()
def _global_opts(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable INFO-level logs."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output."),
    unsafe_debug_prompt: bool = typer.Option(
        False,
        "--unsafe-debug-prompt",
        help="DANGER: log full prompt body. Never use in production. Will log to stderr.",
    ),
) -> None:
    if verbose:
        os.environ["SEALEDX_LOG_LEVEL"] = "INFO"
    if quiet:
        os.environ["SEALEDX_LOG_LEVEL"] = "ERROR"
    if unsafe_debug_prompt:
        os.environ["SEALEDX_UNSAFE_DEBUG_PROMPT"] = "1"
        os.environ["SEALEDX_LOG_LEVEL"] = "DEBUG"
        typer.echo(
            "WARNING: --unsafe-debug-prompt enabled. Prompt bytes will be logged.",
            err=True,
        )


def _print_json(obj: dict) -> None:
    typer.echo(json.dumps(obj, indent=2, sort_keys=True, default=str))


# -----------------------------------------------------------------------------
# vendor
# -----------------------------------------------------------------------------


@vendor_app.command("package")
def vendor_package(
    name: str = typer.Option(..., "--name"),
    prompt: Path = typer.Option(..., "--prompt", exists=True, dir_okay=False),
    input_schema: Path = typer.Option(..., "--input-schema", exists=True, dir_okay=False),
    output_schema: Path = typer.Option(..., "--output-schema", exists=True, dir_okay=False),
    version: str = typer.Option("0.1.0", "--version"),
    publisher: Optional[str] = typer.Option(None, "--publisher"),
    license: Optional[str] = typer.Option(None, "--license"),
    require_provider: Optional[str] = typer.Option(None, "--require-provider"),
    require_models: Optional[str] = typer.Option(
        None,
        "--require-models",
        help="Comma-separated list of model IDs the package requires.",
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Package a workflow. Prompt bytes are NOT printed; only their hash."""
    required_models = [m.strip() for m in require_models.split(",")] if require_models else None
    pkg = pkg_builder.package(
        name=name,
        version=version,
        prompt_path=prompt,
        input_schema_path=input_schema,
        output_schema_path=output_schema,
        publisher=publisher,
        license=license,
        required_provider=require_provider,
        required_models=required_models,
    )
    if json_out:
        _print_json(pkg.to_public_dict())
    else:
        typer.echo(f"Packaged: {pkg.name} v{pkg.version}")
        typer.echo(f"  package_id : {pkg.package_id}")
        typer.echo(f"  prompt     : {pkg.prompt_hash}")
        typer.echo(f"  input.json : {pkg.input_schema_hash}")
        typer.echo(f"  output.json: {pkg.output_schema_hash}")


# -----------------------------------------------------------------------------
# customer
# -----------------------------------------------------------------------------


@customer_app.command("grant")
def customer_grant(
    provider: str = typer.Option(..., "--provider"),
    model: str = typer.Option(..., "--model"),
    budget_usd: float = typer.Option(..., "--budget-usd"),
    expires_in: str = typer.Option(..., "--expires-in", help="e.g. 1h, 30m, 2d"),
    allow_models: Optional[str] = typer.Option(None, "--allow-models"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Issue a bounded execution grant. Provider credentials stay in the env."""
    allowed = [m.strip() for m in allow_models.split(",")] if allow_models else None
    grant = grants_mgr.create_grant(
        provider=provider,
        model=model,
        budget_usd=Decimal(str(budget_usd)),
        expires_in=expires_in,
        allowed_models=allowed,
    )
    if json_out:
        _print_json(grant.model_dump(mode="json"))
    else:
        typer.echo(f"Grant: {grant.grant_id}")
        typer.echo(f"  provider  : {grant.provider}")
        typer.echo(f"  model     : {grant.model}")
        typer.echo(f"  budget    : ${grant.budget_usd}")
        typer.echo(f"  expires   : {grant.expires_at.isoformat()}")


# -----------------------------------------------------------------------------
# broker
# -----------------------------------------------------------------------------


@broker_app.command("execute")
def broker_execute(
    package_id: str = typer.Option(..., "--package-id"),
    grant_id: str = typer.Option(..., "--grant-id"),
    input: Path = typer.Option(..., "--input", exists=True, dir_okay=False),
    out: Optional[Path] = typer.Option(None, "--out", help="Optional explicit output path."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Execute a package against a grant with a given input. Always emits a signed receipt."""
    input_obj = json.loads(input.read_text(encoding="utf-8"))
    try:
        result = runtime.execute(package_id=package_id, grant_id=grant_id, input=input_obj)
    except SealedxError as e:
        typer.echo(f"error[{e.code}]: {e.message}", err=True)
        raise typer.Exit(code=2) from None

    if out is not None:
        out.write_text(
            json.dumps(result.output, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    if json_out:
        _print_json(
            {
                "receipt": result.receipt.model_dump(mode="json"),
                "output": result.output,
                "receipt_path": result.receipt_path,
                "result_path": result.result_path,
            }
        )
        return

    typer.echo(f"Execution {result.receipt.execution_id}: {result.receipt.status}")
    typer.echo(f"  receipt : {result.receipt_path}")
    typer.echo(f"  result  : {result.result_path}")
    typer.echo(f"  tokens  : in={result.receipt.tokens_in} out={result.receipt.tokens_out}")
    typer.echo(f"  cost    : ${result.receipt.estimated_cost_usd}")


# -----------------------------------------------------------------------------
# package
# -----------------------------------------------------------------------------


@package_app.command("show")
def package_show(package_id: str, json_out: bool = typer.Option(False, "--json")) -> None:
    """Show package metadata. Never prints the prompt body."""
    pkg = pkg_registry.load_package(package_id)
    if json_out:
        _print_json(pkg.to_public_dict())
        return
    typer.echo(f"{pkg.name} v{pkg.version} ({pkg.package_id})")
    typer.echo(f"  publisher          : {pkg.publisher}")
    typer.echo(f"  license            : {pkg.license}")
    typer.echo(f"  prompt_hash        : {pkg.prompt_hash}")
    typer.echo(f"  input_schema_hash  : {pkg.input_schema_hash}")
    typer.echo(f"  output_schema_hash : {pkg.output_schema_hash}")
    typer.echo(f"  required_provider  : {pkg.required_provider}")
    typer.echo(f"  required_models    : {pkg.required_models}")


@package_app.command("list")
def package_list() -> None:
    pkgs = pkg_registry.list_packages()
    for p in pkgs:
        typer.echo(f"{p.package_id}  {p.name} v{p.version}  {p.created_at.isoformat()}")


# -----------------------------------------------------------------------------
# grant
# -----------------------------------------------------------------------------


@grant_app.command("show")
def grant_show(grant_id: str, json_out: bool = typer.Option(False, "--json")) -> None:
    g = grants_mgr.load_grant(grant_id)
    if json_out:
        _print_json(g.model_dump(mode="json"))
        return
    typer.echo(f"{g.grant_id}")
    typer.echo(f"  provider : {g.provider}")
    typer.echo(f"  model    : {g.model}")
    typer.echo(f"  budget   : ${g.budget_usd}")
    typer.echo(f"  spent    : ${g.spent_usd}")
    typer.echo(f"  expires  : {g.expires_at.isoformat()}")
    typer.echo(f"  status   : {g.derived_status().value}")


@grant_app.command("list")
def grant_list() -> None:
    for g in grants_mgr.list_grants():
        typer.echo(
            f"{g.grant_id}  {g.provider}/{g.model}  "
            f"${g.spent_usd}/${g.budget_usd}  {g.derived_status().value}"
        )


@grant_app.command("revoke")
def grant_revoke(grant_id: str) -> None:
    g = grants_mgr.revoke(grant_id)
    typer.echo(f"revoked: {g.grant_id}")


# -----------------------------------------------------------------------------
# receipt
# -----------------------------------------------------------------------------


@receipt_app.command("verify")
def receipt_verify(receipt_path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    result = verify_receipt(receipt_path)
    typer.echo(result.summary())
    if not result.ok:
        raise typer.Exit(code=1)


@receipt_app.command("show")
def receipt_show(receipt_path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    typer.echo(receipt_path.read_text(encoding="utf-8"))


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
