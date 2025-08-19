#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import argparse
import shutil

def restore_one(prev_path: str, keep_instrumented: bool, dry_run: bool):
    if not prev_path.endswith('_prev.cc'):
        return False

    orig_path = prev_path[:-8] + '.cc'   # strip "_prev.cc" -> ".cc"

    if not os.path.exists(prev_path):
        print(f"[skip] not found: {prev_path}")
        return False

    if dry_run:
        print(f"[dry-run] restore {prev_path} -> {orig_path}")
        return True

    # If the original exists and we want to keep it, rename it to .inst (instrumented)
    if os.path.exists(orig_path) and keep_instrumented:
        inst_path = orig_path + '.inst'
        # Avoid clobbering an existing .inst file
        n = 1
        candidate = inst_path
        while os.path.exists(candidate):
            candidate = f"{inst_path}.{n}"
            n += 1
        os.rename(orig_path, candidate)
        print(f"[kept] {orig_path} -> {candidate}")

    # Move/overwrite backup to original
    shutil.move(prev_path, orig_path)
    print(f"[restored] {prev_path} -> {orig_path}")
    return True


def main():
    ap = argparse.ArgumentParser(description="Restore *_prev.cc backups back to .cc")
    ap.add_argument("directory", help="Root directory to search")
    ap.add_argument("--keep-instrumented", action="store_true",
                    help="If original .cc exists, keep it by renaming to .inst (instead of overwriting)")
    ap.add_argument("--dry-run", action="store_true", help="Print actions without changing files")
    args = ap.parse_args()

    restored = 0
    for root, dirs, files in os.walk(args.directory):
        for fn in files:
            if fn.endswith('_prev.cc'):
                path = os.path.join(root, fn)
                if restore_one(path, args.keep_instrumented, args.dry_run):
                    restored += 1
    print(f"[done] restored {restored} file(s).")


if __name__ == "__main__":
    main()

