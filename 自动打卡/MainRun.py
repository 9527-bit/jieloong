import json
import random
import threading
import time
from datetime import datetime

import 自动打卡.PunchCard


def run_punch_card(name, delay_seconds=0):
    try:
        if delay_seconds > 0:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {name}: 模拟真实错峰打卡，随机等待 {delay_seconds} 秒后开始..."
            )
            time.sleep(delay_seconds)
        # 输出线程开始的日志
        print(
            f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {name}: 线程开始执行打卡操作"
        )
        # 创建PunchCard对象并调用Main方法
        自动打卡.PunchCard.PunchCard(name).Main()
        # 输出线程结束的日志
        print(
            f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {name}: 线程完成打卡操作"
        )
    except Exception as e:
        # 输出线程执行过程中的异常日志
        print(
            f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {name}: 线程执行过程中出现异常: {e}"
        )


def main():
    try:
        import os
        # 扫描自动打卡/Tokens目录下的所有JSON文件
        tokens_dir = "自动打卡/Tokens"
        if not os.path.exists(tokens_dir):
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] 未找到Tokens目录，正在创建..."
            )
            os.makedirs(tokens_dir)
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] Tokens目录创建完成"
            )
            return
        
        # 获取所有.json文件（排除模版文件 example.json 和点开头的隐藏文件）
        json_files = [
            f for f in sorted(os.listdir(tokens_dir))
            if f.endswith('.json') and f != 'example.json' and not f.startswith('.')
        ]
        
        if not json_files:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] Tokens目录下没有找到有效的用户配置文件（请在Tokens目录下创建 [用户名].json）"
            )
            return
        
        threads = []
        active_users = []
        # 检查各用户状态，已暂停的用户跳过调度
        for json_file in json_files:
            name = json_file[:-5]
            fpath = os.path.join(tokens_dir, json_file)
            try:
                with open(fpath, "r", encoding="utf-8") as fp:
                    u_data = json.load(fp)
                if u_data.get("Status") == "paused":
                    print(
                        f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] ⏸️ {name}: 配置已处于【暂停打卡】状态 (原因: {u_data.get('LastError', '多次失败')})，跳过今日定时打卡，等待用户更新"
                    )
                    continue
            except Exception:
                pass
            active_users.append(name)

        if not active_users:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] 当前所有用户均处于暂停状态或未配置，跳过本次调度"
            )
            return

        # 为正常状态的用户创建线程，错开随机秒数（模拟多用户陆续操作）
        for idx, name in enumerate(active_users):
            stagger = random.randint(2, 10) + (idx * random.randint(5, 18))
            thread = threading.Thread(target=run_punch_card, args=(name, stagger))
            threads.append(thread)
            thread.start()

        # 等待所有线程完成
        for thread in threads:
            thread.join()

    except FileNotFoundError as e:
        # 输出文件未找到的异常日志
        print(
            f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] 文件未找到: {e}"
        )
    except Exception as e:
        # 输出其他异常的日志
        print(f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] 发生未知异常: {e}")
