#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TaskForge - 系统已存打卡配置查询工具
用法:
  python3 list_users.py
或在 Docker 容器中执行:
  docker compose exec taskforge python3 list_users.py
"""

import datetime
import json
import os
import sys

TOKENS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "自动打卡", "Tokens")

def format_time(ts):
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "未知"

def main():
    print("\n" + "=" * 76)
    print("           📋  TaskForge - 系统已存打卡配置列表")
    print("=" * 76)

    if not os.path.exists(TOKENS_DIR):
        print(f"❌ 未找到配置目录: {TOKENS_DIR}")
        print("=" * 76 + "\n")
        return

    files = [
        f for f in sorted(os.listdir(TOKENS_DIR))
        if f.endswith(".json") and f != "example.json" and not f.startswith(".")
    ]

    if not files:
        print("ℹ️  当前系统暂无已保存的用户打卡配置。")
        print("   (用户可在 Web 页面微信扫码授权后保存打卡设置，或在 Tokens 目录创建 [姓名].json)")
        print("=" * 76 + "\n")
        return

    print(f"✅ 系统当前共有 {len(files)} 位已配置自动打卡的用户:\n")

    for idx, fname in enumerate(files, 1):
        username = fname[:-5]
        fpath = os.path.join(TOKENS_DIR, fname)
        mtime = os.path.getmtime(fpath)

        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception as e:
            print(f"[{idx}] 用户: {username} (⚠️ 读取配置文件失败: {e})")
            continue

        thread_id = data.get("ThreadId", 0)
        token = (data.get("Token") or "").strip()
        email = (data.get("Email") or "").strip()
        loc = data.get("Location", {})
        loc_text = loc.get("text", "未指定位置")
        coords_raw = loc.get("coordinates", "{}")
        try:
            coords = json.loads(coords_raw) if isinstance(coords_raw, str) else (coords_raw or {})
        except Exception:
            coords = {}

        lat = coords.get("latitude", "N/A")
        lng = coords.get("longitude", "N/A")

        token_status = "✅ 已配置 (" + token[:10] + "...)" if token else "❌ 未配置或已失效"
        email_status = email if email else "（未配置通知邮箱）"

        status_val = data.get("Status", "active")
        fail_cnt = data.get("FailCount", 0)
        last_err = data.get("LastError", "")
        last_success = data.get("LastSuccessTime", "无记录")
        last_fail = data.get("LastFailTime", "无记录")

        if status_val == "paused":
            run_status = f"⏸️ 已自动暂停打卡 (连续失败 {fail_cnt} 次: {last_err or 'Token失效或多次错误'})"
        else:
            run_status = "✅ 正常打卡 (active)"
            if fail_cnt > 0:
                run_status += f" [注意: 近期失败 {fail_cnt} 次: {last_err}]"

        print(f"【{idx}】打卡用户: {username}")
        print(f"    • 调度运行状态       : {run_status}")
        print(f"    • 接龙编号 (ThreadId) : {thread_id}")
        print(f"    • 打卡地点名称       : {loc_text}")
        print(f"    • 坐标 (经度, 纬度)   : {lng}, {lat}")
        print(f"    • 微信 Token 凭证     : {token_status}")
        print(f"    • 提醒邮箱           : {email_status}")
        print(f"    • 最近打卡记录       : 成功: {last_success} | 失败: {last_fail}")
        print(f"    • 配置文件路径       : 自动打卡/Tokens/{fname}")
        print(f"    • 最近配置修改时间   : {format_time(mtime)}")
        print("-" * 76)

    print("\n💡 常用管理命令提示:")
    print("  • 立即测试单人打卡: python3 -c \"import 自动打卡.PunchCard; 自动打卡.PunchCard.PunchCard('姓名').Main()\"")
    print("  • 立即触发全部打卡: python3 -c \"import 自动打卡.MainRun; 自动打卡.MainRun.main()\"")
    print("  • 查看打卡后台日志: docker compose logs -f 或在 Web 页面控制台查看")
    print("=" * 76 + "\n")

if __name__ == "__main__":
    main()
