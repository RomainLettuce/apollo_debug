#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Instrument Apollo planning sources for branch coverage.

    scripts/instrument_coverage.py            # instrument the default scope
    scripts/instrument_coverage.py --clean    # put the tree back the way it was

For every ``if`` / ``else if`` / ``else`` / ``case`` / ``default`` block in
scope the tool injects

    INSTR_BRANCH_HIT("B<id>");

as the first statement of the block, adds the collector include to the source
and the collector dep to the Bazel target that builds it -- all in one pass.

Each id is recorded in ``branch_id_map.json`` along with the file, the line of
the branch in the *original* source, and the condition text it guards (the
"operand"), so a dumped frame can be mapped back to real code:

    "B417": {
      "file": "modules/planning/traffic_rules/crosswalk.cc",
      "line": 132,
      "local_id": 18,
      "type": "else_if",
      "operand": "obstacle->IsVirtual()"
    }

Ids already assigned to other files are never reshuffled, so a partial re-run
keeps previously collected traces readable.

The edits this tool makes are build artifacts and are not meant to be
committed: instrument, build, run, then ``--clean``.
"""

import os
import re
import json
import argparse
from collections import defaultdict, namedtuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INCLUDE_PATH = "modules/common/instrumentation_logger/instrumentation_collector.h"
INCLUDE_LINE = '#include "%s"\n' % INCLUDE_PATH
BUILD_DEP = "//modules/common/instrumentation_logger:instrumentation_collector"

DEFAULT_MAP_PATH = "modules/common/instrumentation_logger/branch_id_map.json"

MACRO_TMPL = 'INSTR_BRANCH_HIT("B{gid}");'

# A macro line from this tool, or from the pre-"B<n>" scheme that used
# __FILE__.  Matching both keeps re-runs idempotent on an older tree.
MACRO_RE = re.compile(
    r'^\s*INSTR_BRANCH_HIT\(\s*'
    r'(?:"B\d+"|\(std::string\(__FILE__\)\s*\+\s*"_\d+"\)\.c_str\(\))'
    r'\s*\);\s*$')

# What gets instrumented when no path is given on the command line.  The two
# planning/common sources and on_lane_planning.cc are named one by one because
# the directory walk skips "common" wholesale and never descends into the
# planning root.
DEFAULT_TARGETS = [
    "modules/planning/on_lane_planning.cc",
    "modules/planning/common/obstacle.cc",
    "modules/planning/common/obstacle_blocking_analyzer.cc",
    "modules/planning/scenarios",
    "modules/planning/tasks",
    "modules/planning/traffic_rules",
]

# Directory names are matched as substrings, so "narrow" also drops
# scenarios/narrow_street_u_turn.  Note this only prunes the walk: a file
# named after an excluded directory (traffic_rules/yield_sign.cc) still
# gets instrumented.
EXCLUDE_DIRS = ["common", "park", "yield_sign", "narrow", "dead_end",
                "open_space", "learning_model", "utils"]
EXCLUDE_FILES = ["dp_st_cost", "st_graph_point", "gridded_path_time_graph"]
# *_prev.cc / *_backup.cc are this tool's own leftovers; never treat them as
# sources or they get instrumented too and burn branch ids.
EXCLUDE_SUFFIXES = ["test.cc", "_prev.cc", "_backup.cc"]


# ----------------------------------------------------------------- utilities

def leading_ws(s):
    return s[:len(s) - len(s.lstrip())]


def read_lines(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.readlines()


def write_lines(path, lines):
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)


def mask_line(line, in_block, mask_strings):
    """Blank out comments (and optionally string literals) in `line`.

    Characters are replaced one for one so column numbers stay valid.  Returns
    the masked text and the block-comment state for the next line.
    """
    out = list(line)
    n = len(line)
    i = 0
    while i < n:
        c = line[i]
        if in_block:
            if c == '*' and i + 1 < n and line[i + 1] == '/':
                out[i] = out[i + 1] = ' '
                i += 2
                in_block = False
                continue
            if c != '\n':
                out[i] = ' '
            i += 1
            continue
        if c == '/' and i + 1 < n and line[i + 1] == '*':
            out[i] = out[i + 1] = ' '
            i += 2
            in_block = True
            continue
        if c == '/' and i + 1 < n and line[i + 1] == '/':
            for j in range(i, n):
                if line[j] != '\n':
                    out[j] = ' '
            break
        if c in '"\'':
            quote = c
            if mask_strings:
                out[i] = ' '
            i += 1
            while i < n:
                if line[i] == '\\':
                    if mask_strings:
                        out[i] = ' '
                        if i + 1 < n:
                            out[i + 1] = ' '
                    i += 2
                    continue
                if line[i] == quote:
                    if mask_strings:
                        out[i] = ' '
                    i += 1
                    break
                if mask_strings and line[i] != '\n':
                    out[i] = ' '
                i += 1
            continue
        i += 1
    return ''.join(out), in_block


def mask_all(lines, mask_strings):
    masked = []
    state = False
    for ln in lines:
        m, state = mask_line(ln, state, mask_strings)
        masked.append(m)
    return masked


# ------------------------------------------------------------- branch id map

def load_map(map_path):
    if os.path.exists(map_path):
        with open(map_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_map(map_path, mapping):
    out_dir = os.path.dirname(map_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(map_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write('\n')


def next_global_id(mapping):
    max_n = -1
    for k in mapping:
        if k.startswith('B'):
            try:
                max_n = max(max_n, int(k[1:]))
            except ValueError:
                pass
    return max_n + 1


def purge_file_entries(mapping, rel_file):
    for k in [k for k, v in mapping.items() if v.get('file') == rel_file]:
        del mapping[k]


def assign_ids(mapping, rel_file, sites):
    """Give every site in `rel_file` a global id, reusing the one it already
    had wherever the branch is unchanged.

    Re-instrumenting a file it has already seen is therefore a no-op on the
    map, and traces collected earlier stay readable.  A branch that moved,
    changed condition, or is new gets a fresh id; ids belonging to other
    files are never reshuffled.
    """
    old = {v['local_id']: (k, v) for k, v in mapping.items()
           if v.get('file') == rel_file}
    # Seeded before the purge so a freshly minted id can never collide with
    # one of this file's own ids that is about to be reused.
    gid = next_global_id(mapping)
    purge_file_entries(mapping, rel_file)

    ids = []
    for n, site in enumerate(sites):
        local_id = n + 1
        entry = {
            'file': rel_file,
            'line': site.src_line,
            'local_id': local_id,
            'type': site.kind,
            'operand': site.operand,
        }
        previous = old.get(local_id)
        if previous and previous[1].get('type') == site.kind \
                and previous[1].get('operand') == site.operand:
            bid = previous[0]
        else:
            bid = 'B%d' % gid
            gid += 1
        mapping[bid] = entry
        ids.append(int(bid[1:]))
    return ids


# ------------------------------------------------------------ branch scanner

Site = namedtuple('Site', 'line col indent kind operand src_line')

CASE_RE = re.compile(r'^\s*case\s+(.+?)(?<!:):(?!:)')
DEFAULT_RE = re.compile(r'^\s*default\s*:')
# Optional leading '}' so "} else {" is seen.  "else if" must win over "if".
CTRL_RE = re.compile(r'^\s*(?:\}\s*)*(else\s+if|if|else)\b')


def _first_brace(masked, i, j):
    """Position of '{' if it is the next significant character, else None."""
    while i < len(masked):
        line = masked[i]
        while j < len(line):
            c = line[j]
            if c.isspace():
                j += 1
                continue
            return (i, j) if c == '{' else None
        i += 1
        j = 0
    return None


def _span_text(lines, l0, c0, l1, c1):
    """Raw text between two positions, folded onto one line.

    Wrapped lines are joined with a space, except where that would break up a
    member access -- `dead_end_info()\\n.type()` reads back as one expression.
    """
    if l0 == l1:
        parts = [lines[l0][c0:c1]]
    else:
        parts = [lines[l0][c0:]] + lines[l0 + 1:l1] + [lines[l1][:c1]]

    text = ''
    for part in parts:
        part = ' '.join(part.split())
        if not part:
            continue
        if text and text[-1] not in '([' and not (
                part[0] in '.,)]' or part.startswith('->')):
            text += ' '
        text += part
    return text or None


def scan_control(lines, masked, i, j, has_cond):
    """Walk a control statement from just past its keyword.

    Returns (brace_line, brace_col, operand), or None when the body is a
    single brace-less statement -- those are left alone rather than guessed
    at, which is what made the previous version attach a macro to whatever
    block happened to come next.
    """
    if not has_cond:
        pos = _first_brace(masked, i, j)
        return None if pos is None else (pos[0], pos[1], None)

    depth = 0
    start = None
    while i < len(masked):
        line = masked[i]
        while j < len(line):
            c = line[j]
            if c == '(':
                if depth == 0:
                    start = (i, j)
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    operand = _span_text(lines, start[0], start[1] + 1, i, j)
                    pos = _first_brace(masked, i, j + 1)
                    return None if pos is None else (pos[0], pos[1], operand)
            elif depth == 0 and c == ';':
                return None       # `if (...)` never opened; malformed input
            j += 1
        i += 1
        j = 0
    return None


def body_indent(lines, base_line, from_line, from_col):
    """Indent to give the macro: whatever the block's first statement uses."""
    base = leading_ws(lines[base_line].rstrip('\n'))
    if from_col is not None and lines[from_line][from_col + 1:].strip():
        return base + '  '        # code trails the '{' on the same line
    for k in range(from_line + 1, len(lines)):
        if lines[k].strip():
            indent = leading_ws(lines[k])
            return indent if len(indent) > len(base) else base + '  '
    return base + '  '


def classify(keyword):
    keyword = ' '.join(keyword.split())
    if keyword.startswith('else if'):
        return 'else_if'
    return 'if' if keyword == 'if' else 'else'


def find_sites(lines):
    """All branch sites in `lines` ordered by position, plus the masked view
    of the source they were found in (the renderer needs it too)."""
    masked = mask_all(lines, mask_strings=True)     # structure
    nostr = mask_all(lines, mask_strings=False)     # operand text
    sites = []

    for idx, code in enumerate(masked):
        m = CASE_RE.match(code)
        if m:
            operand = ' '.join(CASE_RE.match(nostr[idx]).group(1).split())
            sites.append(Site(idx, len(lines[idx].rstrip('\n')),
                              body_indent(lines, idx, idx, None),
                              'case', operand or None, idx + 1))
            continue
        if DEFAULT_RE.match(code):
            sites.append(Site(idx, len(lines[idx].rstrip('\n')),
                              body_indent(lines, idx, idx, None),
                              'default', None, idx + 1))
            continue

        m = CTRL_RE.match(code)
        if not m:
            continue
        kind = classify(m.group(1))
        found = scan_control(lines, masked, idx, m.end(), kind != 'else')
        if found is None:
            continue
        bline, bcol, operand = found
        sites.append(Site(bline, bcol + 1,
                          body_indent(lines, idx, bline, bcol),
                          kind, operand, idx + 1))

    sites.sort(key=lambda s: (s.line, s.col))
    return sites, masked


def render(lines, masked, sites, macro_for):
    """Splice a macro line into each site, keeping the rest byte for byte.

    Whatever trails the '{' has to go somewhere.  Real code moves down to its
    own line, but a trailing comment stays on the line it annotates -- moving
    those is what turned `} else {  // has change lane` into a two-line mess.
    """
    by_line = defaultdict(list)
    for s in sites:
        by_line[s.line].append(s)

    out = []
    for idx, raw in enumerate(lines):
        entries = by_line.get(idx)
        if not entries:
            out.append(raw)
            continue

        nl = raw.endswith('\n')
        body = raw[:-1] if nl else raw
        prev, indent, brace_at = 0, '', 0

        for s in entries:
            segment = body[prev:s.col]
            if prev == 0:
                out.append(segment + '\n')
                brace_at = len(out) - 1
            elif segment.strip():
                if masked[idx][prev:s.col].strip():
                    out.append(indent + segment.strip() + '\n')
                    brace_at = len(out) - 1
                else:
                    out[brace_at] = out[brace_at].rstrip('\n') + segment.rstrip() + '\n'
            out.append(s.indent + macro_for(s) + '\n')
            prev, indent = s.col, s.indent

        tail = body[prev:]
        if tail.strip():
            if masked[idx][prev:].strip():
                out.append(indent + tail.strip() + '\n')
            else:
                out[brace_at] = out[brace_at].rstrip('\n') + tail.rstrip() + '\n'
        if not nl:
            out[-1] = out[-1].rstrip('\n')
    return out


# ------------------------------------------------------------------ stripping

def uses_instrumentation(lines):
    """True if the file hand-rolls a collector call, so the include has to
    stay even after the generated macros are gone -- on_lane_planning.cc and
    planning_component.cc drive the frame counter themselves.

    DUMP_* does not count: those come from dumper.h, a separate header.
    """
    return any('INSTR_' in ln and INCLUDE_PATH not in ln for ln in lines)


def strip_macros(lines):
    """Drop generated macro lines, plus the blank line the old version left
    behind them, so a re-run always starts from the pristine source."""
    out = []
    for idx, ln in enumerate(lines):
        if MACRO_RE.match(ln):
            continue
        if (not ln.strip() and out and out[-1].rstrip().endswith(('{', ':'))
                and idx > 0 and MACRO_RE.match(lines[idx - 1])):
            continue
        out.append(ln)
    return out


def strip_include(lines):
    return [ln for ln in lines if ln.strip() != INCLUDE_LINE.strip()]


def pristine(lines):
    """The source as it is in git: no macros, and no include unless the file
    hand-rolls instrumentation of its own (on_lane_planning.cc does)."""
    base = strip_macros(lines)
    return base if uses_instrumentation(base) else strip_include(base)


def insert_include(lines):
    if any(ln.strip() == INCLUDE_LINE.strip() for ln in lines):
        return lines, False
    at = 0
    state = False
    for i, ln in enumerate(lines):
        code, state = mask_line(ln, state, True)
        if re.match(r'^\s*#\s*include\b', code):
            at = i + 1
    return lines[:at] + [INCLUDE_LINE] + lines[at:], True


# ---------------------------------------------------------------- BUILD files

RULE_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*$')
ATTR_LIST_RE = re.compile(r'^\s*(\w+)\s*=\s*\[')
ENTRY_RE = re.compile(r'^\s*"[^"]+",\s*$')


def iter_rules(lines):
    """Yield (kind, start, end) for each top-level rule call."""
    i = 0
    while i < len(lines):
        m = RULE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not lines[j].startswith(')'):
            j += 1
        yield m.group(1), i, min(j, len(lines) - 1)
        i = j + 1


def attr_list(lines, start, end, name):
    """(first, last) line indices of a `name = [ ... ]` attribute block."""
    for i in range(start, end):
        m = ATTR_LIST_RE.match(lines[i])
        if not m or m.group(1) != name:
            continue
        if ']' in lines[i][m.end():]:
            return i, i
        for j in range(i + 1, end + 1):
            if lines[j].strip().startswith(']'):
                return i, j
        return i, end
    return None


def rule_srcs(lines, start, end):
    span = attr_list(lines, start, end, 'srcs')
    if span is None:
        return []
    text = ''.join(lines[span[0]:span[1] + 1])
    return re.findall(r'"([^"]+\.(?:cc|h))"', text)


def rule_needs_dep(build_dir, srcs):
    """Whether a target builds an instrumented source.

    Returns None when that cannot be decided -- no srcs attribute, a glob, or
    a file outside this package -- in which case the dep is left exactly as
    it is rather than guessed at.
    """
    readable = False
    for src in srcs:
        path = os.path.join(build_dir, src)
        if not src.endswith('.cc'):
            continue
        if not os.path.isfile(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read()
        except (OSError, UnicodeDecodeError):
            return None
        readable = True
        if 'INSTR_' in text:
            return True
    return False if readable else None


def add_dep(lines, start, end):
    """Insert the collector dep in sorted position; return the new lines."""
    span = attr_list(lines, start, end, 'deps')
    label = '"%s",' % BUILD_DEP

    if span is None:
        indent = '    '
        return (lines[:end]
                + [indent + 'deps = [\n',
                   indent * 2 + label + '\n',
                   indent + '],\n']
                + lines[end:])

    first, last = span
    if any(BUILD_DEP in ln for ln in lines[first:last + 1]):
        return lines
    if first == last:               # deps = [] or a one-line list
        head, sep, tail = lines[first].partition(']')
        inner = head[head.index('[') + 1:].strip()
        prefix = head[:head.index('[') + 1]
        joined = (inner + ' ' if inner and not inner.endswith(',') else inner)
        return (lines[:first]
                + [prefix + joined + label[:-1] + sep + tail]
                + lines[first + 1:])

    entries = [i for i in range(first + 1, last) if ENTRY_RE.match(lines[i])]
    indent = leading_ws(lines[entries[0]]) if entries else '        '
    at = last
    for i in entries:
        if lines[i].strip() > label:
            at = i
            break
    return lines[:at] + [indent + label + '\n'] + lines[at:]


def drop_dep(lines, start, end):
    span = attr_list(lines, start, end, 'deps')
    if span is None:
        return lines
    first, last = span
    if first == last:
        if BUILD_DEP not in lines[first]:
            return lines
        cleaned = re.sub(r'\s*"%s",?' % re.escape(BUILD_DEP), '', lines[first])
        return lines[:first] + [cleaned] + lines[first + 1:]
    keep = [i for i in range(first, last + 1)
            if not (i > first and lines[i].strip() == '"%s",' % BUILD_DEP)]
    return lines[:first] + [lines[i] for i in keep] + lines[last + 1:]


def patch_build(build_path, remove, dry_run=False):
    """Add or drop the collector dep on every target that builds an
    instrumented source.  Returns the number of targets touched.

    Instrumenting only ever adds.  Deps are dropped under --clean alone, and
    only from targets whose sources demonstrably stopped using the collector,
    so a hand-written dep (planning_component, on_lane_planning) survives.
    """
    lines = read_lines(build_path)
    build_dir = os.path.dirname(build_path)
    touched = 0

    # Rules are rewritten back to front so earlier spans stay valid.
    for kind, start, end in reversed(list(iter_rules(lines))):
        if not kind.startswith('cc_'):
            continue
        wants = rule_needs_dep(build_dir, rule_srcs(lines, start, end))
        if wants is None:
            continue
        has = any(BUILD_DEP in ln for ln in lines[start:end + 1])
        before = lines
        if remove:
            if has and not wants:
                lines = drop_dep(lines, start, end)
        elif wants and not has:
            lines = add_dep(lines, start, end)
        if lines != before:
            touched += 1

    if touched and not dry_run:
        write_lines(build_path, lines)
    return touched


# ------------------------------------------------------------------ per file

class Stats(object):
    def __init__(self):
        self.files = 0
        self.branches = 0
        self.includes = 0
        self.targets = 0

    def report(self, mode):
        print("%s: %d file(s), %d branch(es), %d include(s), %d BUILD target(s)"
              % (mode, self.files, self.branches, self.includes, self.targets))


def instrument_file(path, rel, mapping, stats, backup, dry_run):
    lines = pristine(read_lines(path))

    if backup and path.endswith('.cc'):
        prev = path[:-3] + '_prev.cc'
        if not os.path.exists(prev):
            write_lines(prev, lines)

    sites, masked = find_sites(lines)

    # Line numbers and operands refer to the pristine source above, which is
    # what the file looks like in git -- the version a human reads.
    ids = assign_ids(mapping, rel, sites)
    order = {id(s): n for n, s in enumerate(sites)}

    out = render(lines, masked, sites,
                 lambda s: MACRO_TMPL.format(gid=ids[order[id(s)]]))
    out, added = insert_include(out)

    if not dry_run:
        write_lines(path, out)
    stats.files += 1
    stats.branches += len(sites)
    stats.includes += 1 if added else 0


def clean_file(path, rel, mapping, stats, dry_run):
    lines = read_lines(path)
    out = pristine(lines)
    if out == lines:
        return
    if not dry_run:
        write_lines(path, out)
    purge_file_entries(mapping, rel)
    stats.files += 1


# ------------------------------------------------------------- scope walking

def is_source(name):
    if not name.endswith('.cc'):
        return False
    if any(name.endswith(suffix) for suffix in EXCLUDE_SUFFIXES):
        return False
    return not any(ex in name for ex in EXCLUDE_FILES)


def collect(paths):
    """Expand the given paths into (sources, build_files), both sorted."""
    sources, builds = set(), set()
    for path in paths:
        path = path if os.path.isabs(path) else os.path.join(REPO_ROOT, path)
        if os.path.isfile(path):
            name = os.path.basename(path)
            if name == 'BUILD':
                builds.add(path)
            elif is_source(name):
                sources.add(path)
            continue
        if not os.path.isdir(path):
            print("warning: no such path: %s" % path)
            continue
        for root, dirs, files in os.walk(path):
            dirs[:] = sorted(d for d in dirs
                             if not any(ex in d for ex in EXCLUDE_DIRS))
            for name in files:
                if name == 'BUILD':
                    builds.add(os.path.join(root, name))
                elif is_source(name):
                    sources.add(os.path.join(root, name))
    return sorted(sources), sorted(builds)


def main():
    parser = argparse.ArgumentParser(
        description="Instrument Apollo planning sources for branch coverage.",
        epilog="Macros, include and BUILD deps go in together -- a macro "
               "without its include does not compile, and neither does an "
               "include without its dep. The result is a build artifact: run "
               "--clean before committing.")
    parser.add_argument("path", nargs='*',
                        help="files and/or directories to process "
                             "(default: the planning scope)")
    parser.add_argument("--clean", action="store_true",
                        help="take the instrumentation back out again")
    parser.add_argument("--backup", action="store_true",
                        help="keep a *_prev.cc copy (--clean supersedes this)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change, write nothing")
    parser.add_argument("--map", default=DEFAULT_MAP_PATH,
                        help="path to the branch id map (default: %(default)s)")
    args = parser.parse_args()

    map_path = args.map if os.path.isabs(args.map) else os.path.join(
        REPO_ROOT, args.map)
    mapping = load_map(map_path)
    sources, builds = collect(args.path or DEFAULT_TARGETS)
    stats = Stats()

    for path in sources:
        rel = os.path.relpath(path, REPO_ROOT)
        if args.clean:
            clean_file(path, rel, mapping, stats, args.dry_run)
        else:
            instrument_file(path, rel, mapping, stats, args.backup,
                            args.dry_run)

    # Which targets need the dep is read off the sources, so this has to run
    # after they have been written -- hence nothing to do under --dry-run
    # beyond counting what the current tree would give.
    for path in builds:
        stats.targets += patch_build(path, args.clean, args.dry_run)

    if not args.dry_run:
        save_map(map_path, mapping)

    stats.report("would clean" if args.clean and args.dry_run else
                 "would instrument" if args.dry_run else
                 "cleaned" if args.clean else "instrumented")


if __name__ == "__main__":
    main()
