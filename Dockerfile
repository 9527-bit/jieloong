FROM python:3.11-slim

WORKDIR /app

# 环境变量：无缓冲输出、禁止生成pyc、默认绑定端口18080
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=18080 \
    HOST=0.0.0.0

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制整个项目
COPY . .

# 暴露 18080 端口（落于 18000-18999 端口段内）
EXPOSE 18080

# 启动 TaskForge Web 仪表盘与后台调度器
CMD ["python", "run_server.py"]
