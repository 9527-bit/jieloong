import collections
from contextlib import asynccontextmanager
import datetime
import json
import os
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests

import TaskManager
import 自动打卡.MainRun
import 自动打卡.PunchCard
import 自动打卡.WechatTokenWorkflow

# 日志环形缓冲区
class LogCapture:
    def __init__(self, capacity: int = 500):
        self.logs = collections.deque(maxlen=capacity)
        self.terminal = sys.stdout

    def write(self, message: str):
        if self.terminal:
            self.terminal.write(message)
        clean = message.strip()
        if clean:
            self.logs.append({
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "text": clean
            })

    def flush(self):
        if self.terminal:
            self.terminal.flush()

log_capture = LogCapture()
sys.stdout = log_capture

# 启动后台任务调度器
def start_background_scheduler():
    try:
        print("[System] 正在后台启动 TaskForge 任务调度引擎...")
        TaskManager.TaskManager.Run()
    except Exception as e:
        print(f"[System] 调度引擎异常退出: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动后台守护线程
    t = threading.Thread(target=start_background_scheduler, daemon=True)
    t.start()
    yield
    print("[System] Web 服务正在关闭...")

app = FastAPI(title="TaskForge Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOKENS_DIR = "自动打卡/Tokens"
os.makedirs(TOKENS_DIR, exist_ok=True)

class UserConfigModel(BaseModel):
    name: str
    email: str
    thread_id: int
    location_text: str
    latitude: float
    longitude: float
    token: Optional[str] = ""

# --- 页面路由 ---
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>TaskForge Web Dashboard</h1><p>templates/index.html not found</p>"

# --- API 路由 ---
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

@app.get("/api/resolve-thread")
async def resolve_thread(query: str):
    """自动将网页链接 (https://i.jielong.com/c/1WVD88CV8F) 或短码自动解析为纯数字 ThreadId"""
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入接龙链接或编号")

    code = query
    match_c = re.search(r"/c/([a-zA-Z0-9]+)", query)
    if match_c:
        code = match_c.group(1)
    else:
        match_id = re.search(r"threadId=([a-zA-Z0-9]+)", query, re.IGNORECASE)
        if match_id:
            code = match_id.group(1)

    try:
        url = f"https://i-api.jielong.com/api/CheckIn/Detail?threadId={code}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            thread = data.get("Data", {}).get("Thread", {})
            if thread and "ThreadId" in thread:
                return {
                    "success": True,
                    "thread_id": thread["ThreadId"],
                    "str_id": thread.get("ThreadStrId", code),
                    "subject": thread.get("Subject", "未知标题"),
                    "author": thread.get("Author", "未知发起人")
                }
    except Exception as e:
        print(f"[API] 自动解析 ThreadId 出错: {e}")

    if query.isdigit():
        return {
            "success": True,
            "thread_id": int(query),
            "str_id": query,
            "subject": f"接龙 ID: {query}",
            "author": ""
        }

    raise HTTPException(status_code=400, detail="未能自动解析该接龙，请检查链接或直接输入纯数字 ID")

@app.get("/api/status")
async def get_status():
    tasks_info = []
    for t in TaskManager.TaskManager.task_group:
        tasks_info.append({
            "name": t.name,
            "module": t.Name,
            "frequency_days": t.frequency,
            "start_time": str(t.start_time),
            "next_run_time": str(t.next_run_time),
            "count": t.count,
        })

    # 读取用户总数
    user_files = [f for f in os.listdir(TOKENS_DIR) if f.endswith(".json") and f != "example.json"]

    return {
        "server_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_users": len(user_files),
        "tasks": tasks_info,
        "config_modules": TaskManager.TaskManager.module_names,
    }

@app.get("/api/users")
async def list_users():
    users = []
    if os.path.exists(TOKENS_DIR):
        for f in sorted(os.listdir(TOKENS_DIR)):
            if f.endswith(".json") and f != "example.json":
                username = f[:-5]
                filepath = os.path.join(TOKENS_DIR, f)
                try:
                    with open(filepath, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    
                    loc = data.get("Location", {})
                    coords_raw = loc.get("coordinates", "{}")
                    try:
                        coords = json.loads(coords_raw) if isinstance(coords_raw, str) else coords_raw
                    except Exception:
                        coords = {}

                    users.append({
                        "name": username,
                        "email": data.get("Email", ""),
                        "has_token": bool(data.get("Token")),
                        "token_preview": (data.get("Token")[:10] + "...") if data.get("Token") else "未获取",
                        "thread_id": data.get("ThreadId", 0),
                        "location_text": loc.get("text", ""),
                        "latitude": coords.get("latitude", 0.0),
                        "longitude": coords.get("longitude", 0.0),
                    })
                except Exception as e:
                    users.append({
                        "name": username,
                        "error": f"解析失败: {str(e)}"
                    })
    return users

@app.post("/api/users")
async def save_user(config: UserConfigModel):
    filepath = os.path.join(TOKENS_DIR, f"{config.name}.json")
    
    # 保留旧 token 如果未传入新 token
    existing_token = config.token or ""
    if not existing_token and os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                old = json.load(f)
                existing_token = old.get("Token", "")
        except Exception:
            pass

    content = {
        "Email": config.email,
        "Token": existing_token,
        "ThreadId": config.thread_id,
        "Location": {
            "coordinates": json.dumps({
                "latitude": config.latitude,
                "longitude": config.longitude
            }),
            "text": config.location_text
        }
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=4, ensure_ascii=False)

    print(f"[Dashboard] 用户配置已保存: {config.name}")
    return {"success": True, "message": f"用户 {config.name} 配置已保存"}

@app.delete("/api/users/{name}")
async def delete_user(name: str):
    filepath = os.path.join(TOKENS_DIR, f"{name}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
        print(f"[Dashboard] 用户配置已删除: {name}")
        return {"success": True, "message": f"已删除用户 {name}"}
    raise HTTPException(status_code=404, detail="用户不存在")

# --- 打卡触发 API ---
@app.post("/api/punch/{name}")
async def punch_single_user(name: str):
    filepath = os.path.join(TOKENS_DIR, f"{name}.json")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"未找到用户 {name} 的配置文件")

    def worker():
        try:
            print(f"[Dashboard] 手动触发用户 {name} 打卡...")
            自动打卡.PunchCard.PunchCard(name).Main()
        except Exception as e:
            print(f"[Dashboard] 用户 {name} 打卡异常: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return {"success": True, "message": f"用户 {name} 的打卡任务已在后台启动，请查看日志"}

@app.post("/api/punch-all")
async def punch_all():
    def worker():
        try:
            print("[Dashboard] 手动触发全员打卡任务...")
            自动打卡.MainRun.main()
        except Exception as e:
            print(f"[Dashboard] 全员打卡异常: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return {"success": True, "message": "全员打卡任务已在后台启动，请查看实时日志"}

# --- 在线微信扫码授权流程 ---
@app.post("/api/auth/start-qr/{name}")
async def start_qr_auth(name: str):
    filepath = os.path.join(TOKENS_DIR, f"{name}.json")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"用户 {name} 不存在")

    qr_getter = 自动打卡.WechatTokenWorkflow.GetQRCode()
    uuid = qr_getter.getQRCodeEV(f"WebAuth-{name}")
    if not uuid:
        raise HTTPException(status_code=500, detail="获取微信二维码失败，请稍后重试")

    qr_url = f"https://open.weixin.qq.com/connect/qrcode/{uuid}"
    return {
        "success": True,
        "uuid": uuid,
        "qr_url": qr_url,
        "name": name,
        "message": "请使用微信扫描二维码"
    }

@app.get("/api/auth/poll-qr")
async def poll_qr_status(uuid: str, name: str):
    timestamp = int(time.time() * 1000)
    url = f"https://lp.open.weixin.qq.com/connect/l/qrconnect?uuid={uuid}&last=404&_={timestamp}"
    headers = {
        "Host": "lp.open.weixin.qq.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.95 Safari/537.36",
        "Referer": "https://open.weixin.qq.com/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=8)
        text = resp.text

        if "window.wx_errcode=408" in text:
            return {"status": "waiting", "message": "等待手机扫码授权..."}
        
        if "window.wx_errcode=404" in text:
            return {"status": "scanned", "message": "已扫码！请在手机微信上点击【允许/确认登录】"}

        if "window.wx_code" in text and "window.wx_code=''" not in text:
            match = re.search(r"window\.wx_code='([^']*)'", text)
            if match:
                wx_code = match.group(1)
                print(f"[WebAuth-{name}] 成功捕获 wx_code: {wx_code}")
                # 换取 Token
                auth_worker = 自动打卡.WechatTokenWorkflow.GetAuthorization(wx_code)
                token = auth_worker.getToken(f"WebAuth-{name}")
                if token:
                    # 写入用户 json
                    punch = 自动打卡.PunchCard.PunchCard(name)
                    punch.UpdataJsonToken(token)
                    print(f"[WebAuth-{name}] Token 已成功保存至用户 {name}.json")
                    return {"status": "success", "message": "🎉 微信授权成功！Token 已自动更新保存"}
                else:
                    return {"status": "error", "message": "获取 Token 失败，请重试"}

        if "window.wx_errcode=403" in text or "window.wx_errcode=402" in text:
            return {"status": "expired", "message": "二维码已失效，请重新生成"}

        return {"status": "waiting", "message": "等待扫码..."}
    except Exception as e:
        return {"status": "waiting", "message": f"网络轮询中... ({e})"}

# --- 实时日志流 ---
@app.get("/api/logs")
async def get_logs():
    return list(log_capture.logs)
