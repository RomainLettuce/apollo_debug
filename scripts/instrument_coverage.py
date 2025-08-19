#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import shutil
import argparse

INCLUDE_LINE = '#include "modules/common/instrumentation_logger/instrumentation_collector.h"\n'
BUILD_DEPS_LINE = '        "//modules/common/instrumentation_logger:instrumentation_collector",\n'

BRANCH_MACRO_TMPL = 'INSTR_BRANCH_HIT((std::string(__FILE__) + "_{num}").c_str());\n'


# ------------------- Utility helpers -------------------

def strip_line_comments(s: str, in_block: bool):
    i = 0
    out = []
    n = len(s)
    while i < n:
        if in_block:
            end = s.find('*/', i)
            if end == -1:
                return ''.join(out), True
            i = end + 2
            in_block = False
            continue
        if i + 1 < n and s[i] == '/' and s[i+1] == '*':
            in_block = True
            i += 2
            continue
        if i + 1 < n and s[i] == '/' and s[i+1] == '/':
            break
        out.append(s[i])
        i += 1
    return ''.join(out), in_block


def is_blank_or_comment(line: str, in_block: bool):
    code, nb = strip_line_comments(line, in_block)
    return (code.strip() == ''), nb


def leading_ws(s: str):
    return s[:len(s) - len(s.lstrip())]


# ------------------- Include insertion -------------------

def insert_include_once(file_path: str):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if any(INCLUDE_LINE.strip() == ln.strip() for ln in lines):
        return False

    insert_idx = 0
    for i, ln in enumerate(lines):
        code, _ = strip_line_comments(ln, False)
        if re.match(r'^\s*#\s*include\b', code):
            insert_idx = i + 1

    lines.insert(insert_idx, INCLUDE_LINE)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    return True


# ------------------- BUILD deps -------------------

def insert_build_dep(build_path: str):
    with open(build_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    do_not_insert = False
    in_deps = False
    targets_to_patch_endidx = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if stripped.startswith('name ='):
            name = stripped
            if ('_test' in name) or name.endswith('_factory') or \
               ('dp_st_cost' in name) or ('gridded_path_time_graph' in name) or \
               ('st_graph_point' in name):
                do_not_insert = True
        if stripped.startswith('deps = ['):
            if do_not_insert:
                do_not_insert = False
            else:
                in_deps = True
                continue
        if in_deps:
            if ']' in stripped:
                targets_to_patch_endidx.append(i)
                in_deps = False

    for idx in reversed(targets_to_patch_endidx):
        start = idx
        while start >= 0 and 'deps = [' not in lines[start]:
            start -= 1
        if start >= 0:
            block_text = ''.join(lines[start:idx+1])
            if 'instrumentation_collector' not in block_text:
                lines.insert(idx, BUILD_DEPS_LINE)

    with open(build_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)


# ------------------- Instrumentation core -------------------

def instrument_file(file_path: str, backup: bool):
    """
    Simplest version:
    - For every 'case ...:' or 'default:' label, insert macro right after it.
    - For 'if/else if/else', insert after the opening '{'.
    - Optional backup to *_prev.cc
    """
    import re, shutil

    MACRO = 'INSTR_BRANCH_HIT((std::string(__FILE__) + "_{num}").c_str());\n'
    branch_id = 1

    # -------- optional backup --------
    if backup and file_path.endswith('.cc'):
        shutil.copy2(file_path, file_path[:-3] + '_prev.cc')

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    def leading_ws(s: str): return s[:len(s) - len(s.lstrip())]

    # Regexes
    case_re = re.compile(r'^\s*case\b')
    def_re  = re.compile(r'^\s*default\s*:')

    # ---------- PASS 1: case/default ----------
    new = []
    for raw in lines:
        new.append(raw)
        code = raw.split('//')[0]  # ignore inline comment
        if case_re.match(code) or def_re.match(code):
            indent = leading_ws(raw)
            new.append(indent + MACRO.format(num=branch_id))
            branch_id += 1
    lines = new

    # ---------- PASS 2: if / else ----------
    new = []
    ctrl_re = re.compile(r'^\s*(?:}\s*)*(?:else\s+if\b|if\b|else\b(?!\s*if))')
    i = 0
    while i < len(lines):
        raw = lines[i]
        code = raw.split('//')[0]
        m = ctrl_re.match(code)
        if m:
            pos = raw.find('{', m.end())
            if pos != -1:  # same line has '{'
                before = raw[:pos+1]
                after  = raw[pos+1:]
                new.append(before if before.endswith('\n') else before + '\n')
                new.append(leading_ws(raw) + MACRO.format(num=branch_id))
                branch_id += 1
                if after:
                    new.append(after)
                i += 1
                continue
            # multi-line: look ahead until '{'
            j = i+1
            found = -1
            while j < len(lines):
                if '{' in lines[j]:
                    found = j; break
                j += 1
            if found != -1:
                for k in range(i, found):
                    new.append(lines[k])
                raw2 = lines[found]
                pos = raw2.find('{')
                before = raw2[:pos+1]
                after  = raw2[pos+1:]
                new.append(before if before.endswith('\n') else before + '\n')
                new.append(leading_ws(raw2) + MACRO.format(num=branch_id))
                branch_id += 1
                if after:
                    new.append(after)
                i = found+1
                continue
        new.append(raw)
        i += 1

    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(new)



# ------------------- Main -------------------

def main():
    parser = argparse.ArgumentParser(description="Auto-instrument C++ sources for branch coverage.")
    parser.add_argument("directory", help="Root directory to walk")
    parser.add_argument("--instrument", action="store_true", help="Instrument .cc files")
    parser.add_argument("--build", action="store_true", help="Patch BUILD deps")
    parser.add_argument("--include", action="store_true", help="Insert include lines")
    parser.add_argument("--backup", action="store_true", help="Backup .cc files to *_prev.cc before modifying")
    args = parser.parse_args()

    exclude_dirs = ["common", "park", "yield_sign", "narrow", "dead_end", "open_space", "learning_model", "utils"]
    exclude_files = ["dp_st_cost", "st_graph_point", "gridded_path_time_graph"]

    for root, dirs, files in os.walk(args.directory):
        dirs[:] = [d for d in dirs if not any(ex in d for ex in exclude_dirs)]
        for file_name in files:
            if any(ex in file_name for ex in exclude_files):
                continue
            path = os.path.join(root, file_name)
            if file_name == "BUILD" and args.build:
                insert_build_dep(path)
            elif file_name.endswith(".cc") and not file_name.endswith("test.cc"):
                if args.instrument:
                    instrument_file(path, args.backup)
                if args.include:
                    insert_include_once(path)


if __name__ == "__main__":
    main()
