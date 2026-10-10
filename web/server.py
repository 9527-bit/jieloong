import collections
from contextlib import asynccontextmanager
import datetime
import json
import os
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Union

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
SESSION_TOKEN_FILE = os.path.join(TOKENS_DIR, ".session_token")

# --- 辅助函数 ---
def get_current_user_file() -> Optional[str]:
    """获取当前有效用户配置文件（单用户模式下取唯一配置文件）"""
    if not os.path.exists(TOKENS_DIR):
        return None
    files = [f for f in sorted(os.listdir(TOKENS_DIR)) if f.endswith(".json") and f != "example.json" and not f.startswith(".")]
    if files:
        return os.path.join(TOKENS_DIR, files[0])
    return None

def get_active_token() -> str:
    """获取当前可用的 Token（优先从配置文件中读取，其次从会话文件读取）"""
    uf = get_current_user_file()
    if uf and os.path.exists(uf):
        try:
            with open(uf, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if data.get("Token"):
                    return data["Token"].strip()
        except Exception:
            pass
    if os.path.exists(SESSION_TOKEN_FILE):
        try:
            with open(SESSION_TOKEN_FILE, "r", encoding="utf-8") as fp:
                return fp.read().strip()
        except Exception:
            pass
    return ""

def save_active_token(token: str):
    """保存或更新 Token 到会话文件以及已有用户配置文件中"""
    token = token.strip()
    try:
        with open(SESSION_TOKEN_FILE, "w", encoding="utf-8") as fp:
            fp.write(token)
    except Exception as e:
        print(f"[Dashboard] 写入会话 Token 失败: {e}")
        
    uf = get_current_user_file()
    if uf and os.path.exists(uf):
        try:
            with open(uf, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            data["Token"] = token
            with open(uf, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=4, ensure_ascii=False)
            print(f"[Dashboard] 已同步更新配置文件中的 Token: {os.path.basename(uf)}")
        except Exception as e:
            print(f"[Dashboard] 同步更新 Token 失败: {e}")

class SingleUserConfigModel(BaseModel):
    name: str
    email: Optional[str] = ""
    thread_id: int
    location_text: str
    latitude: float
    longitude: float
    token: Optional[str] = ""

# --- 页面路由 ---
@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>TaskForge Web Dashboard</h1><p>templates/index.html not found</p>"

# --- API 路由 ---
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health_check():
    return {"status": "ok", "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

@app.get("/api/config")
async def get_config():
    """获取单用户打卡配置及登录状态"""
    token = get_active_token()
    uf = get_current_user_file()
    
    config_data = {
        "has_config": False,
        "logged_in": bool(token),
        "name": "",
        "email": "",
        "thread_id": 0,
        "thread_subject": "",
        "location_text": "",
        "latitude": 23.099994,
        "longitude": 113.324520,
        "token_preview": (token[:10] + "...") if token else "",
    }
    
    if uf and os.path.exists(uf):
        try:
            username = os.path.basename(uf)[:-5]
            with open(uf, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            
            loc = data.get("Location", {})
            coords_raw = loc.get("coordinates", "{}")
            try:
                coords = json.loads(coords_raw) if isinstance(coords_raw, str) else (coords_raw or {})
            except Exception:
                coords = {}
                
            config_data.update({
                "has_config": True,
                "name": username,
                "email": data.get("Email", ""),
                "thread_id": data.get("ThreadId", 0),
                "location_text": loc.get("text", ""),
                "latitude": coords.get("latitude", 23.099994),
                "longitude": coords.get("longitude", 113.324520),
            })
        except Exception as e:
            print(f"[Dashboard] 读取配置异常: {e}")
            
    return config_data

@app.post("/api/config")
async def save_config(cfg: SingleUserConfigModel):
    """保存单用户打卡配置"""
    clean_name = cfg.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="姓名不能为空（必须与接龙打卡名单对应）")
    if not cfg.thread_id:
        raise HTTPException(status_code=400, detail="请选择或输入要打卡的接龙 ThreadId")
        
    token_to_use = cfg.token.strip() if cfg.token else get_active_token()
    
    # 清理 Tokens 目录下原有的其它用户配置，确保单用户唯一生效
    if os.path.exists(TOKENS_DIR):
        for f in os.listdir(TOKENS_DIR):
            if f.endswith(".json") and f != "example.json" and not f.startswith("."):
                fpath = os.path.join(TOKENS_DIR, f)
                if f != f"{clean_name}.json":
                    try:
                        os.remove(fpath)
                        print(f"[Dashboard] 清理旧配置文件: {f}")
                    except Exception:
                        pass
                        
    filepath = os.path.join(TOKENS_DIR, f"{clean_name}.json")
    content = {
        "Email": cfg.email.strip() if cfg.email else "",
        "Token": token_to_use,
        "ThreadId": cfg.thread_id,
        "Location": {
            "coordinates": json.dumps({
                "latitude": cfg.latitude,
                "longitude": cfg.longitude
            }),
            "text": cfg.location_text.strip()
        }
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=4, ensure_ascii=False)
        
    if token_to_use:
        save_active_token(token_to_use)
        
    print(f"[Dashboard] 单用户配置已成功保存: {clean_name}")
    return {"success": True, "message": f"用户【{clean_name}】打卡配置已成功保存！"}

@app.get("/api/favorites")
async def get_favorites():
    """从接龙管家官网 API (https://i.jielong.com/my-form?tab=5) 拉取收藏的接龙列表"""
    token = get_active_token()
    if not token:
        return {"success": False, "logged_in": False, "items": [], "error": "尚未登录微信，请先扫码登录"}
        
    url = "https://i-api.jielong.com/api/Thread/Threads?pageIndex=1&pageSize=50&listType=5"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        data = resp.json()
        if data.get("Type") == "000001":
            raw_list = data.get("Data", []) or []
            items = []
            for item in raw_list:
                if not item:
                    continue
                checkin = item.get("CheckInInfo") or {}
                items.append({
                    "id": item.get("Id"),
                    "str_id": item.get("ThreadStrId", ""),
                    "subject": item.get("Subject", "未命名接龙"),
                    "author": item.get("Author", "未知发起人"),
                    "avatar": item.get("Avatar", ""),
                    "thread_type": item.get("ThreadType", 0),
                    "special_time": item.get("SpecialTime", ""),
                    "date_created": item.get("DateCreated", ""),
                    "is_start": checkin.get("IsStart", True),
                    "is_end": checkin.get("IsEnd", False),
                    "start_time": checkin.get("StartTime", ""),
                    "end_time": checkin.get("EndTime", ""),
                })
            return {"success": True, "logged_in": True, "items": items}
        elif data.get("Type") == "000000":
            return {"success": False, "logged_in": False, "items": [], "error": data.get("Description") or "登录已过期，请重新扫码登录"}
        else:
            return {"success": False, "logged_in": True, "items": [], "error": data.get("Description") or "获取收藏列表失败"}
    except Exception as e:
        print(f"[API] 获取收藏接龙出错: {e}")
        return {"success": False, "logged_in": True, "items": [], "error": f"网络请求异常: {str(e)}"}

@app.get("/api/thread-detail")
async def get_thread_detail(thread_id: Union[int, str]):
    """获取指定接龙的详细信息及打卡花名册 (NameRange)"""
    token = get_active_token()
    url = f"https://i-api.jielong.com/api/CheckIn/Detail?threadId={thread_id}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        data = resp.json()
        thread = data.get("Data", {}).get("Thread", {})
        if thread and "ThreadId" in thread:
            raw_names = thread.get("NameRange", "")
            name_list = []
            if isinstance(raw_names, str) and raw_names.strip():
                name_list = [n.strip() for n in re.split(r'[\r\n]+', raw_names) if n.strip()]
                
            return {
                "success": True,
                "thread_id": thread["ThreadId"],
                "str_id": thread.get("ThreadStrId", str(thread_id)),
                "subject": thread.get("Subject", "未知接龙"),
                "author": thread.get("Author", "未知发起人"),
                "name_range": name_list,
                "has_name_scope": thread.get("HasNameScope", False)
            }
        else:
            raise HTTPException(status_code=404, detail="未找到该接龙或接龙已关闭")
    except Exception as e:
        print(f"[API] 获取接龙详情异常: {e}")
        raise HTTPException(status_code=500, detail=f"解析接龙详情失败: {str(e)}")

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
        token = get_active_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            thread = data.get("Data", {}).get("Thread", {})
            if thread and "ThreadId" in thread:
                raw_names = thread.get("NameRange", "")
                name_list = []
                if isinstance(raw_names, str) and raw_names.strip():
                    name_list = [n.strip() for n in re.split(r'[\r\n]+', raw_names) if n.strip()]

                return {
                    "success": True,
                    "thread_id": thread["ThreadId"],
                    "str_id": thread.get("ThreadStrId", code),
                    "subject": thread.get("Subject", "未知标题"),
                    "author": thread.get("Author", "未知发起人"),
                    "name_range": name_list
                }
    except Exception as e:
        print(f"[API] 自动解析 ThreadId 出错: {e}")

    if query.isdigit():
        return {
            "success": True,
            "thread_id": int(query),
            "str_id": query,
            "subject": f"接龙 ID: {query}",
            "author": "",
            "name_range": []
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

    uf = get_current_user_file()
    token = get_active_token()

    return {
        "server_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "has_user": bool(uf),
        "logged_in": bool(token),
        "user_name": os.path.basename(uf)[:-5] if uf else "未配置",
        "tasks": tasks_info,
        "config_modules": TaskManager.TaskManager.module_names,
    }

# --- 打卡触发 API ---
@app.post("/api/punch")
async def punch_current():
    """立即对当前配置的用户执行打卡测试"""
    uf = get_current_user_file()
    if not uf or not os.path.exists(uf):
        raise HTTPException(status_code=400, detail="未检测到已保存的用户配置，请先完善并保存配置")

    username = os.path.basename(uf)[:-5]

    def worker():
        try:
            print(f"[Dashboard] 手动触发用户【{username}】打卡...")
            自动打卡.PunchCard.PunchCard(username).Main()
        except Exception as e:
            print(f"[Dashboard] 用户【{username}】打卡异常: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return {"success": True, "message": f"用户【{username}】打卡任务已在后台启动，请查看实时日志"}

@app.post("/api/punch/{name}")
async def punch_single_user(name: str):
    return await punch_current()

@app.post("/api/punch-all")
async def punch_all():
    return await punch_current()

# --- 在线微信扫码授权流程 ---
@app.post("/api/auth/start-qr")
@app.post("/api/auth/start-qr/{name}")
async def start_qr_auth(name: Optional[str] = "User"):
    qr_getter = 自动打卡.WechatTokenWorkflow.GetQRCode()
    uuid = qr_getter.getQRCodeEV("WebAuth")
    if not uuid:
        raise HTTPException(status_code=500, detail="获取微信二维码失败，请稍后重试")

    qr_url = f"https://open.weixin.qq.com/connect/qrcode/{uuid}"
    return {
        "success": True,
        "uuid": uuid,
        "qr_url": qr_url,
        "message": "请使用微信扫描二维码登录接龙管家"
    }

@app.get("/api/auth/poll-qr")
async def poll_qr_status(uuid: str, name: Optional[str] = ""):
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
            return {"status": "waiting", "message": "等待手机微信扫码..."}
        
        if "window.wx_errcode=404" in text:
            return {"status": "scanned", "message": "已扫码！请在手机微信上点击【允许/确认登录】"}

        if "window.wx_code" in text and "window.wx_code=''" not in text:
            match = re.search(r"window\.wx_code='([^']*)'", text)
            if match:
                wx_code = match.group(1)
                print(f"[WebAuth] 成功捕获 wx_code: {wx_code}")
                # 换取 Token
                auth_worker = 自动打卡.WechatTokenWorkflow.GetAuthorization(wx_code)
                token = auth_worker.getToken("WebAuth")
                if token:
                    save_active_token(token)
                    return {"status": "success", "token": token, "message": "🎉 微信授权成功！已绑定登录"}
                else:
                    return {"status": "error", "message": "获取 Token 失败，请重试"}

        if "window.wx_errcode=403" in text or "window.wx_errcode=402" in text:
            return {"status": "expired", "message": "二维码已失效，请重新生成"}

        return {"status": "waiting", "message": "等待扫码..."}
    except Exception as e:
        return {"status": "waiting", "message": f"网络轮询中... ({e})"}

@app.post("/api/logout")
async def logout():
    """退出登录"""
    if os.path.exists(SESSION_TOKEN_FILE):
        try:
            os.remove(SESSION_TOKEN_FILE)
        except Exception:
            pass
    uf = get_current_user_file()
    if uf and os.path.exists(uf):
        try:
            with open(uf, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            data["Token"] = ""
            with open(uf, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=4, ensure_ascii=False)
        except Exception:
            pass
    print("[Dashboard] 用户已退出登录，Token 已清除")
    return {"success": True, "message": "已退出登录"}

# --- 兼容老接口 ---
@app.get("/api/users")
async def list_users():
    cfg = await get_config()
    if cfg["has_config"]:
        return [{
            "name": cfg["name"],
            "email": cfg["email"],
            "has_token": bool(cfg["token_preview"]),
            "token_preview": cfg["token_preview"],
            "thread_id": cfg["thread_id"],
            "location_text": cfg["location_text"],
            "latitude": cfg["latitude"],
            "longitude": cfg["longitude"],
        }]
    return []

@app.post("/api/users")
async def save_user_compat(config: SingleUserConfigModel):
    return await save_config(config)

@app.delete("/api/users/{name}")
async def delete_user(name: str):
    filepath = os.path.join(TOKENS_DIR, f"{name}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
        print(f"[Dashboard] 用户配置已删除: {name}")
        return {"success": True, "message": f"已删除用户 {name}"}
    raise HTTPException(status_code=404, detail="用户不存在")

# --- 实时日志流 ---
@app.get("/api/logs")
async def get_logs():
    return list(log_capture.logs)
