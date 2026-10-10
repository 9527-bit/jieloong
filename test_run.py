"""
快速测试脚本：用于立即触发一次打卡与授权流程，无需等待定时调度
"""
import sys
import 自动打卡.MainRun

if __name__ == "__main__":
    print("=" * 50)
    print("开始执行一次性打卡与授权测试...")
    print("=" * 50)
    自动打卡.MainRun.main()
    print("=" * 50)
    print("测试执行结束")
    print("=" * 50)
