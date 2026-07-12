"""本地投递记录管理器（可编辑）。

部署到 gh-pages 的报告是只读的；本地双击「管理.bat」起这个 Flask 服务，
同一套页面会冒出编辑控件（我投了 / 改阶段 / 手动添加 / 删除），写回 data/applications.json。
纯本地运行、永不部署，不影响 CI 与静态报告。

录入/改动投递后会**自动**把 data/applications.json 提交并推送到 origin/main，
触发 sync_report 工作流，手机端几分钟内即可看到（设 WEBAPP_AUTO_SYNC=0 可关闭）。

用法：
    python webapp.py
"""

import os
import shutil
import subprocess
import threading
import webbrowser
from datetime import date, datetime
from pathlib import Path

from flask import Flask, redirect, request

import db as db_module
import reporter

_ROOT = Path(__file__).parent
DB_PATH = str(_ROOT / "data" / "jobs.db")
_PORT = 5000

# 自动把投递记录推到远端（让手机端的报告同步）。设 WEBAPP_AUTO_SYNC=0 关闭。
_AUTO_SYNC = os.environ.get("WEBAPP_AUTO_SYNC", "1") != "0"
_APPS_REL = "data/applications.json"
_sync_lock = threading.Lock()

app = Flask(__name__)


def _conn():
    return db_module.init_db(DB_PATH)


def _run_git(args, timeout=120):
    """跑一条 git 子命令（非交互、不弹编辑器/凭据框）。"""
    env = {**os.environ, "GIT_EDITOR": "true", "GIT_TERMINAL_PROMPT": "0"}
    # 强制 UTF-8 解码：Windows 默认 locale 是 GBK，git 输出含 UTF-8 字节会解码崩溃。
    return subprocess.run(
        ["git", *args], cwd=str(_ROOT), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )


def _git_sync():
    """提交并推送 data/applications.json 到 origin/main。

    严格遵守 CLAUDE.md「Git 工作流」：用 git pull(merge) + push，**不 rebase**。
    只 `git add` applications.json——投递记录已与 jobs.db 解耦，正常情况下不碰 db、
    不会覆盖云端当天爬取（仅当你本地另跑过 main.py 改了 db 才会触发 db 的 merge=ours）。
    任何失败都只打印提示、保留本地提交，绝不做破坏性操作。
    """
    if not _AUTO_SYNC:
        return
    if shutil.which("git") is None:
        print("[sync] 未找到 git，跳过自动推送（可手动 push data/applications.json）")
        return
    with _sync_lock:
        try:
            if _run_git(["rev-parse", "--is-inside-work-tree"]).returncode != 0:
                print("[sync] 不在 git 仓库内，跳过自动推送")
                return
            _run_git(["add", _APPS_REL])
            if _run_git(["diff", "--cached", "--quiet"]).returncode == 0:
                return  # 无改动，无需提交
            msg = f"chore(apps): 更新投递记录 {datetime.now():%Y-%m-%d %H:%M}"
            r = _run_git(["commit", "-m", msg])
            if r.returncode != 0:
                print("[sync] commit 失败：", r.stderr.strip())
                return
            r = _run_git(["pull", "--no-rebase", "--no-edit", "origin", "main"])
            if r.returncode != 0:
                print("[sync] pull 失败（已本地提交，稍后手动 push）：", (r.stderr or r.stdout).strip())
                return
            r = _run_git(["push", "origin", "main"])
            if r.returncode != 0:
                print("[sync] push 失败（已本地提交，检查网络/凭据后手动 push）：", (r.stderr or r.stdout).strip())
                return
            print("[sync] ✅ 已推送投递记录，手机端几分钟内更新")
        except subprocess.TimeoutExpired:
            print("[sync] git 超时（已本地提交，稍后手动 push）")
        except Exception as e:  # noqa: BLE001 — 后台线程，任何异常都不应崩进程
            print("[sync] 异常（已本地提交，稍后手动 push）：", e)


def _schedule_sync():
    """后台线程跑 git 同步，不阻塞页面响应。"""
    threading.Thread(target=_git_sync, daemon=True).start()


@app.route("/")
def index():
    conn = _conn()
    try:
        data = {
            "items": db_module.get_all_jobs_with_analysis(conn),
            "applications": db_module.get_applications(conn),
            "date": date.today().isoformat(),
        }
    finally:
        conn.close()
    return reporter.render_html(date.today().isoformat(), data, editable=True)


@app.route("/apply", methods=["POST"])
def apply():
    job_id = request.form.get("job_id", type=int)
    conn = _conn()
    try:
        db_module.upsert_application(
            conn,
            job_id,
            request.form.get("company", ""),
            request.form.get("title", ""),
            request.form.get("city", ""),
        )
    finally:
        conn.close()
    _schedule_sync()  # 后台自动提交+推送 applications.json → 手机端同步
    return redirect("/#applications")


@app.route("/application/new", methods=["POST"])
def application_new():
    conn = _conn()
    try:
        db_module.add_manual_application(
            conn,
            request.form.get("company", "").strip(),
            request.form.get("title", "").strip(),
            request.form.get("city", "").strip(),
        )
    finally:
        conn.close()
    _schedule_sync()  # 后台自动提交+推送 applications.json → 手机端同步
    return redirect("/#applications")


@app.route("/application/<int:app_id>/stage", methods=["POST"])
def application_stage(app_id):
    conn = _conn()
    try:
        db_module.update_application_stage(
            conn,
            app_id,
            request.form.get("stage", ""),
            request.form.get("result", "待"),
            request.form.get("note", ""),
        )
    finally:
        conn.close()
    _schedule_sync()  # 后台自动提交+推送 applications.json → 手机端同步
    return redirect("/#applications")


@app.route("/application/<int:app_id>/event", methods=["POST"])
def application_event(app_id):
    conn = _conn()
    try:
        db_module.add_application_event(
            conn,
            app_id,
            request.form.get("event_type", ""),
            request.form.get("event_date", ""),
            request.form.get("event_time", ""),
            request.form.get("note", ""),
        )
    finally:
        conn.close()
    _schedule_sync()  # 后台自动提交+推送 applications.json → 手机端同步
    return redirect("/#schedule")


@app.route("/application/<int:app_id>/event/<int:event_id>/delete", methods=["POST"])
def application_event_delete(app_id, event_id):
    conn = _conn()
    try:
        db_module.delete_application_event(conn, app_id, event_id)
    finally:
        conn.close()
    _schedule_sync()  # 后台自动提交+推送 applications.json → 手机端同步
    return redirect("/#schedule")


@app.route("/application/<int:app_id>/delete", methods=["POST"])
def application_delete(app_id):
    conn = _conn()
    try:
        db_module.delete_application(conn, app_id)
    finally:
        conn.close()
    _schedule_sync()  # 后台自动提交+推送 applications.json → 手机端同步
    return redirect("/#applications")


def main():
    url = f"http://localhost:{_PORT}/"
    # 开自动重载：改任何 .py（含 reporter.py）服务自动重启，无需手动关窗重开。
    # 重载器把脚本跑两次（监视父进程 + 真正服务的子进程）；只在子进程
    # （WERKZEUG_RUN_MAIN=true，即真正绑定端口的那个）里打印+弹一次浏览器。
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        print(f"投递记录管理器已启动：{url}")
        sync_state = "开" if _AUTO_SYNC else "关（WEBAPP_AUTO_SYNC=0）"
        print(f"录入/更新投递会自动推送到远端、同步到手机端，无需手动 commit。自动同步：{sync_state}")
        print("关闭此窗口即停止。")
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=_PORT, debug=False, use_reloader=True)


if __name__ == "__main__":
    main()
