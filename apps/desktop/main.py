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
    QMessageBox,
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

from apps.job_prompt import compose_boss_prompt
from orchestrator.hive.controller import HiveController
from orchestrator.hive.gates import load_project_commands
from orchestrator.hive.protocol import JobMode, JobRecord, JobRequest

DEFAULT_GOAL = "把这件事从我身上拿走，并给我一个可直接验收的结果。"
DEFAULT_BACKGROUND = "任务背景、上下文、约束和现状。"
DEFAULT_OFFLOAD = "我不想自己来回沟通、盯进度、补细节、做复查。"
DEFAULT_DELIVERABLE = "最终只给我结论、证据、风险和下一步。"


def load_app_state(state_file: Path | None = None) -> AppState:
    state_file = state_file or STATE_FILE
    fallback_repo = str(Path.cwd().resolve())
    default = AppState(
        repo_path=fallback_repo,
        recent_repos=[fallback_repo],
        goal=DEFAULT_GOAL,
        background=DEFAULT_BACKGROUND,
        offload=DEFAULT_OFFLOAD,
        deliverable=DEFAULT_DELIVERABLE,
    )
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

STATE_FILE = Path.home() / ".codex" / "hive_boss_dialog_state.json"
MAX_RECENT_REPOS = 5

SURFACE = "#090d13"
SURFACE_PANEL = "#0f151f"
SURFACE_CARD = "#121926"
SURFACE_SOFT = "#0c121b"
BORDER = "#1b2432"
TEXT = "#edf2f9"
TEXT_DIM = "#a3b2c8"
TEXT_SOFT = "#7f91a9"
ACCENT = "#d4dfef"
ACCENT_SOFT = "#20344a"
SUCCESS = "#1f7a57"
WARNING = "#886325"
FAILURE = "#8c4448"
INFO = "#2a5a83"


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


APP_QSS = f"""
QMainWindow, QWidget {{
    background: {SURFACE};
    color: {TEXT};
    font-family: "Segoe UI", "Microsoft YaHei UI";
}}
QLabel {{
    background: transparent;
}}
QFrame#Panel {{
    background: {SURFACE_PANEL};
    border: 1px solid {BORDER};
    border-radius: 24px;
}}
QFrame#Card {{
    background: {SURFACE_CARD};
    border: 1px solid {BORDER};
    border-radius: 18px;
}}
QFrame#HeroCard {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #0d1724, stop:0.58 #101a29, stop:1 #142236);
    border: 1px solid #24374d;
    border-radius: 22px;
}}
QLabel#Eyebrow {{ color: #90a3be; font-size: 11px; font-weight: 700; }}
QLabel#Title {{ color: {TEXT}; font-size: 26px; font-weight: 700; }}
QLabel#SectionTitle {{ color: {TEXT}; font-size: 18px; font-weight: 700; }}
QLabel#Lead {{ color: {TEXT_DIM}; font-size: 13px; }}
QLabel#Body {{ color: {TEXT_SOFT}; font-size: 12px; }}
QLineEdit, QPlainTextEdit, QTextEdit {{
    background: #081019;
    border: 1px solid #1a2532;
    border-radius: 16px;
    padding: 12px;
    color: {TEXT};
    selection-background-color: #264768;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border-color: #345073; }}
QPushButton {{
    background: #121a26;
    border: 1px solid #213044;
    border-radius: 14px;
    color: {TEXT};
    padding: 10px 15px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton:hover {{ background: #172233; border-color: #2e4561; }}
QPushButton#PrimaryButton {{ background: {ACCENT}; color: #0b1118; border: 1px solid #cedced; }}
QPushButton#GhostButton {{ background: transparent; }}
QPushButton#ModeButton:checked {{ background: #27384d; border-color: #496380; }}
QPushButton#RepoButton {{ text-align: left; padding: 11px 13px; }}
QToolButton {{ background: transparent; border: none; color: {TEXT_DIM}; font-size: 12px; font-weight: 600; }}
QToolButton:hover {{ color: {TEXT}; }}
QScrollArea, QSplitter {{ background: transparent; border: none; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 18px; background: {SURFACE_SOFT}; top: -1px; }}
QTabBar::tab {{
    background: #121b27;
    border: 1px solid #223043;
    border-bottom: none;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    padding: 10px 16px;
    margin-right: 6px;
    color: {TEXT_SOFT};
}}
QTabBar::tab:selected {{ background: #1b2a3c; color: {TEXT}; }}
"""


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


def load_app_state(state_file: Path = STATE_FILE) -> AppState:
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


def save_app_state(state: AppState, state_file: Path = STATE_FILE) -> None:
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
    has_owner_profile = any((repo_path / name).exists() for name in ("OWNER_PROFILE.md", "OWNER_PROFILE.txt"))
    latest_run_dir = _find_latest_run_dir(repo_path)
    is_git = _is_git_checkout(repo_path)
    if has_agents and command_labels:
        hint = "制度和验证命令都在，可以直接跑完整交付闭环。"
    elif has_agents:
        hint = "找到了 AGENTS.md，但命令不完整，部分闸门可能会跳过。"
    else:
        hint = "还没发现 AGENTS.md，系统仍能运行，但质量护栏会弱一些。"
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
    lines = [
        f"结论: {record.delivery.summary if record.delivery else '任务已结束，但还没有生成标准交付摘要。'}",
        f"当前状态: {record.status.value}",
        f"执行模式: {record.mode.value}",
    ]
    if record.delivery is not None:
        lines.append(f"Reviewer: {record.delivery.reviewer_decision} / blockers={record.delivery.reviewer_blocker_count}")
        if record.delivery.risks:
            lines.extend(["", "主要风险:"])
            lines.extend(f"- {risk}" for risk in record.delivery.risks[:6])
        if record.delivery.remaining_gaps:
            lines.extend(["", "还需注意:"])
            lines.extend(f"- {gap}" for gap in record.delivery.remaining_gaps[:6])
    if record.runtime_notes:
        lines.extend(["", "运行备注:"])
        lines.extend(f"- {note}" for note in record.runtime_notes[:6])
    return "\n".join(lines)


def format_artifact_evidence(record: JobRecord) -> str:
    lines = [
        f"项目目录: {record.repo_path}",
        f"运行目录: {record.artifacts.run_dir}",
        f"计划文件: {record.artifacts.plan}",
        f"交付文件: {record.artifacts.delivery or 'N/A'}",
    ]
    if record.artifacts.patch:
        lines.append(f"Patch: {record.artifacts.patch}")
    if record.delivery is not None:
        lines.append(f"Gate Report: {record.delivery.gate_report_path}")
        if record.delivery.verification:
            lines.extend(["", "验证命令:"])
            for step in record.delivery.verification:
                suffix = f" | log: {step.log_path}" if step.log_path else ""
                lines.append(f"- {step.name}: {step.command} -> {step.result}{suffix}")
        if record.delivery.artifacts:
            lines.extend(["", "关键工件:"])
            lines.extend(f"- {artifact.name}: {artifact.path}" for artifact in record.delivery.artifacts[:10])
    return "\n".join(lines)


def format_chat_reply(record: JobRecord) -> str:
    summary = record.delivery.summary if record.delivery else "任务结束了，但还没有生成标准交付摘要。"
    lines = [summary, "", f"状态: {record.status.value}", f"模式: {record.mode.value}"]
    if record.delivery is not None:
        lines.append(f"Reviewer: {record.delivery.reviewer_decision} / blockers={record.delivery.reviewer_blocker_count}")
        if record.delivery.risks:
            lines.extend(["", "风险:"])
            lines.extend(f"- {risk}" for risk in record.delivery.risks[:4])
        if record.delivery.remaining_gaps:
            lines.extend(["", "缺口:"])
            lines.extend(f"- {gap}" for gap in record.delivery.remaining_gaps[:4])
    return "\n".join(lines)


def format_job_record(record: JobRecord) -> str:
    lines = [
        f"任务号: {record.job_id}",
        f"状态: {record.status.value}",
        f"模式: {record.mode.value}",
        f"项目目录: {record.repo_path}",
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
                f"Gate Report: {record.delivery.gate_report_path}",
            ]
        )
        if record.delivery.remaining_gaps:
            lines.extend(["", "剩余缺口:"])
            lines.extend(f"- {gap}" for gap in record.delivery.remaining_gaps)
        if record.delivery.risks:
            lines.extend(["", "风险:"])
            lines.extend(f"- {risk}" for risk in record.delivery.risks)
    if record.runtime_notes:
        lines.extend(["", "运行备注:"])
        lines.extend(f"- {note}" for note in record.runtime_notes)
    return "\n".join(lines)


def _find_latest_run_dir(repo_path: Path) -> str | None:
    runs_dir = repo_path / "runs"
    if not runs_dir.exists():
        return None
    candidates = [path for path in runs_dir.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return str(max(candidates, key=lambda item: item.stat().st_mtime))


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
    return ACCENT_SOFT


def _open_path(path: Path) -> None:
    target = path.resolve()
    if os.name == "nt":
        os.startfile(str(target))
        return
    opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"
    subprocess.Popen([opener, str(target)])


DEFAULT_GOAL = "把这件事从我身上拿走，并给我一个可直接验收的结果。"
DEFAULT_BACKGROUND = "任务背景、上下文、约束和现状。"
DEFAULT_OFFLOAD = "我不想自己来回沟通、盯进度、补细节、做复查。"
DEFAULT_DELIVERABLE = "最终只给我结论、证据、风险和下一步。"


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
    has_owner_profile = any((repo_path / name).exists() for name in ("OWNER_PROFILE.md", "OWNER_PROFILE.txt"))
    latest_run_dir = _find_latest_run_dir(repo_path)
    is_git = _is_git_checkout(repo_path)
    if has_agents and command_labels:
        hint = "制度和验证命令都在，可以直接跑完整交付闭环。"
    elif has_agents:
        hint = "找到了 AGENTS.md，但命令不完整，部分闸门可能会跳过。"
    else:
        hint = "还没发现 AGENTS.md，系统仍能运行，但质量护栏会弱一些。"
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
    lines = [
        f"结论: {record.delivery.summary if record.delivery else '任务已结束，但还没有生成标准交付摘要。'}",
        f"当前状态: {record.status.value}",
        f"执行模式: {record.mode.value}",
    ]
    if record.delivery is not None:
        lines.append(f"Reviewer: {record.delivery.reviewer_decision} / blockers={record.delivery.reviewer_blocker_count}")
        if record.delivery.risks:
            lines.extend(["", "主要风险:"])
            lines.extend(f"- {risk}" for risk in record.delivery.risks[:6])
        if record.delivery.remaining_gaps:
            lines.extend(["", "还需注意:"])
            lines.extend(f"- {gap}" for gap in record.delivery.remaining_gaps[:6])
    if record.runtime_notes:
        lines.extend(["", "运行备注:"])
        lines.extend(f"- {note}" for note in record.runtime_notes[:6])
    return "\n".join(lines)


def format_artifact_evidence(record: JobRecord) -> str:
    lines = [
        f"项目目录: {record.repo_path}",
        f"运行目录: {record.artifacts.run_dir}",
        f"计划文件: {record.artifacts.plan}",
        f"交付文件: {record.artifacts.delivery or 'N/A'}",
    ]
    if record.artifacts.patch:
        lines.append(f"Patch: {record.artifacts.patch}")
    if record.delivery is not None:
        lines.append(f"Gate Report: {record.delivery.gate_report_path}")
        if record.delivery.verification:
            lines.extend(["", "验证命令:"])
            for step in record.delivery.verification:
                suffix = f" | log: {step.log_path}" if step.log_path else ""
                lines.append(f"- {step.name}: {step.command} -> {step.result}{suffix}")
        if record.delivery.artifacts:
            lines.extend(["", "关键工件:"])
            lines.extend(f"- {artifact.name}: {artifact.path}" for artifact in record.delivery.artifacts[:10])
    return "\n".join(lines)


def format_chat_reply(record: JobRecord) -> str:
    summary = record.delivery.summary if record.delivery else "任务结束了，但还没有生成标准交付摘要。"
    lines = [summary, "", f"状态: {record.status.value}", f"模式: {record.mode.value}"]
    if record.delivery is not None:
        lines.append(f"Reviewer: {record.delivery.reviewer_decision} / blockers={record.delivery.reviewer_blocker_count}")
        if record.delivery.risks:
            lines.extend(["", "风险:"])
            lines.extend(f"- {risk}" for risk in record.delivery.risks[:4])
        if record.delivery.remaining_gaps:
            lines.extend(["", "缺口:"])
            lines.extend(f"- {gap}" for gap in record.delivery.remaining_gaps[:4])
    return "\n".join(lines)


def format_job_record(record: JobRecord) -> str:
    lines = [
        f"任务号: {record.job_id}",
        f"状态: {record.status.value}",
        f"模式: {record.mode.value}",
        f"项目目录: {record.repo_path}",
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
                f"Gate Report: {record.delivery.gate_report_path}",
            ]
        )
        if record.delivery.remaining_gaps:
            lines.extend(["", "剩余缺口:"])
            lines.extend(f"- {gap}" for gap in record.delivery.remaining_gaps)
        if record.delivery.risks:
            lines.extend(["", "风险:"])
            lines.extend(f"- {risk}" for risk in record.delivery.risks)
    if record.runtime_notes:
        lines.extend(["", "运行备注:"])
        lines.extend(f"- {note}" for note in record.runtime_notes)
    return "\n".join(lines)


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
    def __init__(self, text: str, color: str = ACCENT_SOFT) -> None:
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_pill(text, color)

    def set_pill(self, text: str, color: str) -> None:
        self.setText(text)
        self.setStyleSheet(
            f"background:{color}; border:1px solid {BORDER}; border-radius:999px; "
            f"padding:6px 12px; color:{TEXT}; font-size:11px; font-weight:600;"
        )


class MessageBubble(QFrame):
    def __init__(self, role: str, title: str, body: str, *, tone: str = "default") -> None:
        super().__init__()
        palette = {
            "user": ("#193046", "#d9e8fb"),
            "assistant": ("#121a26", TEXT),
            "system": ("#101923", TEXT_DIM),
            "error": ("#28171b", "#ffd7dc"),
        }
        background, title_color = palette.get(tone if tone != "default" else role, ("#121a26", TEXT))
        self.setMaximumWidth(720)
        self.setStyleSheet(
            f"QFrame {{ background:{background}; border:1px solid {BORDER}; border-radius:20px; }}"
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
        body_label.setStyleSheet(f"font-size:13px; color:{TEXT};")
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
        self.window.resize(1480, 930)
        self.window.setMinimumSize(1240, 820)

        self._build_ui()
        self._restore_state()
        self._refresh_mode_note()
        self._refresh_project_snapshot()
        self._render_recent_repos()
        self._show_welcome_message()
        self.window.closeEvent = self._on_close_event  # type: ignore[assignment]

    def _build_ui(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 16, 16, 16)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_chat_panel())
        splitter.addWidget(self._build_inspector())
        splitter.setSizes([272, 920, 328])
        outer.addWidget(splitter)
        self.window.setCentralWidget(root)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.window)
        shortcut.activated.connect(self.submit_job)

    def _build_sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setFixedWidth(272)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        hero = self._card("PERSONAL CHIEF OF STAFF", "")
        hero.setObjectName("HeroCard")
        hero.layout().addWidget(self._label("Codex 老板总助", "Title"))
        hero.layout().addWidget(self._lead("一句话交办，交付结果回到右侧。"))
        layout.addWidget(hero)

        workspace = self._card("工作区", "项目、模式和补充背景统一收在这里。")
        workspace_layout = workspace.layout()
        self.repo_input = QLineEdit()
        self.repo_input.setPlaceholderText("选择你的项目目录")
        self.repo_input.textChanged.connect(self._refresh_project_snapshot)
        row = QHBoxLayout()
        row.addWidget(self.repo_input, 1)
        row.addWidget(self._button("选择文件夹", self.choose_repo))
        workspace_layout.addLayout(row)

        self.open_project_button = self._button("打开文件夹", self.open_project_dir, ghost=True)
        workspace_layout.addWidget(self.open_project_button)
        workspace_layout.addWidget(self._label("最近项目", "Eyebrow"))
        self.recent_repos_host = QWidget()
        self.recent_repos_layout = QVBoxLayout(self.recent_repos_host)
        self.recent_repos_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_repos_layout.setSpacing(8)
        workspace_layout.addWidget(self.recent_repos_host)

        workspace_layout.addSpacing(4)
        workspace_layout.addWidget(self._label("运行方式", "Eyebrow"))
        self.mode_note_label = self._body("")
        workspace_layout.addWidget(self.mode_note_label)
        mode_row = QHBoxLayout()
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

        workspace_layout.addSpacing(4)
        workspace_layout.addWidget(self._label("补充信息", "Eyebrow"))
        self.context_toggle = QToolButton()
        self.context_toggle.setText("展开补充背景")
        self.context_toggle.setCheckable(True)
        self.context_toggle.toggled.connect(self._toggle_context_panel)
        workspace_layout.addWidget(self.context_toggle)
        self.context_panel = QWidget()
        extra = QVBoxLayout(self.context_panel)
        extra.setContentsMargins(0, 0, 0, 0)
        extra.setSpacing(10)
        self.background_text = self._textbox(76)
        self.offload_text = self._textbox(64)
        self.deliverable_text = self._textbox(64)
        extra.addWidget(self._field("背景与约束", self.background_text))
        extra.addWidget(self._field("不想自己处理的事", self.offload_text))
        extra.addWidget(self._field("最终只想看到", self.deliverable_text))
        self.context_panel.setVisible(False)
        workspace_layout.addWidget(self.context_panel)

        layout.addWidget(workspace)
        layout.addStretch(1)
        return panel

        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setFixedWidth(272)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        hero = self._card("PERSONAL CHIEF OF STAFF", "")
        hero.setObjectName("HeroCard")
        hero.layout().addWidget(self._label("Codex 老板总助", "Title"))
        hero.layout().addWidget(self._lead("你只说一句目标，剩下的计划、执行、测试、审查和交付，都在后台收口。"))
        layout.addWidget(hero)

        workspace = self._card("工作区", "项目选择、最近项目和运行模式都收在这里。")
        workspace_layout = workspace.layout()
        self.repo_input = QLineEdit()
        self.repo_input.setPlaceholderText("选择你的项目目录")
        self.repo_input.textChanged.connect(self._refresh_project_snapshot)
        row = QHBoxLayout()
        row.addWidget(self.repo_input, 1)
        row.addWidget(self._button("选择文件夹", self.choose_repo))
        workspace_layout.addLayout(row)
        self.open_project_button = self._button("打开文件夹", self.open_project_dir, ghost=True)
        workspace_layout.addWidget(self.open_project_button)
        workspace_layout.addWidget(self._label("最近项目", "Eyebrow"))
        self.recent_repos_host = QWidget()
        self.recent_repos_layout = QVBoxLayout(self.recent_repos_host)
        self.recent_repos_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_repos_layout.setSpacing(8)
        workspace_layout.addWidget(self.recent_repos_host)
        layout.addWidget(workspace)

        mode_card = self._card("运行方式", "")
        mode_layout = mode_card.layout()
        self.mode_note_label = self._body("")
        mode_layout.addWidget(self.mode_note_label)
        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self.window)
        self.auto_button = self._button("auto", lambda: self.set_mode(JobMode.AUTO), checkable=True)
        self.auto_button.setObjectName("ModeButton")
        self.dry_button = self._button("dry-run", lambda: self.set_mode(JobMode.DRY_RUN), checkable=True)
        self.dry_button.setObjectName("ModeButton")
        self.mode_group.addButton(self.auto_button)
        self.mode_group.addButton(self.dry_button)
        mode_row.addWidget(self.auto_button)
        mode_row.addWidget(self.dry_button)
        mode_layout.addLayout(mode_row)
        layout.addWidget(mode_card)

        context = self._card("补充信息", "默认不填也能发任务，需要时再展开。")
        context_layout = context.layout()
        self.context_toggle = QToolButton()
        self.context_toggle.setText("展开补充背景")
        self.context_toggle.setCheckable(True)
        self.context_toggle.toggled.connect(self._toggle_context_panel)
        context_layout.addWidget(self.context_toggle)
        self.context_panel = QWidget()
        extra = QVBoxLayout(self.context_panel)
        extra.setContentsMargins(0, 0, 0, 0)
        extra.setSpacing(10)
        self.background_text = self._textbox(76)
        self.offload_text = self._textbox(64)
        self.deliverable_text = self._textbox(64)
        extra.addWidget(self._field("背景与约束", self.background_text))
        extra.addWidget(self._field("不想自己处理的事", self.offload_text))
        extra.addWidget(self._field("最终只想看到", self.deliverable_text))
        self.context_panel.setVisible(False)
        context_layout.addWidget(self.context_panel)
        layout.addWidget(context)
        layout.addStretch(1)
        return panel

    def _build_chat_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 18, 22, 18)
        hero_layout.addWidget(self._label("CHAT", "Eyebrow"))
        top = QHBoxLayout()
        stack = QVBoxLayout()
        self.chat_headline = self._label("把目标交给我", "Title")
        self.chat_subheadline = self._lead("聊天负责托付，后台负责拆解、执行、验证和交付。")
        stack.addWidget(self.chat_headline)
        stack.addWidget(self.chat_subheadline)
        top.addLayout(stack, 1)
        self.status_pill = PillLabel("待命", ACCENT_SOFT)
        top.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(top)
        layout.addWidget(hero)

        lane = QFrame()
        lane.setObjectName("Card")
        lane_layout = QVBoxLayout(lane)
        lane_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_body = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_body)
        self.chat_layout.setContentsMargins(12, 12, 12, 12)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch(1)
        self.chat_scroll.setWidget(self.chat_body)
        lane_layout.addWidget(self.chat_scroll)
        layout.addWidget(lane, 1)

        composer = self._card("直接对我说", "不用先选模板，也不用拆任务。按 Ctrl+Enter 或点击发送。")
        composer_layout = composer.layout()
        self.goal_text = QPlainTextEdit()
        self.goal_text.setPlaceholderText("例如：把登录页的报错提示梳理好，补上必要测试，然后只把可验收结果给我。")
        self.goal_text.setMinimumHeight(148)
        composer_layout.addWidget(self.goal_text)
        actions = QHBoxLayout()
        self.send_button = self._button("开始交付", self.submit_job, primary=True)
        self.reset_button = self._button("恢复默认背景", self.reset_fields, ghost=True)
        actions.addWidget(self.send_button)
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        composer_layout.addLayout(actions)
        layout.addWidget(composer)
        return panel

        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 20, 22, 20)
        hero_layout.addWidget(self._label("CHAT", "Eyebrow"))
        top = QHBoxLayout()
        stack = QVBoxLayout()
        self.chat_headline = self._label("说一句目标，剩下的我来推进。", "Title")
        self.chat_subheadline = self._lead("前台像聊天，后台才有工单、闸门、评审和交付包。")
        stack.addWidget(self.chat_headline)
        stack.addWidget(self.chat_subheadline)
        top.addLayout(stack, 1)
        self.status_pill = PillLabel("待命", ACCENT_SOFT)
        top.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignTop)
        hero_layout.addLayout(top)
        layout.addWidget(hero)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_body = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_body)
        self.chat_layout.setContentsMargins(12, 12, 12, 12)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch(1)
        self.chat_scroll.setWidget(self.chat_body)
        layout.addWidget(self.chat_scroll, 1)

        composer = self._card("直接对我说", "不用先选模板，也不用拆任务。按 Ctrl+Enter 或点击发送。")
        composer_layout = composer.layout()
        self.goal_text = QPlainTextEdit()
        self.goal_text.setPlaceholderText("例如：把登录页的报错提示梳理好，补上必要测试，然后只把可验收结果给我。")
        self.goal_text.setMinimumHeight(148)
        composer_layout.addWidget(self.goal_text)
        actions = QHBoxLayout()
        self.send_button = self._button("开始交付", self.submit_job, primary=True)
        self.reset_button = self._button("恢复默认背景", self.reset_fields, ghost=True)
        actions.addWidget(self.send_button)
        actions.addWidget(self.reset_button)
        actions.addStretch(1)
        composer_layout.addLayout(actions)
        layout.addWidget(composer)
        return panel

    def _build_inspector(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setFixedWidth(328)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        project = QFrame()
        project.setObjectName("HeroCard")
        project_layout = QVBoxLayout(project)
        project_layout.setContentsMargins(18, 16, 18, 16)
        project_layout.addWidget(self._label("DELIVERY", "Eyebrow"))
        self.project_title = self._label("等待连接项目", "SectionTitle")
        self.project_meta = self._body("")
        self.project_hint = self._body("")
        project_layout.addWidget(self.project_title)
        project_layout.addWidget(self.project_meta)
        project_layout.addWidget(self.project_hint)
        self.badges_host = QWidget()
        self.badges_layout = QHBoxLayout(self.badges_host)
        self.badges_layout.setContentsMargins(0, 0, 0, 0)
        self.commands_host = QWidget()
        self.commands_layout = QHBoxLayout(self.commands_host)
        self.commands_layout.setContentsMargins(0, 0, 0, 0)
        project_layout.addWidget(self.badges_host)
        project_layout.addWidget(self.commands_host)
        layout.addWidget(project)

        pills = QWidget()
        pills_layout = QVBoxLayout(pills)
        pills_layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        bottom = QHBoxLayout()
        self.summary_status = PillLabel("状态: 待命", ACCENT_SOFT)
        self.summary_mode = PillLabel("模式: auto", SURFACE_CARD)
        self.summary_review = PillLabel("Reviewer: 未运行", SURFACE_CARD)
        self.summary_project = PillLabel("项目: 未连接", SURFACE_CARD)
        top.addWidget(self.summary_status)
        top.addWidget(self.summary_mode)
        bottom.addWidget(self.summary_review)
        bottom.addWidget(self.summary_project)
        pills_layout.addLayout(top)
        pills_layout.addLayout(bottom)
        layout.addWidget(pills)

        actions = self._card("快捷动作", "")
        action_layout = actions.layout()
        self.open_run_button = self._button("打开运行目录", self.open_run_dir)
        self.open_delivery_button = self._button("打开交付文件", self.open_delivery_file)
        self.copy_summary_button = self._button("复制老板摘要", self.copy_summary, ghost=True)
        action_layout.addWidget(self.open_run_button)
        action_layout.addWidget(self.open_delivery_button)
        action_layout.addWidget(self.copy_summary_button)
        layout.addWidget(actions)

        self.tabs = QTabWidget()
        self.summary_text = self._read_only()
        self.evidence_text = self._read_only()
        self.record_text = self._read_only()
        self.tabs.addTab(self.summary_text, "老板摘要")
        self.tabs.addTab(self.evidence_text, "证据工件")
        self.tabs.addTab(self.record_text, "完整记录")
        layout.addWidget(self.tabs, 1)
        return panel

        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setFixedWidth(328)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        project = QFrame()
        project.setObjectName("HeroCard")
        project_layout = QVBoxLayout(project)
        project_layout.setContentsMargins(18, 16, 18, 16)
        project_layout.addWidget(self._label("DELIVERY", "Eyebrow"))
        self.project_title = self._label("等待连接项目", "SectionTitle")
        self.project_meta = self._body("")
        self.project_hint = self._body("")
        project_layout.addWidget(self.project_title)
        project_layout.addWidget(self.project_meta)
        project_layout.addWidget(self.project_hint)
        self.badges_host = QWidget()
        self.badges_layout = QHBoxLayout(self.badges_host)
        self.badges_layout.setContentsMargins(0, 0, 0, 0)
        self.commands_host = QWidget()
        self.commands_layout = QHBoxLayout(self.commands_host)
        self.commands_layout.setContentsMargins(0, 0, 0, 0)
        project_layout.addWidget(self.badges_host)
        project_layout.addWidget(self.commands_host)
        layout.addWidget(project)

        pills = QWidget()
        pills_layout = QVBoxLayout(pills)
        pills_layout.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        bottom = QHBoxLayout()
        self.summary_status = PillLabel("状态: 待命", ACCENT_SOFT)
        self.summary_mode = PillLabel("模式: auto", SURFACE_CARD)
        self.summary_review = PillLabel("Reviewer: 未运行", SURFACE_CARD)
        self.summary_project = PillLabel("项目: 未连接", SURFACE_CARD)
        top.addWidget(self.summary_status)
        top.addWidget(self.summary_mode)
        bottom.addWidget(self.summary_review)
        bottom.addWidget(self.summary_project)
        pills_layout.addLayout(top)
        pills_layout.addLayout(bottom)
        layout.addWidget(pills)

        actions = self._card("快捷动作", "")
        action_layout = actions.layout()
        self.open_run_button = self._button("打开运行目录", self.open_run_dir)
        self.open_delivery_button = self._button("打开交付文件", self.open_delivery_file)
        self.copy_summary_button = self._button("复制老板摘要", self.copy_summary, ghost=True)
        action_layout.addWidget(self.open_run_button)
        action_layout.addWidget(self.open_delivery_button)
        action_layout.addWidget(self.copy_summary_button)
        layout.addWidget(actions)

        self.tabs = QTabWidget()
        self.summary_text = self._read_only()
        self.evidence_text = self._read_only()
        self.record_text = self._read_only()
        self.tabs.addTab(self.summary_text, "老板摘要")
        self.tabs.addTab(self.evidence_text, "证据工件")
        self.tabs.addTab(self.record_text, "完整记录")
        layout.addWidget(self.tabs, 1)
        return panel

    def _label(self, text: str, style: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(style)
        label.setWordWrap(True)
        return label

    def _lead(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Lead")
        label.setWordWrap(True)
        return label

    def _body(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Body")
        label.setWordWrap(True)
        return label

    def _card(self, title: str, subtitle: str) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        if title:
            layout.addWidget(self._label(title, "Eyebrow" if title.isupper() else "SectionTitle"))
        if subtitle:
            layout.addWidget(self._body(subtitle))
        return card

    def _button(self, text: str, callback, *, primary: bool = False, ghost: bool = False, checkable: bool = False) -> QPushButton:
        button = QPushButton(text)
        if primary:
            button.setObjectName("PrimaryButton")
        elif ghost:
            button.setObjectName("GhostButton")
        button.setCheckable(checkable)
        button.clicked.connect(callback)
        return button

    def _field(self, title: str, editor: QPlainTextEdit) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._label(title, "Eyebrow"))
        layout.addWidget(editor)
        return wrapper

    def _textbox(self, height: int) -> QPlainTextEdit:
        editor = QPlainTextEdit()
        editor.setMinimumHeight(height)
        return editor

    def _read_only(self) -> QTextEdit:
        widget = QTextEdit()
        widget.setReadOnly(True)
        return widget

    def _restore_state(self) -> None:
        self.repo_input.setText(self.state.repo_path)
        self.background_text.setPlainText(self.state.background)
        self.offload_text.setPlainText(self.state.offload)
        self.deliverable_text.setPlainText(self.state.deliverable)
        self.goal_text.setPlainText("")
        self.set_mode(JobMode(self.state.mode))
        self._sync_action_buttons()

    def _show_welcome_message(self) -> None:
        self._clear_messages()
        self.append_message(
            "assistant",
            "总助",
            "把任务像聊天一样交给我就行。我会在后台做计划、执行、测试、审查和交付打包。",
            tone="system",
        )
        self.summary_text.setPlainText("老板摘要会出现在这里。\n\n- 任务是否通过\n- 怎么验证\n- 风险和回滚")
        self.evidence_text.setPlainText("证据工件会出现在这里。\n\n- run 目录\n- deliver.json / DELIVER.md\n- gate_report.json")
        self.record_text.setPlainText("完整记录会保留在这里，方便下钻。")
        return

        self._clear_messages()
        self.append_message("assistant", "总助", "把任务像聊天一样交给我就行。我会在后台做计划、执行、测试、审查和交付打包。", tone="system")
        self.summary_text.setPlainText("老板摘要会出现在这里。\n\n- 任务是否通过\n- 怎么验证\n- 风险和回滚")
        self.evidence_text.setPlainText("证据工件会出现在这里。\n\n- run 目录\n- deliver.json / DELIVER.md\n- gate_report.json")
        self.record_text.setPlainText("完整记录会保留在这里，方便下钻。")

    def _clear_messages(self) -> None:
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def append_message(self, role: str, title: str, body: str, *, tone: str = "default") -> None:
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
        bar = self.chat_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def choose_repo(self) -> None:
        selected = QFileDialog.getExistingDirectory(self.window, "选择项目文件夹", self.repo_input.text() or str(Path.cwd()))
        if not selected:
            return
        self.repo_input.setText(selected)
        self.state.recent_repos = remember_recent_repo(self.state.recent_repos, selected)
        self._render_recent_repos()
        self._write_state()

    def open_project_dir(self) -> None:
        repo_path = Path(self.repo_input.text()).expanduser()
        if repo_path.exists():
            _open_path(repo_path)

    def open_run_dir(self) -> None:
        if self.last_record is not None:
            _open_path(Path(self.last_record.artifacts.run_dir))
        elif self.last_run_dir is not None and self.last_run_dir.exists():
            _open_path(self.last_run_dir)

    def open_delivery_file(self) -> None:
        if self.last_record is not None and self.last_record.artifacts.delivery:
            _open_path(Path(self.last_record.artifacts.delivery))
        elif self.last_delivery_path is not None and self.last_delivery_path.exists():
            _open_path(self.last_delivery_path)

    def copy_summary(self) -> None:
        if self.last_record is None:
            return
        QGuiApplication.clipboard().setText(format_boss_summary(self.last_record))
        self.status_pill.set_pill("摘要已复制", INFO)
        return

        if self.last_record is None:
            return
        QGuiApplication.clipboard().setText(format_boss_summary(self.last_record))
        self.status_pill.set_pill("摘要已复制", INFO)

    def set_mode(self, mode: JobMode) -> None:
        self.auto_button.setChecked(mode == JobMode.AUTO)
        self.dry_button.setChecked(mode == JobMode.DRY_RUN)
        self.state.mode = mode.value
        self.summary_mode.set_pill(f"模式: {mode.value}", SURFACE_CARD)
        self._refresh_mode_note()
        return

        self.auto_button.setChecked(mode == JobMode.AUTO)
        self.dry_button.setChecked(mode == JobMode.DRY_RUN)
        self.state.mode = mode.value
        self.summary_mode.set_pill(f"模式: {mode.value}", SURFACE_CARD)
        self._refresh_mode_note()

    def _refresh_mode_note(self) -> None:
        note = "auto 会直接推进实现、验证、审查和交付。" if self.auto_button.isChecked() else "dry-run 先给你结构化计划和交付骨架。"
        self.mode_note_label.setText(note)

    def _toggle_context_panel(self, checked: bool) -> None:
        self.context_panel.setVisible(checked)
        self.context_toggle.setText("收起补充背景" if checked else "展开补充背景")

    def _render_recent_repos(self) -> None:
        while self.recent_repos_layout.count():
            item = self.recent_repos_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for repo in (self.state.recent_repos or [str(Path.cwd().resolve())])[:MAX_RECENT_REPOS]:
            button = self._button(Path(repo).name or repo, lambda _checked=False, value=repo: self._use_recent_repo(value), ghost=True)
            self.recent_repos_layout.addWidget(button)
        self.recent_repos_layout.addStretch(1)

    def _use_recent_repo(self, repo: str) -> None:
        self.repo_input.setText(repo)
        self.state.recent_repos = remember_recent_repo(self.state.recent_repos, repo)
        self._render_recent_repos()
        self._write_state()

    def _refresh_project_snapshot(self) -> None:
        repo_path = Path(self.repo_input.text()).expanduser()
        project_name = repo_path.name or str(repo_path) or "未连接"
        self.summary_project.set_pill(f"项目: {project_name}", SURFACE_CARD)
        if not repo_path.exists() or not repo_path.is_dir():
            self.project_title.setText("项目路径无效")
            self.project_meta.setText("请选择一个存在的项目文件夹。")
            self.project_hint.setText("路径有效后，这里会自动显示 AGENTS、Git 和命令闸门情况。")
            self.open_project_button.setEnabled(False)
            self._render_badges([])
            self._render_command_badges([])
            return

        self.open_project_button.setEnabled(True)
        snapshot = inspect_project(repo_path)
        self.project_title.setText(snapshot.name)
        self.project_meta.setText(
            f"{repo_path}\n最近运行: {snapshot.latest_run_dir or '暂无交付记录'}\n"
            f"{'有老板偏好' if snapshot.has_owner_profile else '无老板偏好'} / {'Git 可用' if snapshot.is_git else '非 Git 目录'}"
        )
        self.project_hint.setText(snapshot.hint)
        self._render_badges(
            [
                ("AGENTS.md" if snapshot.has_agents else "缺 AGENTS.md", SUCCESS if snapshot.has_agents else WARNING),
                ("Git" if snapshot.is_git else "No Git", SUCCESS if snapshot.is_git else WARNING),
                ("Owner Profile" if snapshot.has_owner_profile else "No Owner Profile", INFO if snapshot.has_owner_profile else SURFACE_CARD),
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
            self.commands_layout.addWidget(self._body("还没识别到命令闸门。"))
            self.commands_layout.addStretch(1)
            return
        for label in labels:
            self.commands_layout.addWidget(PillLabel(label, SURFACE_CARD))
        self.commands_layout.addStretch(1)

    def _compose_background(self) -> str:
        parts: list[str] = []
        if self.background_text.toPlainText().strip():
            parts.append(self.background_text.toPlainText().strip())
        if self.chat_history:
            history = "\n".join(f"{speaker}: {text}" for speaker, text in self.chat_history[-4:])
            parts.append("最近上下文：\n" + history)
            parts.append("当前这条新任务应在上面的上下文基础上继续推进。")
        return "\n\n".join(parts)

    def submit_job(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        repo_path = Path(self.repo_input.text()).expanduser()
        if not repo_path.exists() or not repo_path.is_dir():
            QMessageBox.critical(self.window, "目录无效", "请先选择一个存在的项目文件夹。")
            return
        goal = self.goal_text.toPlainText().strip()
        if not goal:
            QMessageBox.critical(self.window, "缺少任务", "至少写一句你想让我接手的事。")
            return

        self.state.recent_repos = remember_recent_repo(self.state.recent_repos, repo_path)
        self._render_recent_repos()
        self._write_state()

        self.append_message("user", "你", goal)
        self.chat_history.append(("老板", goal))
        self.append_message("assistant", "总助", "收到。我会静默推进整条交付链，右侧同步更新收口后的摘要和工件。", tone="system")

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
        self.status_pill.set_pill("正在推进", INFO)
        self.summary_status.set_pill("状态: running", INFO)
        self.summary_review.set_pill("Reviewer: 等待中", SURFACE_CARD)
        self.summary_text.setPlainText("任务已接手，正在生成计划并推进交付。")
        self.evidence_text.setPlainText(f"项目目录: {repo_path.resolve()}\n模式: {job.mode.value}\n\n等待任务结果。")
        self.record_text.setPlainText("正在运行，请稍候...\n")
        self.chat_headline.setText("正在静默推进整条交付链。")
        self.chat_subheadline.setText("系统会先拆任务，再跑执行、测试、审查和交付打包。")

        self.worker = JobWorker(job)
        self.worker.result_ready.connect(self._handle_job_success)
        self.worker.error_ready.connect(self._handle_job_error)
        self.worker.finished.connect(lambda: self.send_button.setEnabled(True))
        self.worker.start()

    def _handle_job_error(self, payload: str) -> None:
        self.status_pill.set_pill("失败", FAILURE)
        self.summary_status.set_pill("状态: failed", FAILURE)
        self.append_message("assistant", "总助", payload, tone="error")
        self.summary_text.setPlainText("任务失败。请查看完整记录里的错误堆栈。")
        self.evidence_text.setPlainText("这次没有生成完整交付工件。")
        self.record_text.setPlainText(payload)
        QMessageBox.critical(self.window, "交付失败", "任务执行失败，详细堆栈已经写到结果区。")

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
        self.summary_status.set_pill(f"状态: {record.status.value}", _status_color(record.status.value))
        self.summary_mode.set_pill(f"模式: {record.mode.value}", SURFACE_CARD)
        self.summary_project.set_pill(f"项目: {project_name}", SURFACE_CARD)
        if record.delivery is not None:
            review_color = SUCCESS if record.delivery.reviewer_decision == "PASS" else WARNING
            self.summary_review.set_pill(f"Reviewer: {record.delivery.reviewer_decision}", review_color)
            self.chat_headline.setText(record.delivery.summary)
            self.chat_subheadline.setText(
                f"任务号 {record.job_id} / Reviewer {record.delivery.reviewer_decision} / blockers {record.delivery.reviewer_blocker_count}"
            )
        else:
            self.summary_review.set_pill("Reviewer: 未审查", SURFACE_CARD)
            self.chat_headline.setText("任务结束了，但还没有标准交付摘要。")
            self.chat_subheadline.setText(f"任务号 {record.job_id}")
        reply = format_chat_reply(record)
        self.chat_history.append(("系统", reply))
        self.append_message("assistant", "总助", reply)
        self.summary_text.setPlainText(format_boss_summary(record))
        self.evidence_text.setPlainText(format_artifact_evidence(record))
        self.record_text.setPlainText(format_job_record(record))

    def choose_repo(self) -> None:
        selected = QFileDialog.getExistingDirectory(self.window, "选择项目文件夹", self.repo_input.text() or str(Path.cwd()))
        if not selected:
            return
        self.repo_input.setText(selected)
        self.state.recent_repos = remember_recent_repo(self.state.recent_repos, selected)
        self._render_recent_repos()
        self._write_state()

    def copy_summary(self) -> None:
        if self.last_record is None:
            return
        QGuiApplication.clipboard().setText(format_boss_summary(self.last_record))
        self.status_pill.set_pill("摘要已复制", INFO)

    def set_mode(self, mode: JobMode) -> None:
        self.auto_button.setChecked(mode == JobMode.AUTO)
        self.dry_button.setChecked(mode == JobMode.DRY_RUN)
        self.state.mode = mode.value
        self.summary_mode.set_pill(f"模式: {mode.value}", SURFACE_CARD)
        self._refresh_mode_note()

    def _refresh_mode_note(self) -> None:
        note = "auto 会直接推进实现、验证、审查和交付。" if self.auto_button.isChecked() else "dry-run 先给你结构化计划和交付骨架。"
        self.mode_note_label.setText(note)

    def _toggle_context_panel(self, checked: bool) -> None:
        self.context_panel.setVisible(checked)
        self.context_toggle.setText("收起补充背景" if checked else "展开补充背景")

    def _render_recent_repos(self) -> None:
        while self.recent_repos_layout.count():
            item = self.recent_repos_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for repo in (self.state.recent_repos or [str(Path.cwd().resolve())])[:MAX_RECENT_REPOS]:
            button = self._button(Path(repo).name or repo, lambda _checked=False, value=repo: self._use_recent_repo(value), ghost=True)
            button.setObjectName("RepoButton")
            button.setToolTip(repo)
            self.recent_repos_layout.addWidget(button)
        self.recent_repos_layout.addStretch(1)

    def _refresh_project_snapshot(self) -> None:
        repo_path = Path(self.repo_input.text()).expanduser()
        project_name = repo_path.name or str(repo_path) or "未连接"
        self.summary_project.set_pill(f"项目: {project_name}", SURFACE_CARD)
        if not repo_path.exists() or not repo_path.is_dir():
            self.project_title.setText("项目路径无效")
            self.project_meta.setText("请选择一个存在的项目文件夹。")
            self.project_hint.setText("路径有效后，这里会自动显示 AGENTS、Git 和命令闸门情况。")
            self.open_project_button.setEnabled(False)
            self._render_badges([])
            self._render_command_badges([])
            return

        self.open_project_button.setEnabled(True)
        snapshot = inspect_project(repo_path)
        latest_run = snapshot.latest_run_dir or "暂无交付记录"
        owner_state = "有老板偏好" if snapshot.has_owner_profile else "无老板偏好"
        git_state = "Git 可用" if snapshot.is_git else "非 Git 目录"
        self.project_title.setText(snapshot.name)
        self.project_meta.setText(f"{repo_path}\n最近运行: {latest_run}\n{owner_state} / {git_state}")
        self.project_hint.setText(snapshot.hint)
        self._render_badges(
            [
                ("AGENTS.md" if snapshot.has_agents else "缺 AGENTS.md", SUCCESS if snapshot.has_agents else WARNING),
                ("Git" if snapshot.is_git else "No Git", SUCCESS if snapshot.is_git else WARNING),
                ("Owner" if snapshot.has_owner_profile else "No Owner", INFO if snapshot.has_owner_profile else SURFACE_CARD),
            ]
        )
        self._render_command_badges(snapshot.command_labels)

    def _render_command_badges(self, labels: list[str]) -> None:
        while self.commands_layout.count():
            item = self.commands_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not labels:
            self.commands_layout.addWidget(self._body("还没识别到命令闸门。"))
            self.commands_layout.addStretch(1)
            return
        for label in labels:
            self.commands_layout.addWidget(PillLabel(label, SURFACE_CARD))
        self.commands_layout.addStretch(1)

    def _compose_background(self) -> str:
        parts: list[str] = []
        background = self.background_text.toPlainText().strip()
        if background:
            parts.append(background)
        if self.chat_history:
            history = "\n".join(f"{speaker}: {text}" for speaker, text in self.chat_history[-4:])
            parts.append("最近上下文：\n" + history)
            parts.append("当前这条新任务应在上面的上下文基础上继续推进。")
        return "\n\n".join(parts)

    def submit_job(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        repo_path = Path(self.repo_input.text()).expanduser()
        if not repo_path.exists() or not repo_path.is_dir():
            QMessageBox.critical(self.window, "目录无效", "请先选择一个存在的项目文件夹。")
            return

        goal = self.goal_text.toPlainText().strip()
        if not goal:
            QMessageBox.critical(self.window, "缺少任务", "至少写一句你想让我接手的事。")
            return

        self.state.recent_repos = remember_recent_repo(self.state.recent_repos, repo_path)
        self._render_recent_repos()
        self._write_state()

        self.append_message("user", "你", goal)
        self.chat_history.append(("老板", goal))
        self.append_message("assistant", "总助", "收到。我会静默推进整条交付链，右侧同步更新收口后的摘要和工件。", tone="system")

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
        self.status_pill.set_pill("正在推进", INFO)
        self.summary_status.set_pill("状态: running", INFO)
        self.summary_review.set_pill("Reviewer: 等待中", SURFACE_CARD)
        self.summary_text.setPlainText("任务已接手，正在生成计划并推进交付。")
        self.evidence_text.setPlainText(f"项目目录: {repo_path.resolve()}\n模式: {job.mode.value}\n\n等待任务结果。")
        self.record_text.setPlainText("正在运行，请稍候...\n")
        self.chat_headline.setText("把目标交给我")
        self.chat_subheadline.setText("系统正在静默推进整条交付链。")

        self.worker = JobWorker(job)
        self.worker.result_ready.connect(self._handle_job_success)
        self.worker.error_ready.connect(self._handle_job_error)
        self.worker.finished.connect(lambda: self.send_button.setEnabled(True))
        self.worker.start()

    def _handle_job_error(self, payload: str) -> None:
        self.status_pill.set_pill("失败", FAILURE)
        self.summary_status.set_pill("状态: failed", FAILURE)
        self.append_message("assistant", "总助", payload, tone="error")
        self.summary_text.setPlainText("任务失败。请查看完整记录里的错误堆栈。")
        self.evidence_text.setPlainText("这次没有生成完整交付工件。")
        self.record_text.setPlainText(payload)
        QMessageBox.critical(self.window, "交付失败", "任务执行失败，详细堆栈已经写到结果区。")

    def _apply_record(self, record: JobRecord) -> None:
        project_name = Path(record.repo_path).name or record.repo_path
        self.status_pill.set_pill(record.status.value, _status_color(record.status.value))
        self.summary_status.set_pill(f"状态: {record.status.value}", _status_color(record.status.value))
        self.summary_mode.set_pill(f"模式: {record.mode.value}", SURFACE_CARD)
        self.summary_project.set_pill(f"项目: {project_name}", SURFACE_CARD)
        if record.delivery is not None:
            review_color = SUCCESS if record.delivery.reviewer_decision == "PASS" else WARNING
            self.summary_review.set_pill(f"Reviewer: {record.delivery.reviewer_decision}", review_color)
            self.chat_headline.setText("把目标交给我")
            self.chat_subheadline.setText(
                f"{record.delivery.summary}\n任务号 {record.job_id} / Reviewer {record.delivery.reviewer_decision} / blockers {record.delivery.reviewer_blocker_count}"
            )
        else:
            self.summary_review.set_pill("Reviewer: 未审查", SURFACE_CARD)
            self.chat_headline.setText("把目标交给我")
            self.chat_subheadline.setText(f"任务号 {record.job_id}")

        reply = format_chat_reply(record)
        self.chat_history.append(("系统", reply))
        self.append_message("assistant", "总助", reply)
        self.summary_text.setPlainText(format_boss_summary(record))
        self.evidence_text.setPlainText(format_artifact_evidence(record))
        self.record_text.setPlainText(format_job_record(record))

    def _sync_action_buttons(self) -> None:
        self.open_run_button.setEnabled(self.last_run_dir is not None and self.last_run_dir.exists())
        self.open_delivery_button.setEnabled(self.last_delivery_path is not None and self.last_delivery_path.exists())
        self.copy_summary_button.setEnabled(self.last_record is not None)

    def reset_fields(self) -> None:
        self.background_text.setPlainText(DEFAULT_BACKGROUND)
        self.offload_text.setPlainText(DEFAULT_OFFLOAD)
        self.deliverable_text.setPlainText(DEFAULT_DELIVERABLE)

    def _write_state(self) -> None:
        self.state.repo_path = self.repo_input.text().strip() or str(Path.cwd().resolve())
        self.state.goal = self.goal_text.toPlainText().strip() or DEFAULT_GOAL
        self.state.background = self.background_text.toPlainText().strip() or DEFAULT_BACKGROUND
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
