from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from apps.polished_job_prompt import compose_boss_prompt
from orchestrator.hive.controller import HiveController
from orchestrator.hive.gates import load_project_commands
from orchestrator.hive.protocol import JobMode, JobRecord, JobRequest

DEFAULT_GOAL = "把这件事接走，最后只把可验收结果给我。"
DEFAULT_BACKGROUND = ""
DEFAULT_OFFLOAD = "我不想盯过程、催进度或来回返工沟通。"
DEFAULT_DELIVERABLE = "只告诉我结论、证据、风险和下一步。"

STATE_FILE = Path.home() / ".codex" / "hive_boss_dialog_state.json"
MAX_RECENT_REPOS = 4

SURFACE = "#0b1016"
PANEL = "#101720"
CARD = "#121b26"
CARD_ALT = "#0d141d"
EDGE = "#202c3b"
EDGE_SOFT = "#182230"
TEXT = "#eef3fa"
TEXT_SOFT = "#a2b0c2"
TEXT_DIM = "#76859a"
ACCENT = "#dfe7f3"
ACCENT_LINE = "#42597a"
SUCCESS = "#1f6b51"
WARNING = "#8c6930"
FAILURE = "#8a4b52"
INFO = "#335f8b"
SELECTION = "#243446"

APP_QSS = f"""
QMainWindow, QWidget {{
    background: {SURFACE};
    color: {TEXT};
    font-family: "Segoe UI", "Microsoft YaHei UI";
}}
QWidget#Column {{
    background: transparent;
}}
QLabel {{
    background: transparent;
}}
QFrame#Card {{
    background: {CARD};
    border: 1px solid {EDGE_SOFT};
    border-radius: 18px;
}}
QFrame#Hero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #101824, stop:0.55 #121c28, stop:1 #182434);
    border: 1px solid {ACCENT_LINE};
    border-radius: 20px;
}}
QLabel#Kicker {{
    color: {TEXT_DIM};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
}}
QLabel#Heading {{
    color: {TEXT};
    font-size: 15px;
    font-weight: 700;
}}
QLabel#HeroTitle {{
    color: {TEXT};
    font-size: 22px;
    font-weight: 700;
}}
QLabel#Lead {{
    color: {TEXT_SOFT};
    font-size: 13px;
}}
QLabel#Muted {{
    color: {TEXT_DIM};
    font-size: 12px;
}}
QLineEdit, QPlainTextEdit, QTextEdit {{
    background: #0a1118;
    border: 1px solid {EDGE};
    border-radius: 14px;
    padding: 11px 12px;
    color: {TEXT};
    selection-background-color: #294564;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {ACCENT_LINE};
}}
QPushButton {{
    background: #121b26;
    border: 1px solid {EDGE};
    border-radius: 13px;
    color: {TEXT};
    padding: 9px 14px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: #182332;
    border-color: #30445d;
}}
QPushButton#PrimaryButton {{
    background: {ACCENT};
    color: #0b1118;
    border: 1px solid #d9e3f1;
}}
QPushButton#GhostButton {{
    background: transparent;
}}
QPushButton#ModeButton:checked {{
    background: {SELECTION};
    border-color: #4f6783;
}}
QPushButton#RepoButton {{
    text-align: left;
    padding: 10px 12px;
}}
QPushButton#RepoButton:checked {{
    background: {SELECTION};
    border-color: #4f6783;
}}
QToolButton {{
    background: transparent;
    border: none;
    color: {TEXT_SOFT};
    font-size: 12px;
    font-weight: 600;
    padding: 2px 0;
}}
QToolButton:hover {{
    color: {TEXT};
}}
QScrollArea, QSplitter {{
    background: transparent;
    border: none;
}}
QTabWidget::pane {{
    border: 1px solid {EDGE};
    border-radius: 16px;
    background: {CARD_ALT};
    top: -1px;
}}
QTabBar::tab {{
    background: #101821;
    border: 1px solid {EDGE};
    border-bottom: none;
    border-top-left-radius: 11px;
    border-top-right-radius: 11px;
    padding: 8px 12px;
    margin-right: 6px;
    color: {TEXT_DIM};
}}
QTabBar::tab:selected {{
    background: #172230;
    color: {TEXT};
}}
"""


@dataclass
class DesktopJobInput:
    repo_path: Path
    goal: str
    background: str
    offload: str
    deliverable: str
    mode: JobMode


@dataclass
class ProjectSnapshot:
    repo_path: Path
    name: str
    has_agents: bool
    is_git: bool
    has_owner_profile: bool
    command_labels: list[str]
    latest_run_dir: str | None
    hint: str


@dataclass
class AppState:
    repo_path: str
    recent_repos: list[str] = field(default_factory=list)
    goal: str = DEFAULT_GOAL
    background: str = DEFAULT_BACKGROUND
    offload: str = DEFAULT_OFFLOAD
    deliverable: str = DEFAULT_DELIVERABLE
    mode: str = JobMode.AUTO.value
    last_run_dir: str = ""
    last_delivery_path: str = ""


def run_desktop_job(job: DesktopJobInput) -> JobRecord:
    controller = HiveController(job.repo_path.resolve())
    request = JobRequest(
        boss_prompt=compose_boss_prompt(
            goal=job.goal,
            background=job.background,
            offload=job.offload,
            deliverable=job.deliverable,
        ),
        repo_path=str(job.repo_path.resolve()),
        mode=job.mode,
    )
    return asyncio.run(controller.run_job(request))


def remember_recent_repo(recent_repos: list[str], repo_path: str | Path, *, limit: int = MAX_RECENT_REPOS) -> list[str]:
    normalized = str(Path(repo_path).expanduser().resolve(strict=False))
    merged = [normalized]
    for item in recent_repos:
        candidate = str(Path(item).expanduser().resolve(strict=False))
        if candidate not in merged:
            merged.append(candidate)
    return merged[:limit]


def load_app_state(state_file: Path | None = None) -> AppState:
    state_file = state_file or STATE_FILE
    fallback_repo = str(Path.cwd().resolve())
    default = AppState(repo_path=fallback_repo, recent_repos=[fallback_repo])
    if not state_file.exists():
        return default
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return default
    if not isinstance(payload, dict):
        return default

    repo_path = str(Path(str(payload.get("repo_path") or fallback_repo)).expanduser().resolve(strict=False))
    recent = payload.get("recent_repos")
    recent_list = [str(item) for item in recent] if isinstance(recent, list) else [repo_path]
    return AppState(
        repo_path=repo_path,
        recent_repos=remember_recent_repo(recent_list, repo_path),
        goal=str(payload.get("goal") or DEFAULT_GOAL),
        background=str(payload.get("background") or DEFAULT_BACKGROUND),
        offload=str(payload.get("offload") or DEFAULT_OFFLOAD),
        deliverable=str(payload.get("deliverable") or DEFAULT_DELIVERABLE),
        mode=str(payload.get("mode") or JobMode.AUTO.value),
        last_run_dir=str(payload.get("last_run_dir") or ""),
        last_delivery_path=str(payload.get("last_delivery_path") or ""),
    )


def save_app_state(state: AppState, state_file: Path | None = None) -> None:
    state_file = state_file or STATE_FILE
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")


def inspect_project(repo_path: Path) -> ProjectSnapshot:
    commands = load_project_commands(repo_path / "AGENTS.md")
    command_labels = [
        label
        for key, label in (
            ("INSTALL_CMD", "Install"),
            ("TEST_CMD", "Tests"),
            ("LINT_CMD", "Lint"),
            ("TYPECHECK_CMD", "Typecheck"),
        )
        if key in commands
    ]
    has_agents = (repo_path / "AGENTS.md").exists()
    has_owner_profile = any((repo_path / candidate).exists() for candidate in ("OWNER_PROFILE.md", "OWNER_PROFILE.txt"))
    latest_run_dir = _find_latest_run_dir(repo_path)
    is_git = _is_git_checkout(repo_path)
    if has_agents and command_labels:
        hint = "规则和闸门已识别"
    elif has_agents:
        hint = "规则存在，但闸门不完整"
    else:
        hint = "缺少 AGENTS.md"
    return ProjectSnapshot(
        repo_path=repo_path,
        name=repo_path.name or str(repo_path),
        has_agents=has_agents,
        is_git=is_git,
        has_owner_profile=has_owner_profile,
        command_labels=command_labels,
        latest_run_dir=latest_run_dir,
        hint=hint,
    )


def format_boss_summary(record: JobRecord) -> str:
    lines: list[str] = []
    if record.delivery is not None:
        lines.append(record.delivery.summary)
        lines.append(f"状态: {record.status.value}")
        lines.append(f"Reviewer: {record.delivery.reviewer_decision} / blockers={record.delivery.reviewer_blocker_count}")
        if record.delivery.risks:
            lines.extend(["", "风险"])
            lines.extend(f"- {risk}" for risk in record.delivery.risks[:4])
        if record.delivery.remaining_gaps:
            lines.extend(["", "缺口"])
            lines.extend(f"- {gap}" for gap in record.delivery.remaining_gaps[:4])
    else:
        lines.append("任务结束，但还没有标准交付摘要。")
        lines.append(f"状态: {record.status.value}")
    if record.runtime_notes:
        lines.extend(["", "运行备注"])
        lines.extend(f"- {note}" for note in record.runtime_notes[:4])
    return "\n".join(lines)


def format_artifact_evidence(record: JobRecord) -> str:
    lines = [
        f"Run: {record.artifacts.run_dir}",
        f"Plan: {record.artifacts.plan}",
        f"Deliver: {record.artifacts.delivery or 'N/A'}",
    ]
    if record.artifacts.patch:
        lines.append(f"Patch: {record.artifacts.patch}")
    if record.delivery is not None:
        lines.append(f"Gate: {record.delivery.gate_report_path}")
        if record.delivery.verification:
            lines.extend(["", "验证"])
            for step in record.delivery.verification:
                suffix = f" | {step.log_path}" if step.log_path else ""
                lines.append(f"- {step.command} -> {step.result}{suffix}")
        if record.delivery.artifacts:
            lines.extend(["", "工件"])
            lines.extend(f"- {artifact.name}: {artifact.path}" for artifact in record.delivery.artifacts[:8])
    return "\n".join(lines)


def format_chat_reply(record: JobRecord) -> str:
    if record.delivery is None:
        return f"任务结束，当前状态 {record.status.value}。"
    lines = [
        record.delivery.summary,
        f"Reviewer: {record.delivery.reviewer_decision} / blockers={record.delivery.reviewer_blocker_count}",
    ]
    if record.delivery.risks:
        lines.extend(["", "风险"])
        lines.extend(f"- {risk}" for risk in record.delivery.risks[:3])
    if record.delivery.remaining_gaps:
        lines.extend(["", "缺口"])
        lines.extend(f"- {gap}" for gap in record.delivery.remaining_gaps[:3])
    return "\n".join(lines)


def format_job_record(record: JobRecord) -> str:
    lines = [
        f"任务号: {record.job_id}",
        f"状态: {record.status.value}",
        f"模式: {record.mode.value}",
        f"项目: {record.repo_path}",
        f"运行目录: {record.artifacts.run_dir}",
    ]
    if record.delivery is not None:
        lines.extend(
            [
                "",
                f"结论: {record.delivery.summary}",
                f"Outcome: {record.delivery.outcome.value}",
                f"Reviewer: {record.delivery.reviewer_decision} ({record.delivery.reviewer_blocker_count} blockers)",
                f"交付包: {record.artifacts.delivery or 'N/A'}",
                f"Gate: {record.delivery.gate_report_path}",
            ]
        )
        if record.delivery.remaining_gaps:
            lines.extend(["", "缺口"])
            lines.extend(f"- {gap}" for gap in record.delivery.remaining_gaps)
        if record.delivery.risks:
            lines.extend(["", "风险"])
            lines.extend(f"- {risk}" for risk in record.delivery.risks)
    if record.runtime_notes:
        lines.extend(["", "运行备注"])
        lines.extend(f"- {note}" for note in record.runtime_notes)
    return "\n".join(lines)


def _find_latest_run_dir(repo_path: Path) -> str | None:
    runs_dir = repo_path / "runs"
    if not runs_dir.exists():
        return None
    candidates = [path for path in runs_dir.iterdir() if path.is_dir()]
    if not candidates:
        return None
    latest = max(candidates, key=lambda item: item.stat().st_mtime)
    return str(latest)


def _is_git_checkout(path: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def _status_color(status: str) -> str:
    normalized = status.lower()
    if normalized in {"pass", "passed"}:
        return SUCCESS
    if normalized in {"fail", "failed"}:
        return FAILURE
    if normalized == "needs_human":
        return WARNING
    if normalized == "running":
        return INFO
    return SELECTION


def _open_path(path: Path) -> None:
    target = path.resolve()
    if os.name == "nt":
        os.startfile(str(target))
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(target)])


class JobWorker(QThread):
    result_ready = Signal(object)
    error_ready = Signal(str)

    def __init__(self, job: DesktopJobInput) -> None:
        super().__init__()
        self.job = job

    def run(self) -> None:
        try:
            self.result_ready.emit(run_desktop_job(self.job))
        except Exception as exc:
            import traceback

            self.error_ready.emit("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))


class PillLabel(QLabel):
    def __init__(self, text: str, color: str = SELECTION) -> None:
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_pill(text, color)

    def set_pill(self, text: str, color: str) -> None:
        self.setText(text)
        self.setStyleSheet(
            f"background:{color}; border:1px solid {EDGE}; border-radius:999px; "
            f"padding:5px 10px; color:{TEXT}; font-size:11px; font-weight:600;"
        )


class MessageBubble(QFrame):
    def __init__(self, role: str, title: str, body: str, *, tone: str = "default") -> None:
        super().__init__()
        palette = {
            "user": ("#192b3f", "#dce9f8"),
            "assistant": ("#131b26", TEXT),
            "system": ("#101720", TEXT_SOFT),
            "error": ("#26181d", "#ffdbe0"),
        }
        background, title_color = palette.get(tone if tone != "default" else role, ("#131b26", TEXT))
        self.setMaximumWidth(760)
        self.setStyleSheet(
            f"QFrame {{ background:{background}; border:1px solid {EDGE}; border-radius:18px; }}"
            f"QLabel {{ background:transparent; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"color:{title_color}; font-size:11px; font-weight:700;")
        body_label = QLabel(body)
        body_label.setWordWrap(True)
        body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body_label.setStyleSheet(f"font-size:13px; color:{TEXT}; line-height:1.45;")

        layout.addWidget(title_label)
        layout.addWidget(body_label)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


class BossDialogApp:
    def __init__(self) -> None:
        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setApplicationName("Codex Boss Deck")
        self.qt_app.setStyleSheet(APP_QSS)
        self.qt_app.setFont(QFont("Segoe UI", 10))

        self.state = load_app_state()
        self.last_record: JobRecord | None = None
        self.last_run_dir = Path(self.state.last_run_dir) if self.state.last_run_dir else None
        self.last_delivery_path = Path(self.state.last_delivery_path) if self.state.last_delivery_path else None
        self.chat_history: list[tuple[str, str]] = []
        self.worker: JobWorker | None = None

        self.window = QMainWindow()
        self.window.setWindowTitle("Codex Boss Deck")
        self.window.resize(1460, 900)
        self.window.setMinimumSize(1220, 800)

        self._build_ui()
        self._restore_state()
        self._refresh_project_snapshot()
        self._render_recent_repos()
        self._refresh_mode_note()
        self._show_welcome_state()
        self.window.closeEvent = self._on_close_event  # type: ignore[assignment]

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([236, 914, 310])
        outer.addWidget(splitter)
        self.window.setCentralWidget(root)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.window)
        shortcut.activated.connect(self.submit_job)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("Column")
        panel.setFixedWidth(236)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        workspace = self._card("工作区")
        workspace_layout = workspace.layout()

        self.repo_input = QLineEdit()
        self.repo_input.setPlaceholderText("选择项目文件夹")
        self.repo_input.textChanged.connect(self._refresh_project_snapshot)

        repo_row = QHBoxLayout()
        repo_row.setSpacing(8)
        repo_row.addWidget(self.repo_input, 1)
        repo_row.addWidget(self._button("选择", self.choose_repo))
        workspace_layout.addLayout(repo_row)

        repo_actions = QHBoxLayout()
        repo_actions.setSpacing(8)
        self.open_project_button = self._button("打开", self.open_project_dir, ghost=True)
        self.clear_repo_button = self._button("清空", self.clear_repo, ghost=True)
        repo_actions.addWidget(self.open_project_button)
        repo_actions.addWidget(self.clear_repo_button)
        workspace_layout.addLayout(repo_actions)

        workspace_layout.addWidget(self._label("最近项目", "Muted"))
        self.recent_repos_host = QWidget()
        self.recent_repos_layout = QVBoxLayout(self.recent_repos_host)
        self.recent_repos_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_repos_layout.setSpacing(8)
        workspace_layout.addWidget(self.recent_repos_host)
        self.current_repo_note = self._label("", "Muted")
        workspace_layout.addWidget(self.current_repo_note)

        workspace_layout.addWidget(self._label("模式", "Muted"))
        self.mode_note_label = self._label("", "Muted")
        workspace_layout.addWidget(self.mode_note_label)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        self.mode_group = QButtonGroup(self.window)
        self.auto_button = self._button("auto", lambda: self.set_mode(JobMode.AUTO), checkable=True)
        self.auto_button.setObjectName("ModeButton")
        self.dry_button = self._button("dry-run", lambda: self.set_mode(JobMode.DRY_RUN), checkable=True)
        self.dry_button.setObjectName("ModeButton")
        self.mode_group.addButton(self.auto_button)
        self.mode_group.addButton(self.dry_button)
        mode_row.addWidget(self.auto_button)
        mode_row.addWidget(self.dry_button)
        workspace_layout.addLayout(mode_row)

        self.context_toggle = QToolButton()
        self.context_toggle.setText("补充说明")
        self.context_toggle.setCheckable(True)
        self.context_toggle.toggled.connect(self._toggle_context_panel)
        workspace_layout.addWidget(self.context_toggle)

        layout.addWidget(workspace)

        self.context_card = self._card("补充说明", "可留空")
        context_layout = self.context_card.layout()
        self.background_text = self._textbox(72)
        self.offload_text = self._textbox(64)
        self.deliverable_text = self._textbox(64)
        self.background_text.setPlaceholderText("背景或约束")
        self.offload_text.setPlaceholderText("你不想亲自处理的部分")
        self.deliverable_text.setPlaceholderText("你最终只想看到什么")
        context_layout.addWidget(self._field("背景", self.background_text))
        context_layout.addWidget(self._field("代办边界", self.offload_text))
        context_layout.addWidget(self._field("交付偏好", self.deliverable_text))
        context_layout.addWidget(self._button("恢复默认", self.reset_fields, ghost=True))
        self.context_card.setVisible(False)
        layout.addWidget(self.context_card)

        layout.addStretch(1)
        return panel

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("Column")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("Hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 18, 22, 18)
        hero_layout.setSpacing(8)

        top = QHBoxLayout()
        stack = QVBoxLayout()
        stack.setSpacing(4)
        stack.addWidget(self._label("把事情交给我", "HeroTitle"))
        self.chat_subheadline = self._label("说一句目标就行。", "Lead")
        stack.addWidget(self.chat_subheadline)
        top.addLayout(stack, 1)
        self.status_pill = PillLabel("待命", SELECTION)
        top.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(top)
        layout.addWidget(hero)

        lane = QFrame()
        lane.setObjectName("Card")
        lane_layout = QVBoxLayout(lane)
        lane_layout.setContentsMargins(16, 16, 16, 16)
        lane_layout.setSpacing(0)

        self.empty_state = self._build_empty_state()
        lane_layout.addWidget(self.empty_state)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_body = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_body)
        self.chat_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch(1)
        self.chat_scroll.setWidget(self.chat_body)
        self.chat_scroll.setVisible(False)
        lane_layout.addWidget(self.chat_scroll)
        layout.addWidget(lane, 1)

        composer = self._card("")
        composer_layout = composer.layout()
        self.goal_text = QPlainTextEdit()
        self.goal_text.setPlaceholderText("例如：把登录页报错梳理好，补上必要测试，然后只给我结论。")
        self.goal_text.setMinimumHeight(150)
        composer_layout.addWidget(self.goal_text)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.send_button = self._button("开始交付", self.submit_job, primary=True)
        actions.addWidget(self.send_button)
        actions.addStretch(1)
        actions.addWidget(self._label("Ctrl+Enter 发送", "Muted"))
        composer_layout.addLayout(actions)
        layout.addWidget(composer)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("Column")
        panel.setFixedWidth(310)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        summary = QFrame()
        summary.setObjectName("Card")
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(10)

        summary_layout.addWidget(self._label("交付", "Kicker"))
        self.project_title = self._label("未连接项目", "Heading")
        self.project_meta = self._label("", "Muted")
        self.project_hint = self._label("", "Lead")
        summary_layout.addWidget(self.project_title)
        summary_layout.addWidget(self.project_meta)
        summary_layout.addWidget(self.project_hint)

        self.badges_host = QWidget()
        self.badges_layout = QHBoxLayout(self.badges_host)
        self.badges_layout.setContentsMargins(0, 0, 0, 0)
        self.badges_layout.setSpacing(8)
        summary_layout.addWidget(self.badges_host)

        self.commands_host = QWidget()
        self.commands_layout = QHBoxLayout(self.commands_host)
        self.commands_layout.setContentsMargins(0, 0, 0, 0)
        self.commands_layout.setSpacing(8)
        summary_layout.addWidget(self.commands_host)

        strip = QWidget()
        strip_layout = QHBoxLayout(strip)
        strip_layout.setContentsMargins(0, 0, 0, 0)
        strip_layout.setSpacing(8)
        self.summary_status = PillLabel("待命", SELECTION)
        self.summary_mode = PillLabel("auto", CARD_ALT)
        self.summary_review = PillLabel("Reviewer", CARD_ALT)
        strip_layout.addWidget(self.summary_status)
        strip_layout.addWidget(self.summary_mode)
        strip_layout.addWidget(self.summary_review)
        summary_layout.addWidget(strip)

        actions = QWidget()
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        self.open_run_button = self._button("运行目录", self.open_run_dir)
        self.open_delivery_button = self._button("交付文件", self.open_delivery_file)
        actions_layout.addWidget(self.open_run_button)
        actions_layout.addWidget(self.open_delivery_button)
        summary_layout.addWidget(actions)
        self.copy_summary_button = self._button("复制摘要", self.copy_summary, ghost=True)
        summary_layout.addWidget(self.copy_summary_button)
        layout.addWidget(summary)

        self.tabs = QTabWidget()
        self.summary_text = self._read_only()
        self.evidence_text = self._read_only()
        self.record_text = self._read_only()
        self.tabs.addTab(self.summary_text, "摘要")
        self.tabs.addTab(self.evidence_text, "证据")
        self.tabs.addTab(self.record_text, "记录")
        layout.addWidget(self.tabs, 1)
        return panel

    def _build_empty_state(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 56, 0, 56)
        layout.setSpacing(10)
        layout.addStretch(1)
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(6)
        card_layout.addWidget(self._label("直接说任务", "Heading"))
        card_layout.addWidget(self._label("选一次项目，然后把目标交给我。", "Lead"))
        layout.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return wrapper

    def _label(self, text: str, style: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(style)
        label.setWordWrap(True)
        return label

    def _card(self, title: str, subtitle: str = "") -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        if title:
            layout.addWidget(self._label(title, "Heading"))
        if subtitle:
            layout.addWidget(self._label(subtitle, "Muted"))
        return card

    def _button(
        self,
        text: str,
        callback,
        *,
        primary: bool = False,
        ghost: bool = False,
        checkable: bool = False,
        repo_button: bool = False,
    ) -> QPushButton:
        button = QPushButton(text)
        if primary:
            button.setObjectName("PrimaryButton")
        elif ghost:
            button.setObjectName("GhostButton")
        elif repo_button:
            button.setObjectName("RepoButton")
        button.setCheckable(checkable)
        button.clicked.connect(callback)
        return button

    def _textbox(self, min_height: int) -> QPlainTextEdit:
        editor = QPlainTextEdit()
        editor.setMinimumHeight(min_height)
        return editor

    def _field(self, title: str, editor: QPlainTextEdit) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._label(title, "Muted"))
        layout.addWidget(editor)
        return wrapper

    def _read_only(self) -> QTextEdit:
        widget = QTextEdit()
        widget.setReadOnly(True)
        widget.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        return widget

    def _restore_state(self) -> None:
        self.repo_input.setText(self.state.repo_path)
        self.background_text.setPlainText(self.state.background)
        self.offload_text.setPlainText(self.state.offload)
        self.deliverable_text.setPlainText(self.state.deliverable)
        self.goal_text.setPlainText("")
        self.set_mode(JobMode(self.state.mode))
        self._sync_action_buttons()

    def _show_welcome_state(self) -> None:
        self._clear_messages()
        self.empty_state.setVisible(True)
        self.chat_scroll.setVisible(False)
        self.summary_text.setPlainText("还没有交付结果。")
        self.evidence_text.setPlainText("等待工件。")
        self.record_text.setPlainText("等待记录。")

    def _clear_messages(self) -> None:
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def append_message(self, role: str, title: str, body: str, *, tone: str = "default") -> None:
        self.empty_state.setVisible(False)
        self.chat_scroll.setVisible(True)

        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        bubble = MessageBubble(role, title, body, tone=tone)
        if role == "user":
            row.addStretch(1)
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch(1)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, holder)
        scroll_bar = self.chat_scroll.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def choose_repo(self) -> None:
        selected = QFileDialog.getExistingDirectory(self.window, "选择项目文件夹", self.repo_input.text() or str(Path.cwd()))
        if not selected:
            return
        self.repo_input.setText(selected)
        self.state.recent_repos = remember_recent_repo(self.state.recent_repos, selected)
        self._render_recent_repos()
        self._refresh_project_snapshot()
        self._write_state()
        self.status_pill.set_pill("项目已切换", INFO)

    def clear_repo(self) -> None:
        self.repo_input.clear()
        self._render_recent_repos()
        self.status_pill.set_pill("待命", SELECTION)
        self.chat_subheadline.setText("说一句目标就行。")

    def open_project_dir(self) -> None:
        repo_path = Path(self.repo_input.text()).expanduser()
        if repo_path.exists():
            _open_path(repo_path)

    def open_run_dir(self) -> None:
        if self.last_record is not None:
            _open_path(Path(self.last_record.artifacts.run_dir))
            return
        if self.last_run_dir is not None and self.last_run_dir.exists():
            _open_path(self.last_run_dir)

    def open_delivery_file(self) -> None:
        if self.last_record is not None and self.last_record.artifacts.delivery:
            _open_path(Path(self.last_record.artifacts.delivery))
            return
        if self.last_delivery_path is not None and self.last_delivery_path.exists():
            _open_path(self.last_delivery_path)

    def copy_summary(self) -> None:
        if self.last_record is None:
            return
        QGuiApplication.clipboard().setText(format_boss_summary(self.last_record))
        self.status_pill.set_pill("摘要已复制", INFO)

    def set_mode(self, mode: JobMode) -> None:
        self.auto_button.setChecked(mode == JobMode.AUTO)
        self.dry_button.setChecked(mode == JobMode.DRY_RUN)
        self.state.mode = mode.value
        self.summary_mode.set_pill(mode.value, CARD_ALT)
        self._refresh_mode_note()

    def _refresh_mode_note(self) -> None:
        if self.auto_button.isChecked():
            self.mode_note_label.setText("直接推进交付")
        else:
            self.mode_note_label.setText("先产出计划和交付骨架")

    def _toggle_context_panel(self, checked: bool) -> None:
        self.context_card.setVisible(checked)
        self.context_toggle.setText("收起补充" if checked else "补充说明")

    def _render_recent_repos(self) -> None:
        while self.recent_repos_layout.count():
            item = self.recent_repos_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        repos = self.state.recent_repos or [str(Path.cwd().resolve())]
        current = str(Path(self.repo_input.text()).expanduser().resolve(strict=False)) if self.repo_input.text().strip() else ""
        for repo in repos[:MAX_RECENT_REPOS]:
            path = Path(repo)
            label = path.name or str(path)
            button = self._button(
                label,
                lambda _checked=False, value=repo: self._use_recent_repo(value),
                checkable=True,
                repo_button=True,
            )
            button.setChecked(str(path.expanduser().resolve(strict=False)) == current)
            button.setToolTip(repo)
            self.recent_repos_layout.addWidget(button)
        self.recent_repos_layout.addStretch(1)

    def _use_recent_repo(self, repo: str) -> None:
        self.repo_input.setText(repo)
        self.state.recent_repos = remember_recent_repo(self.state.recent_repos, repo)
        self._refresh_project_snapshot()
        self._render_recent_repos()
        self._write_state()
        self.status_pill.set_pill("项目已切换", INFO)
        self.chat_subheadline.setText(f"当前项目：{Path(repo).name or repo}")

    def _refresh_project_snapshot(self) -> None:
        repo_text = self.repo_input.text().strip()
        if not repo_text:
            self.project_title.setText("未连接项目")
            self.project_meta.setText("选择一个可用目录")
            self.project_hint.setText("")
            self.current_repo_note.setText("未选择项目")
            self.open_project_button.setEnabled(False)
            self._render_badges([])
            self._render_command_badges([])
            return

        repo_path = Path(repo_text).expanduser()
        if not repo_path.exists() or not repo_path.is_dir():
            self.project_title.setText("目录无效")
            self.project_meta.setText(repo_text)
            self.project_hint.setText("这个路径不能作为项目工作区。")
            self.current_repo_note.setText(repo_text)
            self.open_project_button.setEnabled(False)
            self._render_badges([])
            self._render_command_badges([])
            return

        self.open_project_button.setEnabled(True)
        snapshot = inspect_project(repo_path)
        latest_run = Path(snapshot.latest_run_dir).name if snapshot.latest_run_dir else "暂无运行"
        owner_state = "Owner" if snapshot.has_owner_profile else "No Owner"
        git_state = "Git" if snapshot.is_git else "No Git"
        self.project_title.setText(snapshot.name)
        self.project_meta.setText(f"{latest_run} · {owner_state} · {git_state}")
        self.project_hint.setText(snapshot.hint)
        self.current_repo_note.setText(str(repo_path))
        self._render_badges(
            [
                ("AGENTS", SUCCESS if snapshot.has_agents else WARNING),
                ("Git" if snapshot.is_git else "No Git", SUCCESS if snapshot.is_git else WARNING),
                ("Owner" if snapshot.has_owner_profile else "No Owner", INFO if snapshot.has_owner_profile else SELECTION),
            ]
        )
        self._render_command_badges(snapshot.command_labels)

    def _render_badges(self, badges: list[tuple[str, str]]) -> None:
        while self.badges_layout.count():
            item = self.badges_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for text, color in badges:
            self.badges_layout.addWidget(PillLabel(text, color))
        self.badges_layout.addStretch(1)

    def _render_command_badges(self, labels: list[str]) -> None:
        while self.commands_layout.count():
            item = self.commands_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not labels:
            self.commands_layout.addWidget(self._label("未识别命令", "Muted"))
            self.commands_layout.addStretch(1)
            return
        for label in labels:
            self.commands_layout.addWidget(PillLabel(label, CARD_ALT))
        self.commands_layout.addStretch(1)

    def _compose_background(self) -> str:
        parts: list[str] = []
        background = self.background_text.toPlainText().strip()
        if background:
            parts.append(background)
        if self.chat_history:
            history = "\n".join(f"{speaker}: {text}" for speaker, text in self.chat_history[-4:])
            parts.append("最近上下文：\n" + history)
        return "\n\n".join(parts)

    def _inline_issue(self, detail: str) -> None:
        self.status_pill.set_pill("需要处理", WARNING)
        self.append_message("assistant", "总助", detail, tone="error")

    def submit_job(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        repo_path = Path(self.repo_input.text()).expanduser()
        if not repo_path.exists() or not repo_path.is_dir():
            self._inline_issue("先给我一个存在的项目目录。")
            return

        goal = self.goal_text.toPlainText().strip()
        if not goal:
            self._inline_issue("至少给我一句明确目标。")
            return

        self.state.recent_repos = remember_recent_repo(self.state.recent_repos, repo_path)
        self._render_recent_repos()
        self._write_state()

        self.append_message("user", "你", goal)
        self.chat_history.append(("老板", goal))
        self.append_message("assistant", "总助", "收到，开始推进。", tone="system")

        job = DesktopJobInput(
            repo_path=repo_path,
            goal=goal,
            background=self._compose_background(),
            offload=self.offload_text.toPlainText().strip(),
            deliverable=self.deliverable_text.toPlainText().strip(),
            mode=JobMode.AUTO if self.auto_button.isChecked() else JobMode.DRY_RUN,
        )

        self.goal_text.clear()
        self.send_button.setEnabled(False)
        self.open_run_button.setEnabled(False)
        self.open_delivery_button.setEnabled(False)
        self.copy_summary_button.setEnabled(False)
        self.status_pill.set_pill("运行中", INFO)
        self.summary_status.set_pill("运行中", INFO)
        self.summary_review.set_pill("Reviewer", CARD_ALT)
        self.chat_subheadline.setText("我在后台推进整条交付链。")
        self.summary_text.setPlainText("正在推进交付。")
        self.evidence_text.setPlainText("等待工件。")
        self.record_text.setPlainText("正在运行，请稍候。")

        self.worker = JobWorker(job)
        self.worker.result_ready.connect(self._handle_job_success)
        self.worker.error_ready.connect(self._handle_job_error)
        self.worker.finished.connect(lambda: self.send_button.setEnabled(True))
        self.worker.start()

    def _handle_job_error(self, payload: str) -> None:
        self.status_pill.set_pill("失败", FAILURE)
        self.summary_status.set_pill("失败", FAILURE)
        self.chat_subheadline.setText("这次没有跑完。")
        self.append_message("assistant", "总助", "这次执行失败了，详细堆栈已经写进记录。", tone="error")
        self.summary_text.setPlainText("任务失败，请查看记录。")
        self.evidence_text.setPlainText("没有生成完整交付工件。")
        self.record_text.setPlainText(payload)

    def _handle_job_success(self, record: object) -> None:
        assert isinstance(record, JobRecord)
        self.last_record = record
        self.last_run_dir = Path(record.artifacts.run_dir)
        self.last_delivery_path = Path(record.artifacts.delivery) if record.artifacts.delivery else None
        self.state.last_run_dir = record.artifacts.run_dir
        self.state.last_delivery_path = record.artifacts.delivery or ""
        self._write_state()
        self._sync_action_buttons()
        self._apply_record(record)
        self._refresh_project_snapshot()

    def _apply_record(self, record: JobRecord) -> None:
        project_name = Path(record.repo_path).name or record.repo_path
        self.status_pill.set_pill(record.status.value, _status_color(record.status.value))
        self.summary_status.set_pill(record.status.value, _status_color(record.status.value))
        self.summary_mode.set_pill(record.mode.value, CARD_ALT)
        if record.delivery is not None:
            review_color = SUCCESS if record.delivery.reviewer_decision == "PASS" else WARNING
            self.summary_review.set_pill(record.delivery.reviewer_decision, review_color)
            self.chat_subheadline.setText(record.delivery.summary)
        else:
            self.summary_review.set_pill("Reviewer", CARD_ALT)
            self.chat_subheadline.setText("任务结束，但还没有标准交付摘要。")
        self.project_title.setText(project_name)

        reply = format_chat_reply(record)
        self.chat_history.append(("系统", reply))
        self.append_message("assistant", "总助", reply)
        self.summary_text.setPlainText(format_boss_summary(record))
        self.evidence_text.setPlainText(format_artifact_evidence(record))
        self.record_text.setPlainText(format_job_record(record))

    def _sync_action_buttons(self) -> None:
        has_run = self.last_run_dir is not None and self.last_run_dir.exists()
        has_delivery = self.last_delivery_path is not None and self.last_delivery_path.exists()
        self.open_run_button.setEnabled(has_run)
        self.open_delivery_button.setEnabled(has_delivery)
        self.copy_summary_button.setEnabled(self.last_record is not None)

    def reset_fields(self) -> None:
        self.background_text.clear()
        self.offload_text.setPlainText(DEFAULT_OFFLOAD)
        self.deliverable_text.setPlainText(DEFAULT_DELIVERABLE)

    def _write_state(self) -> None:
        self.state.repo_path = self.repo_input.text().strip() or str(Path.cwd().resolve())
        self.state.goal = self.goal_text.toPlainText().strip() or DEFAULT_GOAL
        self.state.background = self.background_text.toPlainText().strip()
        self.state.offload = self.offload_text.toPlainText().strip() or DEFAULT_OFFLOAD
        self.state.deliverable = self.deliverable_text.toPlainText().strip() or DEFAULT_DELIVERABLE
        self.state.recent_repos = remember_recent_repo(self.state.recent_repos, self.state.repo_path)
        try:
            save_app_state(self.state)
        except OSError:
            pass

    def _on_close_event(self, event) -> None:
        self._write_state()
        event.accept()

    def run(self) -> None:
        self.window.show()
        self.qt_app.exec()


def entrypoint() -> None:
    BossDialogApp().run()


if __name__ == "__main__":
    entrypoint()
