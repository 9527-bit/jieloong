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
        # 为每个用户创建一个线程，错开随机秒数（模拟多用户陆续操作，避免同一秒并发触发风控）
        for idx, json_file in enumerate(json_files):
            name = json_file[:-5]
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
