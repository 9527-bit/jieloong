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
import uuid

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
SESSIONS_FILE = os.path.join(TOKENS_DIR, ".sessions.json")
_sessions_lock = threading.Lock()
_qr_session_map: Dict[str, str] = {}  # uuid -> sid

# --- 会话持久化与用户隔离支持 ---
def load_sessions() -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(SESSIONS_FILE):
        return {}
    try:
        with open(SESSIONS_FILE, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception as e:
        print(f"[Dashboard] 读取会话存储异常: {e}")
        return {}

def save_sessions(sessions: Dict[str, Dict[str, Any]]):
    try:
        with open(SESSIONS_FILE, "w", encoding="utf-8") as fp:
            json.dump(sessions, fp, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Dashboard] 写入会话存储异常: {e}")

def get_session_id(request: Request) -> str:
    """提取客户端会话 ID（支持 Header、Cookie、Query Param）"""
    sid = request.headers.get("x-session-id", "").strip()
    if not sid:
        sid = request.cookies.get("taskforge_sid", "").strip()
    if not sid:
        sid = request.query_params.get("sid", "").strip()
    if not sid:
        sid = "sid_" + uuid.uuid4().hex[:16]
    return sid

def get_session(sid: str) -> Dict[str, Any]:
    if not sid:
        return {}
    with _sessions_lock:
        sessions = load_sessions()
        return sessions.get(sid, {})

def update_session(sid: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    if not sid:
        return {}
    with _sessions_lock:
        sessions = load_sessions()
        sess = sessions.setdefault(sid, {
            "token": "",
            "user_name": "",
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        sess.update(updates)
        sess["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_sessions(sessions)
        return sess

def get_all_user_names() -> List[str]:
    """获取系统中所有已保存的用户配置名列表"""
    if not os.path.exists(TOKENS_DIR):
        return []
    return sorted([
        f[:-5] for f in os.listdir(TOKENS_DIR)
        if f.endswith(".json") and f != "example.json" and not f.startswith(".")
    ])

def get_user_file_for_session(sess: Dict[str, Any]) -> Optional[str]:
    """获取当前会话绑定的用户配置文件"""
    user_name = (sess.get("user_name") or "").strip()
    if user_name:
        fpath = os.path.join(TOKENS_DIR, f"{user_name}.json")
        if os.path.exists(fpath):
            return fpath
    return None

def get_session_token(sess: Dict[str, Any]) -> str:
    """获取当前会话有效的 Token（优先从用户配置文件同步，其次取会话保存的 Token）"""
    uf = get_user_file_for_session(sess)
    if uf and os.path.exists(uf):
        try:
            with open(uf, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                file_token = (data.get("Token") or "").strip()
                if file_token:
                    return file_token
        except Exception:
            pass
    return (sess.get("token") or "").strip()

# --- Pydantic 模型 ---
class SingleUserConfigModel(BaseModel):
    name: str
    email: Optional[str] = ""
    thread_id: int
    location_text: str
    latitude: float
    longitude: float
    token: Optional[str] = ""

class SwitchUserModel(BaseModel):
    name: str

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
async def get_config(request: Request):
    """获取当前会话关联用户的打卡配置及登录状态（实现多用户隔离）"""
    sid = get_session_id(request)
    sess = get_session(sid)
    token = get_session_token(sess)
    uf = get_user_file_for_session(sess)
    all_users = get_all_user_names()

    config_data = {
        "session_id": sid,
        "has_config": False,
        "logged_in": bool(token),
        "name": sess.get("user_name", ""),
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
            print(f"[Dashboard] 读取会话【{sid[:8]}】配置异常: {e}")

    resp = JSONResponse(content=config_data)
    resp.set_cookie("taskforge_sid", sid, max_age=31536000, samesite="lax")
    return resp

@app.post("/api/config")
async def save_config(request: Request, cfg: SingleUserConfigModel):
    """保存用户打卡配置（隔离多用户，保存不覆盖其它用户文件）"""
    sid = get_session_id(request)
    sess = get_session(sid)

    clean_name = cfg.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="姓名不能为空（必须与接龙打卡名单对应）")
    if not cfg.thread_id:
        raise HTTPException(status_code=400, detail="请选择或输入要打卡的接龙 ThreadId")

    token_to_use = cfg.token.strip() if cfg.token else get_session_token(sess)

    # 保存到对应用户的 JSON 文件（保留所有其它用户文件，保障多用户并存）
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

    # 将当前会话绑定到该用户名及 Token
    update_session(sid, {
        "user_name": clean_name,
        "token": token_to_use
    })

    print(f"[Dashboard] 会话【{sid[:8]}】已成功保存用户配置: {clean_name}")
    resp = JSONResponse(content={"success": True, "message": f"用户【{clean_name}】打卡配置已成功保存！"})
    resp.set_cookie("taskforge_sid", sid, max_age=31536000, samesite="lax")
    return resp

@app.post("/api/session/switch-user")
async def switch_user(request: Request, body: SwitchUserModel):
    """切换当前客户端会话绑定的用户配置"""
    sid = get_session_id(request)
    target_name = body.name.strip()
    fpath = os.path.join(TOKENS_DIR, f"{target_name}.json")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail=f"未找到用户【{target_name}】的配置文件")

    token = ""
    try:
        with open(fpath, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            token = (data.get("Token") or "").strip()
    except Exception:
        pass

    update_session(sid, {
        "user_name": target_name,
        "token": token
    })
    print(f"[Dashboard] 会话【{sid[:8]}】切换至已保存用户: {target_name}")
    resp = JSONResponse(content={"success": True, "message": f"已切换至用户【{target_name}】"})
    resp.set_cookie("taskforge_sid", sid, max_age=31536000, samesite="lax")
    return resp

@app.post("/api/session/new-user")
async def new_user_session(request: Request):
    """当前客户端会话解绑用户名（准备录入新用户的独立配置）"""
    sid = get_session_id(request)
    update_session(sid, {
        "user_name": "",
        "token": ""
    })
    resp = JSONResponse(content={"success": True, "message": "已就绪，可录入新用户配置"})
    resp.set_cookie("taskforge_sid", sid, max_age=31536000, samesite="lax")
    return resp

@app.get("/api/favorites")
async def get_favorites(request: Request):
    """从接龙管家官网 API (https://i.jielong.com/my-form?tab=5) 拉取当前登录用户的收藏列表"""
    sid = get_session_id(request)
    sess = get_session(sid)
    token = get_session_token(sess)
    if not token:
        return {"success": False, "logged_in": False, "items": [], "error": "当前账号尚未登录微信，请先扫码登录"}

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
async def get_thread_detail(request: Request, thread_id: Union[int, str]):
    """获取指定接龙的详细信息及打卡花名册 (NameRange)"""
    sid = get_session_id(request)
    sess = get_session(sid)
    token = get_session_token(sess)

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

            pos_setting = thread.get("PositionSetting")
            has_pos = thread.get("HasPositionSetting", False) or bool(pos_setting)
            return {
                "success": True,
                "thread_id": thread["ThreadId"],
                "str_id": thread.get("ThreadStrId", str(thread_id)),
                "subject": thread.get("Subject", "未知接龙"),
                "author": thread.get("Author", "未知发起人"),
                "name_range": name_list,
                "has_name_scope": thread.get("HasNameScope", False),
                "has_position_setting": has_pos,
                "position_setting": pos_setting
            }
        else:
            raise HTTPException(status_code=404, detail="未找到该接龙或接龙已关闭")
    except Exception as e:
        print(f"[API] 获取接龙详情异常: {e}")
        raise HTTPException(status_code=500, detail=f"解析接龙详情失败: {str(e)}")

@app.get("/api/resolve-thread")
async def resolve_thread(request: Request, query: str):
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
        sid = get_session_id(request)
        sess = get_session(sid)
        token = get_session_token(sess)
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
async def get_status(request: Request):
    """获取调度引擎运行状态及当前会话信息"""
    sid = get_session_id(request)
    sess = get_session(sid)
    token = get_session_token(sess)
    user_name = sess.get("user_name") or "未绑定"
    all_users = get_all_user_names()

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

    return {
        "server_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "session_id": sid[:8] + "...",
        "has_user": bool(user_name and user_name != "未绑定"),
        "logged_in": bool(token),
        "user_name": user_name,
        "total_users": len(all_users),
        "tasks": tasks_info,
        "config_modules": TaskManager.TaskManager.module_names,
    }

# --- 打卡触发 API ---
@app.post("/api/punch")
async def punch_current(request: Request):
    """立即对当前会话绑定的用户执行打卡测试（实现按用户隔离触发）"""
    sid = get_session_id(request)
    sess = get_session(sid)
    username = (sess.get("user_name") or "").strip()

    if not username:
        all_users = get_all_user_names()
        if len(all_users) == 1:
            username = all_users[0]
            update_session(sid, {"user_name": username})
        else:
            raise HTTPException(status_code=400, detail="当前会话尚未绑定打卡用户，请先保存配置或选择用户")

    uf = os.path.join(TOKENS_DIR, f"{username}.json")
    if not os.path.exists(uf):
        raise HTTPException(status_code=400, detail=f"未找到用户【{username}】的配置文件，请先完善并保存配置")

    def worker(uname: str):
        try:
            print(f"[Dashboard] 手动触发用户【{uname}】打卡...")
            自动打卡.PunchCard.PunchCard(uname).Main()
        except Exception as e:
            print(f"[Dashboard] 用户【{uname}】打卡异常: {e}")

    threading.Thread(target=worker, args=(username,), daemon=True).start()
    return {"success": True, "message": f"用户【{username}】打卡任务已在后台启动，请查看实时日志"}

@app.post("/api/punch/{name}")
async def punch_single_user(name: str):
    """触发指定用户的打卡测试"""
    clean_name = name.strip()
    uf = os.path.join(TOKENS_DIR, f"{clean_name}.json")
    if not os.path.exists(uf):
        raise HTTPException(status_code=404, detail=f"未找到用户【{clean_name}】的配置文件")

    def worker(uname: str):
        try:
            print(f"[Dashboard] 手动触发指定用户【{uname}】打卡...")
            自动打卡.PunchCard.PunchCard(uname).Main()
        except Exception as e:
            print(f"[Dashboard] 用户【{uname}】打卡异常: {e}")

    threading.Thread(target=worker, args=(clean_name,), daemon=True).start()
    return {"success": True, "message": f"用户【{clean_name}】打卡任务已在后台启动，请查看实时日志"}

@app.post("/api/punch-all")
async def punch_all(request: Request):
    return await punch_current(request)

# --- 在线微信扫码授权流程（按 Session 隔离） ---
@app.post("/api/auth/start-qr")
@app.post("/api/auth/start-qr/{name}")
async def start_qr_auth(request: Request, name: Optional[str] = "User"):
    sid = get_session_id(request)
    qr_getter = 自动打卡.WechatTokenWorkflow.GetQRCode()
    uuid_val = qr_getter.getQRCodeEV(f"WebAuth-{sid[:8]}")
    if not uuid_val:
        raise HTTPException(status_code=500, detail="获取微信二维码失败，请稍后重试")

    _qr_session_map[uuid_val] = sid
    qr_url = f"https://open.weixin.qq.com/connect/qrcode/{uuid_val}"
    resp = JSONResponse(content={
        "success": True,
        "uuid": uuid_val,
        "qr_url": qr_url,
        "session_id": sid,
        "message": "请使用微信扫描二维码登录接龙管家"
    })
    resp.set_cookie("taskforge_sid", sid, max_age=31536000, samesite="lax")
    return resp

@app.get("/api/auth/poll-qr")
async def poll_qr_status(request: Request, uuid: str):
    sid = get_session_id(request)
    if not sid or sid not in load_sessions():
        sid = _qr_session_map.get(uuid, sid)

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
                print(f"[WebAuth-{sid[:8]}] 成功捕获 wx_code: {wx_code}")
                # 换取 Token
                auth_worker = 自动打卡.WechatTokenWorkflow.GetAuthorization(wx_code)
                token = auth_worker.getToken(f"WebAuth-{sid[:8]}")
                if token:
                    sess = update_session(sid, {"token": token})
                    # 若该会话已绑定了用户文件，同步更新该文件的 Token
                    if sess.get("user_name"):
                        uf = os.path.join(TOKENS_DIR, f"{sess['user_name']}.json")
                        if os.path.exists(uf):
                            try:
                                with open(uf, "r", encoding="utf-8") as fp:
                                    udata = json.load(fp)
                                udata["Token"] = token
                                with open(uf, "w", encoding="utf-8") as fp:
                                    json.dump(udata, fp, indent=4, ensure_ascii=False)
                                print(f"[WebAuth-{sid[:8]}] 同步更新用户【{sess['user_name']}】的 Token")
                            except Exception as e:
                                print(f"[WebAuth] 同步更新用户文件失败: {e}")

                    _qr_session_map.pop(uuid, None)
                    resp = JSONResponse(content={"status": "success", "token": token, "message": "🎉 微信授权成功！已绑定当前用户"})
                    resp.set_cookie("taskforge_sid", sid, max_age=31536000, samesite="lax")
                    return resp
                else:
                    return {"status": "error", "message": "获取 Token 失败，请重试"}

        if "window.wx_errcode=403" in text or "window.wx_errcode=402" in text:
            _qr_session_map.pop(uuid, None)
            return {"status": "expired", "message": "二维码已失效，请重新生成"}

        return {"status": "waiting", "message": "等待扫码..."}
    except Exception as e:
        return {"status": "waiting", "message": f"网络轮询中... ({e})"}

@app.post("/api/logout")
async def logout(request: Request):
    """退出当前会话的微信登录状态"""
    sid = get_session_id(request)
    update_session(sid, {"token": ""})
    print(f"[Dashboard] 会话【{sid[:8]}】已退出登录，Token 已清除")
    resp = JSONResponse(content={"success": True, "message": "已退出登录"})
    resp.set_cookie("taskforge_sid", sid, max_age=31536000, samesite="lax")
    return resp

# --- 多用户列表与兼容接口 ---
@app.get("/api/users")
async def list_users():
    """获取系统中所有已保存的用户打卡概要"""
    all_users = get_all_user_names()
    user_list = []
    for u in all_users:
        fpath = os.path.join(TOKENS_DIR, f"{u}.json")
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            token = (data.get("Token") or "").strip()
            loc = data.get("Location", {})
            coords_raw = loc.get("coordinates", "{}")
            try:
                coords = json.loads(coords_raw) if isinstance(coords_raw, str) else (coords_raw or {})
            except Exception:
                coords = {}
            user_list.append({
                "name": u,
                "email": data.get("Email", ""),
                "has_token": bool(token),
                "token_preview": (token[:10] + "...") if token else "",
                "thread_id": data.get("ThreadId", 0),
                "location_text": loc.get("text", ""),
                "latitude": coords.get("latitude", 23.099994),
                "longitude": coords.get("longitude", 113.324520),
            })
        except Exception:
            pass
    return user_list

@app.post("/api/users")
async def save_user_compat(request: Request, config: SingleUserConfigModel):
    return await save_config(request, config)

@app.delete("/api/users/{name}")
async def delete_user(request: Request, name: str):
    clean_name = name.strip()
    filepath = os.path.join(TOKENS_DIR, f"{clean_name}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
        sid = get_session_id(request)
        sess = get_session(sid)
        if sess.get("user_name") == clean_name:
            update_session(sid, {"user_name": "", "token": ""})
        print(f"[Dashboard] 用户配置已删除: {clean_name}")
        return {"success": True, "message": f"已删除用户 {clean_name}"}
    raise HTTPException(status_code=404, detail="用户不存在")

# --- 实时日志流 ---
@app.get("/api/logs")
async def get_logs():
    return list(log_capture.logs)
