"""Read paths from Codex apply_patch input without applying any of its edits."""
from __future__ import annotations


class PatchError(ValueError):
    pass


_HEADERS = ("*** Add File: ", "*** Update File: ", "*** Delete File: ")
_MOVE = "*** Move to: "


def patch_paths(command: object) -> list[str]:
    """Include both sides of a move; content lines always carry their diff prefix.

    This is a path reader, not a second patch engine. The runtime validates hunks.
    Refuse unrecognized framing or directives rather than omit a possible path.
    """
    if not isinstance(command, str):
        raise PatchError("apply_patch input must contain a string command")
    lines = [line.removesuffix("\r") for line in command.strip().split("\n")]
    if len(lines) < 3 or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        raise PatchError("cannot read apply_patch framing")
    paths = []
    can_move = False
    in_update = False
    for line in lines[1:-1]:
        # The runtime trims headers between files, but a space-prefixed marker
        # inside an Update is context. Deny ambiguous headers outside an Update.
        if not in_update and line != line.lstrip() and line.lstrip().startswith("*** "):
            raise PatchError("apply_patch file directives must not be indented")
        header = next((prefix for prefix in _HEADERS if line.startswith(prefix)), None)
        if header is not None:
            path = line[len(header):].rstrip()
            in_update = header == "*** Update File: "
            can_move = in_update
        elif line.startswith(_MOVE) and can_move:
            path = line[len(_MOVE):].rstrip()
            can_move = False
        else:
            can_move = False
            if line == "*** End of File":
                in_update = False
            if not paths or (line.startswith("*** ") and line != "*** End of File"):
                raise PatchError("cannot read apply_patch file directives")
            continue
        if not path.strip():
            raise PatchError("apply_patch file path is empty")
        paths.append(path)
    if not paths:
        raise PatchError("apply_patch contains no file paths")
    return paths
