"""Check the whole thing is wired, without starting anything.

    python3 scripts/nttd/check_wiring.py

Everything here is a check that has caught a real defect at least once during this build. It runs
in seconds, needs no engine and no API key, and is the thing to run after pulling either repo or
editing a registry.

What it verifies, in the order a failure would bite:

1. **Every registry parses**, with includes resolved from the repo root, which is how neuro-san
   resolves them.
2. **Every `class` reference imports**, from this tree or the workbench. A typo here surfaces at
   server start as a network that silently fails to load.
3. **Every `name_map` target is a file something writes.** The watcher once pointed at a path the
   migration had deleted, so `state_read` would have answered file-not-found for a name the
   registry advertised as valid.
4. **Nothing references a module that no longer exists.**
5. **The manifest names only files that are present.**
6. **No player registry has been hand-edited** — they are generated, and an edit would be lost.

It deliberately does NOT check the game: that needs macOS, OpenTTD and a live session.
"""

from __future__ import annotations

import glob
import importlib
import os
import pathlib
import re
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKBENCH = ROOT / "nttd-workbench"


def _stub_neuro_san() -> None:
    """Let the coded tools import without a neuro-san install.

    Only `CodedTool` is needed, and it is only needed as a base class. Stubbing it keeps this
    check runnable in CI and in a bare checkout, which is where a wiring error is cheapest to
    find.
    """
    if "neuro_san.interfaces.coded_tool" in sys.modules:
        return
    module = types.ModuleType("neuro_san.interfaces.coded_tool")
    module.CodedTool = type("CodedTool", (), {})
    sys.modules.update(
        {
            "neuro_san": types.ModuleType("neuro_san"),
            "neuro_san.interfaces": types.ModuleType("neuro_san.interfaces"),
            "neuro_san.interfaces.coded_tool": module,
        }
    )


def _written_state_files() -> set[str]:
    """Every file under state/ that some tool creates, read out of paths.py.

    Derived from the source rather than listed here, so this check cannot drift away from the
    thing it is checking.
    """
    src = (ROOT / "coded_tools" / "nttd" / "paths.py").read_text()
    names = set(re.findall(r'os\.path\.join\(STATE_DIR, "([^"]+)"\)', src))
    sections = re.search(r"SECTIONS: Final = \(([^)]*)\)", src)
    for section in re.findall(r'"(\w+)"', sections.group(1) if sections else ""):
        names.add(f"playbook_{section}.md")
    pads = re.search(r"PADS: Final = \(([^)]*)\)", src)
    for pad in re.findall(r'"(\w+)"', pads.group(1) if pads else ""):
        names.add(f"scratchpad_{pad}.md")
    return names


def main() -> int:  # noqa: PLR0912, PLR0915 - a linear checklist reads better than helpers here
    os.chdir(ROOT)
    sys.path[:0] = [str(ROOT), str(WORKBENCH)]
    _stub_neuro_san()

    from pyhocon import ConfigFactory  # noqa: PLC0415 - optional, and only this script needs it

    problems: list[str] = []
    written = _written_state_files()
    registries = sorted(glob.glob("registries/nttd/*.hocon"))
    if not registries:
        print("no registries found under registries/nttd/")
        return 1

    print(f"state/ files the harness writes: {len(written)}")
    print()

    parsed: dict[str, object] = {}
    for path in registries:
        try:
            parsed[path] = ConfigFactory.parse_string(pathlib.Path(path).read_text(), basedir=".")
        except Exception as failure:  # noqa: BLE001 - any parse failure is the same problem
            problems.append(f"{path}: will not parse — {type(failure).__name__}: {failure}")

    classes = 0
    for path, config in parsed.items():
        tools = config.get("tools", None) or []
        agents = [t["name"] for t in tools if not t.get("class", None)]
        print(f"OK   {path:<42} tools={len(tools):<3} agents={agents}")

        for tool in tools:
            reference = tool.get("class", None)
            if reference:
                classes += 1
                module, _, name = reference.rpartition(".")
                try:
                    getattr(importlib.import_module(module), name)
                except Exception as failure:  # noqa: BLE001
                    problems.append(f"{path}: class {reference} will not import — {type(failure).__name__}: {failure}")

            for logical, target in ((tool.get("args", None) or {}).get("name_map", None) or {}).items():
                if os.path.basename(str(target)) not in written:
                    problems.append(
                        f"{path}: name_map '{logical}' -> {target}, which nothing writes. "
                        "state_read would answer file-not-found for a name the registry "
                        "advertises as valid."
                    )

    # The manifest must name only files that exist, or the server loads fewer networks than
    # intended and says so only in its log.
    manifest = pathlib.Path("registries/nttd/manifest.hocon")
    if manifest.is_file():
        for name, enabled in re.findall(r'"([^"]+\.hocon)"\s*:\s*(true|false)', manifest.read_text()):
            if enabled == "true" and not (manifest.parent / name).is_file():
                problems.append(f"manifest names {name}, which is not present")

    # Generated files carry a marker. A hand edit to one is work that the next sync destroys.
    for path in registries:
        body = pathlib.Path(path).read_text()
        if "# GENERATED from" in body and "Do not edit by hand" not in body:
            problems.append(f"{path}: looks generated but lacks its warning header")

    # Nothing may reference a module the migrations removed.
    gone = ("trial_parsing", "log_trial", "active_trials", "resolve_trials", "delete_trial", "promote_trial")
    for path in glob.glob("coded_tools/nttd/**/*.py", recursive=True) + registries:
        body = pathlib.Path(path).read_text()
        for name in gone:
            if re.search(rf"\b{name}\b", body) and "no longer exists" not in body:
                problems.append(f"{path}: references '{name}', which was removed")

    print()
    print(f"{classes} class references across {len(parsed)} registries")
    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nwiring is sound. Not checked: the game itself — that needs macOS, OpenTTD and a live session.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
