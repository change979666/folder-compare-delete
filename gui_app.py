from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpacerItem,
    QStyleFactory,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from compare_and_delete import (
    ExecResult,
    PlanItem,
    execute_plan,
    plan_delete,
    plan_migrate,
)


@dataclass
class PreviewContext:
    plan: list[PlanItem]
    overwrite: bool
    remove_empty_dirs_root: Path | None
    clean_source_empty_dirs_root: Path | None
    summary: str


class Worker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object)

    def __init__(
        self,
        plan: list[PlanItem],
        overwrite: bool,
        remove_empty_dirs_root: Path | None,
        clean_source_empty_dirs_root: Path | None,
    ) -> None:
        super().__init__()
        self._plan = plan
        self._overwrite = overwrite
        self._remove_empty_dirs_root = remove_empty_dirs_root
        self._clean_source_empty_dirs_root = clean_source_empty_dirs_root

    def run(self) -> None:
        def on_progress(done: int, total: int, item: PlanItem) -> None:
            if item.relative_path:
                msg = f"{item.action} {item.kind}: {item.relative_path}"
            else:
                msg = str(item.src_path)
            self.progress.emit(done, total, msg)

        result: ExecResult = execute_plan(
            self._plan,
            overwrite=self._overwrite,
            remove_empty_dirs_root=self._remove_empty_dirs_root,
            clean_source_empty_dirs_root=self._clean_source_empty_dirs_root,
            on_progress=on_progress,
        )
        self.finished.emit(result)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("批量对比删除 / 迁移工具")
        self.setMinimumSize(980, 640)

        self._preview: PreviewContext | None = None
        self._thread: QThread | None = None
        self._worker: Worker | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        layout.addWidget(self._build_paths_group())
        layout.addWidget(self._build_options_group())
        layout.addWidget(self._build_actions_row())
        layout.addWidget(self._build_table())
        layout.addWidget(self._build_status_row())

        self._wire_signals()
        self._refresh_explain()
        self._refresh_enabled()

    def _build_paths_group(self) -> QWidget:
        box = QGroupBox("目录")
        v = QVBoxLayout(box)

        self.main_edit = QLineEdit()
        self.sub_edit = QLineEdit()

        v.addLayout(self._path_row("主目录", self.main_edit, self._browse_main))
        v.addLayout(self._path_row("副目录", self.sub_edit, self._browse_sub))

        return box

    def _path_row(self, label: str, edit: QLineEdit, browse_cb) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        row.addWidget(edit)
        btn = QPushButton("浏览…")
        btn.clicked.connect(browse_cb)
        row.addWidget(btn)
        return row

    def _build_options_group(self) -> QWidget:
        box = QGroupBox("功能与模式")
        v = QVBoxLayout(box)

        op_row = QHBoxLayout()
        self.rb_delete = QRadioButton("删除副目录中重复内容")
        self.rb_migrate = QRadioButton("迁移（主↔副）")
        self.rb_delete.setChecked(True)

        self.op_group = QButtonGroup(self)
        self.op_group.addButton(self.rb_delete)
        self.op_group.addButton(self.rb_migrate)

        op_row.addWidget(self.rb_delete)
        op_row.addWidget(self.rb_migrate)
        op_row.addItem(
            QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        v.addLayout(op_row)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("对比模式"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("name：只对比第一层同名", "name")
        self.mode_combo.addItem("structure：对比整个目录结构（按相对路径）", "structure")
        self.mode_combo.addItem("deep-name：深度同名（递归所有层级）", "deep-name")
        mode_row.addWidget(self.mode_combo)
        mode_row.addItem(
            QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        v.addLayout(mode_row)

        self.explain = QLabel("")
        self.explain.setWordWrap(True)
        self.explain.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.explain)

        self.delete_opts = self._build_delete_opts()
        self.migrate_opts = self._build_migrate_opts()
        v.addWidget(self.delete_opts)
        v.addWidget(self.migrate_opts)

        return box

    def _build_delete_opts(self) -> QWidget:
        box = QGroupBox("删除设置")
        row = QHBoxLayout(box)
        self.cb_delete_dirs = QCheckBox("也删除目录（同名文件夹也会删除）")
        self.cb_remove_empty = QCheckBox("删除后清理副目录空文件夹")
        self.cb_delete_dirs.setChecked(True)
        row.addWidget(self.cb_delete_dirs)
        row.addWidget(self.cb_remove_empty)
        row.addItem(
            QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        return box

    def _build_migrate_opts(self) -> QWidget:
        box = QGroupBox("迁移设置")
        v = QVBoxLayout(box)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("方向"))
        self.direction_combo = QComboBox()
        self.direction_combo.addItem("主 → 副", "main-to-sub")
        self.direction_combo.addItem("副 → 主", "sub-to-main")
        row1.addWidget(self.direction_combo)

        row1.addWidget(QLabel("方式"))
        self.op_combo = QComboBox()
        self.op_combo.addItem("移动（迁移）", "move")
        self.op_combo.addItem("复制（不删除源）", "copy")
        row1.addWidget(self.op_combo)

        row1.addItem(
            QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        v.addLayout(row1)

        row2 = QHBoxLayout()
        self.cb_overwrite = QCheckBox("目标已存在时覆盖")
        self.cb_migrate_all = QCheckBox("迁移全部（不检查是否存在）")
        self.cb_clean_source = QCheckBox("完成后清理源目录空文件夹")
        row2.addWidget(self.cb_overwrite)
        row2.addWidget(self.cb_migrate_all)
        row2.addWidget(self.cb_clean_source)
        row2.addItem(
            QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        v.addLayout(row2)

        return box

    def _build_actions_row(self) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.addItem(
            QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        self.preview_btn = QPushButton("预览结果")
        self.exec_btn = QPushButton("执行")
        row.addWidget(self.preview_btn)
        row.addWidget(self.exec_btn)
        return w

    def _build_table(self) -> QWidget:
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["动作", "类型", "相对路径", "源", "目标"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        return self.table

    def _build_status_row(self) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        self.status = QLabel("")
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.status)
        row.addItem(
            QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        return w

    def _wire_signals(self) -> None:
        self.preview_btn.clicked.connect(self._on_preview)
        self.exec_btn.clicked.connect(self._on_execute)

        for widget in [
            self.main_edit,
            self.sub_edit,
            self.rb_delete,
            self.rb_migrate,
            self.mode_combo,
            self.cb_delete_dirs,
            self.cb_remove_empty,
            self.direction_combo,
            self.op_combo,
            self.cb_overwrite,
            self.cb_migrate_all,
            self.cb_clean_source,
        ]:
            try:
                # type: ignore[attr-defined]
                widget.toggled.connect(self._on_change)
            except Exception:
                pass
            try:
                widget.currentIndexChanged.connect(
                    self._on_change
                )  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                # type: ignore[attr-defined]
                widget.textChanged.connect(self._on_change)
            except Exception:
                pass

    def _on_change(self, *_args) -> None:
        self._preview = None
        self._clear_table()
        self._refresh_explain()
        self._refresh_enabled()

    def _refresh_enabled(self) -> None:
        is_delete = self.rb_delete.isChecked()
        self.delete_opts.setVisible(is_delete)
        self.migrate_opts.setVisible(not is_delete)

        self.exec_btn.setEnabled(
            self._preview is not None and len(self._preview.plan) > 0
        )

    def _refresh_explain(self) -> None:
        mode = self.mode_combo.currentData()
        is_delete = self.rb_delete.isChecked()

        if is_delete:
            if mode == "name":
                text = (
                    "【删除-同名】只比较主目录第一层的同名项；"
                    "如果副目录存在同名文件/目录，将被删除。\n"
                    "提示：若不勾选“也删除目录”，同名文件夹不会被删。\n"
                    "建议先点“预览结果”，确认无误再执行。"
                )
            elif mode == "deep-name":
                text = (
                    "【删除-深度同名】递归遍历主目录所有层级的文件/目录名。\n"
                    "副目录中任何层级的同名项都会被删除（不管它在哪个深度）。\n"
                    "警告威力很强：只要名字相同就删，不管路径是否一致。\n"
                    "建议先点预览结果仔细确认。"
                )
            else:
                text = (
                    "【删除-结构】按相对路径对比整个目录结构。\n"
                    "默认只删除‘同相对路径的文件’（更安全）；"
                    "如勾选“也删除目录”，可能会删掉目录内多余文件，谨慎使用。"
                )
        else:
            if mode == "name":
                text = (
                    f"【迁移-同名】方向：{self.direction_combo.currentText()}，"
                    f"方式：{self.op_combo.currentText()}。\n"
                    "只处理第一层：把源目录第一层中‘目标不存在的同名项’迁移过去。\n"
                    "如果目标已存在：默认跳过；可勾选“目标已存在时覆盖”。"
                )
            else:
                text = (
                    f"【迁移-结构】方向：{self.direction_combo.currentText()}，"
                    f"方式：{self.op_combo.currentText()}。\n"
                    "按相对路径遍历源目录文件：仅迁移‘目标不存在的文件’（不会合并/覆盖目录结构）。\n"
                    "如需覆盖已有文件，请勾选\"目标已存在时覆盖\"。\n"
                    "勾选\"迁移全部\"可不检查是否存在，强制迁移所有文件。"
                )

        self.explain.setText(text)

    def _browse_main(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "选择主目录")
        if p:
            self.main_edit.setText(p)

    def _browse_sub(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "选择副目录")
        if p:
            self.sub_edit.setText(p)

    def _clear_table(self) -> None:
        self.table.setRowCount(0)
        self.status.setText("")

    def _set_table(self, plan: list[PlanItem]) -> None:
        self.table.setRowCount(len(plan))
        for row, item in enumerate(plan):
            self.table.setItem(row, 0, QTableWidgetItem(item.action))
            self.table.setItem(row, 1, QTableWidgetItem(item.kind))
            rel_text = str(item.relative_path)
            self.table.setItem(row, 2, QTableWidgetItem(rel_text))
            self.table.setItem(row, 3, QTableWidgetItem(str(item.src_path)))
            self.table.setItem(row, 4, QTableWidgetItem(str(item.dst_path)))

    def _paths(self) -> tuple[Path, Path] | None:
        main = Path(self.main_edit.text().strip())
        sub = Path(self.sub_edit.text().strip())
        if (not self.main_edit.text().strip()) or (
            not self.sub_edit.text().strip()
        ):
            QMessageBox.warning(self, "提示", "请先选择主目录和副目录。")
            return None
        return main, sub

    def _on_preview(self) -> None:
        paths = self._paths()
        if not paths:
            return
        main_dir, sub_dir = paths

        mode = self.mode_combo.currentData()

        try:
            if self.rb_delete.isChecked():
                include_dirs = self.cb_delete_dirs.isChecked()
                plan = plan_delete(
                    main_dir,
                    sub_dir,
                    mode=mode,
                    include_dirs=include_dirs,
                )
                remove_empty_root = (
                    sub_dir if self.cb_remove_empty.isChecked() else None
                )
                summary = (
                    f"删除预览：{len(plan)} 项（从副目录删除）\n"
                    f"模式：{mode}，包含目录：{include_dirs}"
                )
                self._preview = PreviewContext(
                    plan=plan,
                    overwrite=False,
                    remove_empty_dirs_root=remove_empty_root,
                    clean_source_empty_dirs_root=None,
                    summary=summary,
                )
            else:
                direction = self.direction_combo.currentData()
                op = self.op_combo.currentData()
                migrate_all = self.cb_migrate_all.isChecked()
                src_root, dst_root, plan = plan_migrate(
                    main_dir,
                    sub_dir,
                    direction=direction,
                    mode=mode,
                    op=op,
                    migrate_all=migrate_all,
                )
                overwrite = self.cb_overwrite.isChecked()
                clean_source_root = None
                if self.cb_clean_source.isChecked() and op == "move":
                    clean_source_root = src_root

                summary = (
                    f"迁移预览：{len(plan)} 项\n"
                    f"方向：{self.direction_combo.currentText()}，"
                    f"方式：{self.op_combo.currentText()}\n"
                    f"模式：{mode}，源：{src_root}，目标：{dst_root}"
                )
                self._preview = PreviewContext(
                    plan=plan,
                    overwrite=overwrite,
                    remove_empty_dirs_root=None,
                    clean_source_empty_dirs_root=clean_source_root,
                    summary=summary,
                )

            self._set_table(self._preview.plan)
            self.status.setText(self._preview.summary)
            self._refresh_enabled()

            if len(self._preview.plan) == 0:
                QMessageBox.information(self, "结果", "没有需要处理的项。")

        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))

    def _on_execute(self) -> None:
        if not self._preview:
            QMessageBox.information(self, "提示", "请先点击“预览结果”。")
            return
        if len(self._preview.plan) == 0:
            QMessageBox.information(self, "提示", "没有可执行的项。")
            return

        confirm = QMessageBox.question(
            self,
            "确认执行",
            self._preview.summary + "\n\n确认要执行吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self.preview_btn.setEnabled(False)
        self.exec_btn.setEnabled(False)

        self._thread = QThread(self)
        self._worker = Worker(
            plan=self._preview.plan,
            overwrite=self._preview.overwrite,
            remove_empty_dirs_root=self._preview.remove_empty_dirs_root,
            clean_source_empty_dirs_root=(
                self._preview.clean_source_empty_dirs_root
            ),
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self.status.setText("执行中…")
        self._thread.start()

    def _on_progress(self, done: int, total: int, msg: str) -> None:
        self.status.setText(f"执行中：{done}/{total}  {msg}")

    def _on_finished(self, result: ExecResult) -> None:
        self.preview_btn.setEnabled(True)
        self._preview = None
        self._refresh_enabled()

        if result.failed == 0:
            QMessageBox.information(self, "完成", f"成功处理 {result.ok} 项。")
        else:
            err_text = "\n".join(result.errors[:50])
            if len(result.errors) > 50:
                err_text += "\n…（仅显示前 50 条）"
            
            # Check if any errors are permission-related
            has_permission_err = any(
                "权限错误" in e or "被占用" in e or "WinError 5" in e
                for e in result.errors
            )
            
            extra_hint = ""
            if has_permission_err:
                extra_hint = (
                    "\n\n💡 提示：部分文件可能正被其他程序占用。\n"
                    "请关闭视频播放器、编辑器、文件预览等程序后重试。"
                )
            
            QMessageBox.warning(
                self,
                "完成（有失败）",
                (
                    f"成功 {result.ok} 项，失败 {result.failed} 项。"
                    f"{extra_hint}\n\n失败详情：\n{err_text}"
                ),
            )

        self._clear_table()


def main() -> int:
    app = QApplication(sys.argv)

    # A cleaner default look across Windows
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
