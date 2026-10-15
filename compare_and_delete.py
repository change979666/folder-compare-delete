from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Literal


@dataclass(frozen=True)
class PlanItem:
    relative_path: Path
    src_path: Path
    dst_path: Path
    kind: Literal["file", "dir"]
    action: Literal["delete", "move", "copy"]


@dataclass(frozen=True)
class ExecResult:
    ok: int
    failed: int
    errors: tuple[str, ...]


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _iter_root_items(root: Path) -> Iterable[Path]:
    yield from root.iterdir()


def _iter_relative_files(root: Path) -> Iterable[Path]:
    for dirpath, _dirnames, filenames in os.walk(root):
        dirpath_p = Path(dirpath)
        for filename in filenames:
            yield (dirpath_p / filename).relative_to(root)


def _iter_relative_dirs(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, _filenames in os.walk(root):
        dirpath_p = Path(dirpath)
        for dirname in dirnames:
            yield (dirpath_p / dirname).relative_to(root)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _delete_path(path: Path) -> None:
    """Force delete with retry and attribute removal."""
    def _remove_readonly(func, path_str, _exc_info):
        """Error handler to remove read-only and retry."""
        os.chmod(path_str, stat.S_IWRITE)
        func(path_str)
    
    # Try up to 3 times with short delays
    for attempt in range(3):
        try:
            if path.is_dir() and not path.is_symlink():
                # Remove read-only attributes recursively
                for root, dirs, files in os.walk(path):
                    for d in dirs:
                        try:
                            os.chmod(os.path.join(root, d), stat.S_IWRITE)
                        except Exception:
                            pass
                    for f in files:
                        try:
                            os.chmod(os.path.join(root, f), stat.S_IWRITE)
                        except Exception:
                            pass
                shutil.rmtree(path, onerror=_remove_readonly)
            else:
                # Remove read-only for file
                try:
                    os.chmod(path, stat.S_IWRITE)
                except Exception:
                    pass
                path.unlink(missing_ok=False)
            return  # Success
        except PermissionError:
            if attempt < 2:
                time.sleep(0.5)  # Wait 500ms and retry
                continue
            raise  # Give up after 3 attempts
        except Exception:
            raise


def _ensure_safe_pair(dir_a: Path, dir_b: Path) -> None:
    # Prevent nested directories which can cause confusing results.
    if _is_under(dir_b, dir_a):
        raise ValueError("副目录在主目录内部，会导致误删/混淆；请换一个副目录。")
    if _is_under(dir_a, dir_b):
        raise ValueError("主目录在副目录内部，会导致误删/混淆；请换一个主目录。")


def validate_dir_pair(main_dir: Path, sub_dir: Path) -> None:
    if not main_dir.exists() or not main_dir.is_dir():
        raise ValueError(f"主目录不存在或不是文件夹: {main_dir}")
    if not sub_dir.exists() or not sub_dir.is_dir():
        raise ValueError(f"副目录不存在或不是文件夹: {sub_dir}")
    _ensure_safe_pair(main_dir, sub_dir)


CompareMode = Literal["name", "structure", "deep-name"]


def _kind_of(path: Path) -> Literal["file", "dir"]:
    return "dir" if path.is_dir() and not path.is_symlink() else "file"


def _plan_delete(
    main_dir: Path,
    sub_dir: Path,
    mode: CompareMode,
    include_dirs: bool,
) -> list[PlanItem]:
    plan: list[PlanItem] = []

    if mode == "name":
        for item in _iter_root_items(main_dir):
            rel = Path(item.name)
            target = sub_dir / rel
            if not target.exists():
                continue
            kind = _kind_of(target)
            if kind == "dir" and not include_dirs:
                continue
            plan.append(
                PlanItem(
                    rel,
                    src_path=target,
                    dst_path=target,
                    kind=kind,
                    action="delete",
                )
            )
        return plan

    if mode == "deep-name":
        # Collect all names from main_dir at any depth
        main_names: set[str] = set()
        for dirpath, dirnames, filenames in os.walk(main_dir):
            for dirname in dirnames:
                main_names.add(dirname)
            for filename in filenames:
                main_names.add(filename)
        
        # Find and delete matching names in sub_dir at any depth
        for dirpath, dirnames, filenames in os.walk(sub_dir, topdown=False):
            dirpath_p = Path(dirpath)
            
            # Check files
            for filename in filenames:
                if filename in main_names:
                    full_path = dirpath_p / filename
                    rel = full_path.relative_to(sub_dir)
                    plan.append(
                        PlanItem(
                            rel,
                            src_path=full_path,
                            dst_path=full_path,
                            kind="file",
                            action="delete",
                        )
                    )
            
            # Check dirs if include_dirs is True
            if include_dirs:
                for dirname in dirnames:
                    if dirname in main_names:
                        full_path = dirpath_p / dirname
                        rel = full_path.relative_to(sub_dir)
                        plan.append(
                            PlanItem(
                                rel,
                                src_path=full_path,
                                dst_path=full_path,
                                kind="dir",
                                action="delete",
                            )
                        )
        
        return plan

    # structure mode: delete matching relative files; dirs are optional.
    rel_files = set(_iter_relative_files(main_dir))
    for rel in sorted(rel_files):
        target = sub_dir / rel
        if target.exists():
            plan.append(
                PlanItem(
                    rel,
                    src_path=target,
                    dst_path=target,
                    kind="file",
                    action="delete",
                )
            )

    if include_dirs:
        rel_dirs = set(_iter_relative_dirs(main_dir))
        # Delete deeper dirs first so parent deletion doesn't fail.
        sorted_dirs = sorted(
            rel_dirs,
            key=lambda p: (len(p.parts), str(p)),
            reverse=True,
        )
        for rel in sorted_dirs:
            target = sub_dir / rel
            if target.exists() and target.is_dir():
                plan.append(
                    PlanItem(
                        rel,
                        src_path=target,
                        dst_path=target,
                        kind="dir",
                        action="delete",
                    )
                )

    return plan


def plan_delete(
    main_dir: Path,
    sub_dir: Path,
    mode: CompareMode = "name",
    include_dirs: bool = False,
) -> list[PlanItem]:
    """Create a deletion plan.

    Remove items from sub_dir that exist in main_dir.

    mode:
      - name: compare only direct children names under main_dir
      - structure: compare relative file paths; dirs optional via
        include_dirs
      - deep-name: recursively collect all names from main_dir at any
        depth, delete matching names in sub_dir at any depth
    """
    validate_dir_pair(main_dir, sub_dir)
    return _plan_delete(
        main_dir=main_dir,
        sub_dir=sub_dir,
        mode=mode,
        include_dirs=include_dirs,
    )


def _plan_migrate(
    src_root: Path,
    dst_root: Path,
    mode: CompareMode,
    action: Literal["move", "copy"],
    migrate_all: bool = False,
) -> list[PlanItem]:
    plan: list[PlanItem] = []

    if mode == "name":
        for item in _iter_root_items(src_root):
            rel = Path(item.name)
            dst = dst_root / rel
            if not migrate_all and dst.exists():
                continue
            kind = _kind_of(item)
            plan.append(
                PlanItem(
                    rel,
                    src_path=item,
                    dst_path=dst,
                    kind=kind,
                    action=action,
                )
            )
        return plan

    # structure mode: migrate missing files only, by relative path.
    for rel in sorted(set(_iter_relative_files(src_root))):
        src = src_root / rel
        dst = dst_root / rel
        if not migrate_all and dst.exists():
            continue
        plan.append(
            PlanItem(
                rel,
                src_path=src,
                dst_path=dst,
                kind="file",
                action=action,
            )
        )

    return plan


def plan_migrate(
    main_dir: Path,
    sub_dir: Path,
    direction: Literal["main-to-sub", "sub-to-main"],
    mode: CompareMode = "name",
    op: Literal["move", "copy"] = "move",
    migrate_all: bool = False,
) -> tuple[Path, Path, list[PlanItem]]:
    """Create a migration plan.

    - direction: main-to-sub or sub-to-main
    - mode name: only direct children; migrate items missing in destination
    - mode structure: migrate missing files by relative path
    - migrate_all: if True, migrate all items regardless of existence
    """
    validate_dir_pair(main_dir, sub_dir)
    src_root = main_dir if direction == "main-to-sub" else sub_dir
    dst_root = sub_dir if direction == "main-to-sub" else main_dir
    _ensure_safe_pair(src_root, dst_root)
    plan = _plan_migrate(
        src_root=src_root,
        dst_root=dst_root,
        mode=mode,
        action=op,
        migrate_all=migrate_all,
    )
    return src_root, dst_root, plan


def execute_plan(
    plan: list[PlanItem],
    *,
    overwrite: bool = False,
    remove_empty_dirs_root: Path | None = None,
    clean_source_empty_dirs_root: Path | None = None,
    on_progress: callable | None = None,
) -> ExecResult:
    """Execute a plan without any interactive prompts.

    on_progress: optional callback (done:int, total:int, item:PlanItem)
    """
    ok = 0
    failed = 0
    errors: list[str] = []
    total = len(plan)

    for idx, item in enumerate(plan, start=1):
        try:
            if item.action == "delete":
                _delete_path(item.src_path)
            elif item.action == "move":
                if item.dst_path.exists():
                    if not overwrite:
                        # Skip if target exists and overwrite not enabled
                        ok += 1
                        if on_progress:
                            try:
                                on_progress(idx, total, item)
                            except Exception:
                                pass
                        continue
                    _delete_path(item.dst_path)
                item.dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item.src_path), str(item.dst_path))
            elif item.action == "copy":
                if item.dst_path.exists():
                    if not overwrite:
                        # Skip if target exists and overwrite not enabled
                        ok += 1
                        if on_progress:
                            try:
                                on_progress(idx, total, item)
                            except Exception:
                                pass
                        continue
                    _delete_path(item.dst_path)
                item.dst_path.parent.mkdir(parents=True, exist_ok=True)
                if item.kind == "dir":
                    shutil.copytree(item.src_path, item.dst_path)
                else:
                    shutil.copy2(item.src_path, item.dst_path)
            else:
                raise RuntimeError(f"未知 action: {item.action}")

            ok += 1
        except PermissionError as e:
            failed += 1
            err_msg = (
                f"{item.action} {item.kind} {item.src_path} -> "
                f"权限错误/文件被占用 (请关闭相关程序后重试): {e}"
            )
            errors.append(err_msg)
        except Exception as e:
            failed += 1
            errors.append(f"{item.action} {item.kind} {item.src_path} -> {e}")

        if on_progress:
            try:
                on_progress(idx, total, item)
            except Exception:
                pass

    if remove_empty_dirs_root and remove_empty_dirs_root.exists():
        _remove_empty_dirs(remove_empty_dirs_root)
    if clean_source_empty_dirs_root and clean_source_empty_dirs_root.exists():
        _remove_empty_dirs(clean_source_empty_dirs_root)

    return ExecResult(ok=ok, failed=failed, errors=tuple(errors))


def _remove_empty_dirs(root: Path) -> int:
    removed = 0
    # bottom-up
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if dirnames or filenames:
            continue
        p = Path(dirpath)
        if p == root:
            continue
        try:
            p.rmdir()
            removed += 1
        except OSError:
            pass
    return removed


def _confirm_or_exit(prompt: str, yes: bool) -> bool:
    if yes:
        return True
    confirm = input(prompt)
    return confirm == "YES"


def _write_log_header(fp, header: str) -> None:
    fp.write(f"[{_now_stamp()}] {header}\n")


def _execute_plan(
    plan: list[PlanItem],
    dry_run: bool,
    yes: bool,
    remove_empty_dirs: bool,
    log_path: str,
    overwrite: bool,
    clean_source_empty_dirs: bool,
    remove_empty_root: Path | None = None,
    clean_source_root: Path | None = None,
) -> int:
    if not plan:
        print("未发现需要处理的项。")
        return 0

    # Logging
    log_fp = None
    if log_path:
        p = Path(log_path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        log_fp = p.open("a", encoding="utf-8")

    def _log(line: str) -> None:
        if log_fp:
            log_fp.write(line + "\n")

    print(f"匹配到 {len(plan)} 个将要处理的项：")
    for item in plan:
        if item.action == "delete":
            print(f"- [delete {item.kind}] {item.src_path}")
        else:
            print(
                f"- [{item.action} {item.kind}] {item.src_path}"
                f" -> {item.dst_path}"
            )
        _log(
            f"PLAN {item.action} {item.kind} rel={item.relative_path} "
            f"src={item.src_path} dst={item.dst_path}"
        )

    if dry_run:
        print("dry-run：未执行实际操作。")
        _log("DRY_RUN no operation executed")
        if log_fp:
            _write_log_header(log_fp, "END")
            log_fp.close()
        return 0

    if not _confirm_or_exit("确认执行以上操作吗？输入 YES 继续： ", yes=yes):
        print("已取消。")
        _log("CANCELLED by user")
        if log_fp:
            _write_log_header(log_fp, "END")
            log_fp.close()
        return 1

    ok = 0
    failed = 0

    for item in plan:
        try:
            if item.action == "delete":
                _delete_path(item.src_path)
            elif item.action == "move":
                if item.dst_path.exists() and overwrite:
                    _delete_path(item.dst_path)
                item.dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item.src_path), str(item.dst_path))
            elif item.action == "copy":
                if item.dst_path.exists() and overwrite:
                    _delete_path(item.dst_path)
                item.dst_path.parent.mkdir(parents=True, exist_ok=True)
                if item.kind == "dir":
                    shutil.copytree(item.src_path, item.dst_path)
                else:
                    shutil.copy2(item.src_path, item.dst_path)
            else:
                raise RuntimeError(f"未知 action: {item.action}")

            ok += 1
            _log(
                f"OK {item.action} {item.kind} rel={item.relative_path} "
                f"src={item.src_path} dst={item.dst_path}"
            )
        except Exception as e:
            failed += 1
            print(f"ERROR: 处理失败: {item.src_path} -> {e}", file=sys.stderr)
            _log(
                f"FAIL {item.action} {item.kind} rel={item.relative_path} "
                f"src={item.src_path} dst={item.dst_path} err={e}"
            )

    if remove_empty_dirs and remove_empty_root:
        if remove_empty_root.exists():
            removed_dirs = _remove_empty_dirs(remove_empty_root)
            print(f"清理空目录: {removed_dirs} 个")
            _log(f"CLEAN empty_dirs={removed_dirs} root={remove_empty_root}")

    if clean_source_empty_dirs and clean_source_root:
        if clean_source_root.exists():
            removed_dirs = _remove_empty_dirs(clean_source_root)
            print(f"清理源空目录: {removed_dirs} 个")
            _log(
                f"CLEAN source_empty_dirs={removed_dirs} "
                f"root={clean_source_root}"
            )

    print(f"完成：成功 {ok} 个，失败 {failed} 个")
    _log(f"DONE ok={ok} failed={failed}")

    if log_fp:
        _write_log_header(log_fp, "END")
        log_fp.close()

    return 0 if failed == 0 else 3


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "批量对比/删除/迁移工具\n"
            "- delete：删除副目录中与主目录重复的内容\n"
            "- migrate：在主/副目录之间迁移（默认移动）\n\n"
            "对比模式：\n"
            "- name：只比较根目录下一层的同名文件/文件夹\n"
            "- structure：按相对路径比较整个目录结构（默认只处理文件）"
        )
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    delete_p = subparsers.add_parser("delete", help="删除副目录中与主目录重复的项")
    delete_p.add_argument("main_dir", help="主目录路径")
    delete_p.add_argument("sub_dir", help="副目录路径（将被删除内容）")
    delete_p.add_argument(
        "--mode",
        choices=["name", "structure", "deep-name"],
        default="name",
        help="对比模式：name(同名) / structure(目录结构) / deep-name(深度同名)",
    )
    delete_p.add_argument(
        "--include-dirs",
        action="store_true",
        help=(
            "也删除目录（name 模式下常用；structure 模式下谨慎使用，可能会删除目录内额外文件）"
        ),
    )
    delete_p.add_argument("--dry-run", action="store_true", help="只打印，不实际删除")
    delete_p.add_argument("--yes", action="store_true", help="跳过二次确认（危险）")
    delete_p.add_argument(
        "--remove-empty-dirs",
        action="store_true",
        help="删除后清理副目录内空文件夹",
    )
    delete_p.add_argument("--log", default="", help="写入日志文件路径（可选）")

    mig_p = subparsers.add_parser("migrate", help="在主/副目录之间迁移（移动或复制）")
    mig_p.add_argument("main_dir", help="主目录路径")
    mig_p.add_argument("sub_dir", help="副目录路径")
    mig_p.add_argument(
        "--direction",
        choices=["main-to-sub", "sub-to-main"],
        required=True,
        help="迁移方向：main-to-sub 或 sub-to-main",
    )
    mig_p.add_argument(
        "--mode",
        choices=["name", "structure"],
        default="name",
        help="对比模式：name(只看第一层同名) / structure(按相对路径全结构，只迁移缺失文件)",
    )
    mig_p.add_argument(
        "--copy",
        action="store_true",
        help="复制而不是移动（默认是移动=迁移）",
    )
    mig_p.add_argument(
        "--overwrite",
        action="store_true",
        help="目标存在同名/同路径时覆盖（默认跳过）",
    )
    mig_p.add_argument("--dry-run", action="store_true", help="只打印，不实际迁移")
    mig_p.add_argument("--yes", action="store_true", help="跳过二次确认（危险）")
    mig_p.add_argument(
        "--clean-source-empty-dirs",
        action="store_true",
        help="迁移后清理源目录内空文件夹（结构模式移动文件时常用）",
    )
    mig_p.add_argument("--log", default="", help="写入日志文件路径（可选）")

    args = parser.parse_args(argv)

    main_dir = Path(args.main_dir).expanduser()
    sub_dir = Path(args.sub_dir).expanduser()

    if not main_dir.exists() or not main_dir.is_dir():
        print(f"ERROR: 主目录不存在或不是文件夹: {main_dir}", file=sys.stderr)
        return 2
    if not sub_dir.exists() or not sub_dir.is_dir():
        print(f"ERROR: 副目录不存在或不是文件夹: {sub_dir}", file=sys.stderr)
        return 2

    try:
        _ensure_safe_pair(main_dir, sub_dir)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.command == "delete":
        mode: CompareMode = args.mode
        plan = _plan_delete(
            main_dir=main_dir,
            sub_dir=sub_dir,
            mode=mode,
            include_dirs=bool(args.include_dirs),
        )
        if args.log:
            with Path(args.log).expanduser().open("a", encoding="utf-8") as fp:
                _write_log_header(
                    fp,
                    f"START delete main={main_dir} sub={sub_dir} mode={mode}",
                )

        print(f"主目录: {main_dir}")
        print(f"副目录: {sub_dir}")
        print(f"模式: {mode}")
        return _execute_plan(
            plan=plan,
            dry_run=bool(args.dry_run),
            yes=bool(args.yes),
            remove_empty_dirs=bool(args.remove_empty_dirs),
            log_path=str(args.log),
            overwrite=False,
            clean_source_empty_dirs=False,
            remove_empty_root=sub_dir if args.remove_empty_dirs else None,
            clean_source_root=None,
        )

    if args.command == "migrate":
        mode = args.mode
        src_root = main_dir if args.direction == "main-to-sub" else sub_dir
        dst_root = sub_dir if args.direction == "main-to-sub" else main_dir
        op: Literal["move", "copy"] = "copy" if args.copy else "move"

        # safety for chosen direction too
        try:
            _ensure_safe_pair(src_root, dst_root)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2

        plan = _plan_migrate(
            src_root=src_root,
            dst_root=dst_root,
            mode=mode,
            action=op,
            migrate_all=False,
        )

        if args.log:
            with Path(args.log).expanduser().open("a", encoding="utf-8") as fp:
                _write_log_header(
                    fp,
                    (
                        f"START migrate direction={args.direction} "
                        f"src={src_root} dst={dst_root} mode={mode} op={op}"
                    ),
                )

        print(f"源目录: {src_root}")
        print(f"目标目录: {dst_root}")
        print(f"方向: {args.direction}")
        print(f"模式: {mode}")
        print(f"操作: {op}")

        return _execute_plan(
            plan=plan,
            dry_run=bool(args.dry_run),
            yes=bool(args.yes),
            remove_empty_dirs=False,
            log_path=str(args.log),
            overwrite=bool(args.overwrite),
            clean_source_empty_dirs=bool(args.clean_source_empty_dirs),
            remove_empty_root=None,
            clean_source_root=(
                src_root if args.clean_source_empty_dirs else None
            ),
        )

    print("ERROR: 未知命令", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
