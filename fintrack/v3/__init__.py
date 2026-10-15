"""v3 (14 Oct 2026): the whole app as one website. The extra parts the website needs live here, one module each
(sign-in, backups, Fix an item, ...). Each module has register(app); setup(app) calls every one that exists."""
import importlib

PARTS = ("auth", "passkey", "backup", "fixitem", "billswap", "live", "ideas")


def setup(app) -> None:
    for name in PARTS:
        try:
            mod = importlib.import_module(f"fintrack.v3.{name}")
        except ModuleNotFoundError as e:
            if e.name != f"fintrack.v3.{name}":
                raise
            continue
        mod.register(app)
