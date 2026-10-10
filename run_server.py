import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 18080))
    host = os.environ.get("HOST", "0.0.0.0")
    print(f"TaskForge Web 服务已启动: http://{host}:{port} (绑定端口: {port})")
    uvicorn.run("web.server:app", host=host, port=port, reload=False)
