"""astromeshctl eval — run `kind: Eval` files with core's eval runner (`astromesh-eval`)."""

import typer


def eval_command(
    config_dir: str = typer.Argument(..., help="Config tree with the agents under test"),
    files: list[str] | None = typer.Argument(  # noqa: B008
        None, help="*.eval.yaml files (default: <config_dir>/evals/*.eval.yaml)"
    ),
    out: str | None = typer.Option(None, "--out", help="Write the JSON report here"),
) -> None:
    """Run agent evals locally. Exit 0 all pass, 1 below threshold, 2 load error."""
    from astromesh.evals.__main__ import main

    argv = [config_dir, *(files or [])] + (["--out", out] if out else [])
    raise typer.Exit(code=main(argv))
