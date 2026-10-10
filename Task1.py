import Task
import 自动打卡


class Task1(Task.Task):

    def __init__(self):
        # 每天基准时间 21:05，随机浮动 0~35 分钟（在 21:05 ~ 21:40 之间随机时间点打卡）
        super().__init__(__class__.__name__, "自动打卡", 1, 21, 5, random_jitter_minutes=35)

    def run(self):
        自动打卡.MainRun.main()
