"""Module that contains the command line app."""
import warnings

import click
import numpy as np
import toml
from pathlib import Path
import importlib
import hmf
from hmf.helpers.functional import get_hmf
from .helpers.cfg_utils import framework_to_dict
from rich.console import Console
from rich.panel import Panel
from rich import box
from rich.rule import Rule
from time import time
from astropy.units import Quantity

console = Console(width=100)


def _get_config(config=None):
    if config is None:
        return {}

    with open(config, "r") as fl:
        cfg = toml.load(fl)

    # Import an actual framework.
    fmwk = cfg.get("framework", None)
    if fmwk:
        mod, cls = fmwk.rsplit(".", maxsplit=1)

        cfg["framework"] = getattr(importlib.import_module(mod), cls)

    return cfg


def _ctx_to_dct(args):
    dct = {}
    j = 0
    while j < len(args):
        arg = args[j]
        if "=" in arg:
            a = arg.split("=")
            k = a[0].replace("--", "")
            v = a[-1]
            j += 1
        else:
            k = arg.replace("--", "")
            v = args[j + 1]
            j += 2

        try:
            # For most arguments, this will convert it to the right type.
            v = eval(v)
        except NameError:
            # If it's supposed to be a string, but quotes weren't supplied.
            v = eval('"' + v + '"')

        dct[k] = v

    return dct


def _process_dct(dct):
    out = {}
    for k, v in dct.items():
        if isinstance(v, dict):
            if set(v.keys()) == {"unit", "value"}:
                v = Quantity(v["value"], v["unit"])
            else:
                v = _process_dct(v)

        out[k] = v

    return out


main = click.Group()


@main.command(
    context_settings={  # Doing this allows arbitrary options to override config
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    }
)
@click.option(
    "-i", "--config", type=click.Path(exists=True, dir_okay=False), default=None,
)
@click.option(
    "-o",
    "--outdir",
    type=click.Path(exists=True, dir_okay=True, file_okay=True),
    default=".",
)
@click.option(
    "-l", "--label", type=str, default="hmf",
)
@click.pass_context
def run(ctx, config, outdir, label):
    """Calculate quantities using hmf and output to a file.

    Parameters
    ----------
    ctx :
        A parameter from the parent CLI function to be able to override config.
    config : str
        Path to the configuration file.
    """
    console.print(
        Panel("Welcome to hmf!", box=box.DOUBLE_EDGE), style="bold", justify="center"
    )
    console.print()
    console.print(f"Using hmf version [blue]{hmf.__version__}[/blue]", style="strong")

    cfg = _get_config(config)

    # Update the file-based config with options given on the CLI.
    if ctx.args:
        if "params" not in cfg:
            cfg["params"] = {}

        cfg["params"].update(_ctx_to_dct(ctx.args))

    cfg["params"] = _process_dct(cfg["params"])

    console.print(f"Explicitly set parameters: {cfg.get('params', {})}", style="bold")

    quantities = cfg.get("quantities", ["m", "dndm"])
    out = get_hmf(
        quantities,
        framework=cfg.get("framework", hmf.MassFunction),
        get_label=True,
        label_kind="filename",
        **cfg.get("params", {}),
    )

    outdir = Path(outdir)

    console.print()
    console.print("Quantities to be obtained: ", style="bold")
    for q in quantities:
        console.print(f"  - {q}", style="dim grey53")
    console.print()

    console.print(Rule("Starting Calculations", style="grey53"))
    t = time()

    for quants, obj, lab in out:
        lab = lab or label

        console.print(f"Calculated {lab}:", style="bold", end="")
        console.print(
            f"[[{time() - t:.2f} sec]]", style="blue", justify="right", width=100
        )
        t = time()

        # Write out quantities
        for qname, q in zip(quantities, quants):
            np.savetxt(outdir / f"{lab}_{qname}.txt", q)

        console.print(
            f"   Writing quantities to [cyan]{outdir}/{lab}_<quantity>.txt[/cyan]."
        )

        # Write out parameters
        dct = framework_to_dict(obj)
        dct["quantities"] = quantities
        with open(outdir / f"{lab}_cfg.toml", "w") as fl:
            toml.dump(dct, fl, encoder=toml.TomlNumpyEncoder())

        console.print(
            f"   Writing explicit config to [cyan]{outdir}/{lab}_cfg.toml[/cyan]."
        )
        console.print()

    console.print(Rule("Finished!", style="grey53"), style="bold green")