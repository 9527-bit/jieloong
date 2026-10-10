import datetime
import json
import random
import TaskManager


# 定义一个任务模版类，它是所有任务类的父类
class Task:

    def updata_next_run_time(self):
        """
        更新下次任务执行时间（支持随机浮动，模拟真实人工打卡）
        """
        now_time = datetime.datetime.now()
        target_date = now_time.date()
        base_time = datetime.datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            self.start_time.hour,
            self.start_time.minute,
        )

        # 随机浮动秒数 (0 ~ random_jitter_minutes 分钟 + 0 ~ 59 秒)
        jitter_seconds = 0
        if getattr(self, "random_jitter_minutes", 0) > 0:
            jitter_seconds = random.randint(0, self.random_jitter_minutes * 60) + random.randint(0, 59)

        candidate_time = base_time + datetime.timedelta(seconds=jitter_seconds)

        # 如果今天的随机时间已经过去了，计算下一个周期（通常是明天）的随机时间
        if candidate_time <= now_time:
            next_date = target_date + datetime.timedelta(days=self.frequency)
            next_base_time = datetime.datetime(
                next_date.year,
                next_date.month,
                next_date.day,
                self.start_time.hour,
                self.start_time.minute,
            )
            next_jitter = 0
            if getattr(self, "random_jitter_minutes", 0) > 0:
                next_jitter = random.randint(0, self.random_jitter_minutes * 60) + random.randint(0, 59)
            candidate_time = next_base_time + datetime.timedelta(seconds=next_jitter)

        return candidate_time

    def __init__(self, Name, name, frequency, hour, minute, IsDisposable=False, random_jitter_minutes=35):
        """
        初始化任务类
        :param random_jitter_minutes: 随机延后浮动范围（分钟），默认 35 分钟
        """
        self.Name = Name  # 任务对象的类名(模块名)
        self.name = name  # 任务名称
        self.frequency = frequency  # 任务频率，几天执行一次
        self.start_time = datetime.time(hour, minute)  # 任务基准开始执行时间
        self.random_jitter_minutes = random_jitter_minutes  # 随机浮动分钟
        self.count = 0  # 任务总执行次数
        self.IsDisposable = IsDisposable  # 是否为一次性任务
        self.next_run_time = self.updata_next_run_time()  # 获取任务下次执行时间
        print(
            f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {self.name}任务构建完成，基准时间: {self.start_time.strftime('%H:%M')} (浮动范围: +{self.random_jitter_minutes}分钟)，下一次随机执行时间: {self.next_run_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        TaskManager.TaskManager.task_group.append(self)  # 向任务管理器添加当前任务对象

    def interceptor(self):
        """
        拦截器，在任务执行之前调用，用来判断任务是否需要执行
        """
        if (
            self.Name not in TaskManager.TaskManager.module_names
        ):  # 如果当前任务不在任务管理器中，就向任务管理器的删除任务队列中添加此任务
            TaskManager.TaskManager.remove_task_group.append(self)
            TaskManager.TaskManager.remove_loaded_task_group.append(self.Name)
            print(datetime.datetime.now(), "\n###警告：任务%s已移除!\n" % self.name)
            return

        differential_seconds = (
            self.next_run_time - datetime.datetime.now()
        ).total_seconds()
        if (
            differential_seconds <= 0
        ):  # 如果当前时间与任务下次执行时间差值小于等于0（这样可以保证任务在当前频率周期内只执行一次），就执行任务
            self.Run()

    def run(self):
        """
        任务执行的代码，子类需要重新此方法
        """

        pass

    def Run(self):
        """
        真正的run方法，子类的代码在此方法代码的中间执行
        """

        self.count += 1
        print(
            "\n\n==============================开始执行=================================="
        )
        print(datetime.datetime.now(), "任务名称：%s" % self.name)
        print(datetime.datetime.now(), "任务频率：%d" % self.frequency)
        print(datetime.datetime.now(), "任务开始时间：%s" % self.start_time)
        print(datetime.datetime.now(), "任务总执行次数：%d" % self.count)

        print("\n")
        self.run()  # 子类方法
        print("\n")

        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 当前任务执行完成！")
        self.next_run_time = self.updata_next_run_time()  # 更新任务下次执行时间（重新生成随机时间）
        print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 【{self.name}】已自动生成下次随机定时执行时间: {self.next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(
            "==============================执行完成=================================="
        )

        if self.IsDisposable:
            # 如果此任务为一次性任务就在执行完成后将config.json文件中的该任务字段删除
            with open("config.json", "r") as f:
                data = json.load(f)
                if self.Name in data:
                    data.remove(self.Name)
                with open("config.json", "w") as f:
                    json.dump(data, f)
