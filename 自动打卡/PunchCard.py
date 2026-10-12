from datetime import datetime
import requests
import json

import 自动打卡.Sendmail
import 自动打卡.WechatTokenWorkflow
import time
import threading

# 创建一个锁对象
lock = threading.Lock()


class PunchCard:

    def __init__(self, Name):
        try:
            # 输出初始化开始的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {Name}: 开始初始化PunchCard对象"
            )
            self.Name = Name  # 在外边读取并传入
            data = self.RJson()
            self.Email = data["Email"]
            self.Token = data["Token"]
            self.ThreadId = data["ThreadId"]
            self.Location = data["Location"]
            self.url = ""
            self.payload = {}
            self.headers = {}
            # 输出初始化完成的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {Name}: PunchCard对象初始化完成"
            )
        except KeyError as e:
            # 输出配置文件中用户信息缺失的异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {Name}: 配置文件中缺少必要字段: {e}"
            )
        except Exception as e:
            # 输出初始化过程中的其他异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {Name}: 初始化PunchCard对象时出现异常: {e}"
            )

    def UpdataToken(self):
        """更新对象的Token属性，在构建请求体前自动执行"""
        try:
            # 输出更新Token开始的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 开始更新Token"
            )
            data = self.RJson()
            self.Token = data["Token"]
            self.ThreadId = data["ThreadId"]
            self.Location = data["Location"]
            # 输出更新Token完成的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: Token更新完成"
            )
        except KeyError as e:
            # 输出配置文件中用户信息缺失的异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 配置文件中缺少必要字段: {e}"
            )
        except Exception as e:
            # 输出更新Token过程中的其他异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 更新Token时出现异常: {e}"
            )

    def UpdateEmail(self):
        """更新对象的Email属性"""
        try:
            # 输出更新Email开始的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 开始更新Email"
            )
            data = self.RJson()
            self.Email = data["Email"]
            # 输出更新Email完成的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: Email更新完成"
            )
        except KeyError as e:
            # 输出配置文件中用户信息缺失的异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 配置文件中缺少必要字段: {e}"
            )
        except Exception as e:
            # 输出更新Email过程中的其他异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 更新Email时出现异常: {e}"
            )

    def BuildRequest(self):
        """构建请求体，在发送请求之前必须调用一次"""
        try:
            # 输出构建请求体开始的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 开始构建请求体"
            )
            self.UpdataToken()
            self.url = "https://api.jielong.com/api/CheckIn/EditRecord"
            self.payload = json.dumps({
                "Id": 0,
                "EditToken": "",
                "ThreadId": self.ThreadId,
                "Number": "",
                "Signature": self.Name,
                "RecordValues": [{
                    "FieldId": 1,
                    "Values": [
                        self.Location["coordinates"]
                    ],
                    "Texts": [self.Location["text"]],
                    "Scores": [],
                    "Files": [],
                    "MatrixValues": [],
                    "CustomTableValues": [],
                    "FillInMatrixFieldValues": [],
                    "MatrixFormValues": [],
                    "HasValue": True,
                }],
                "DateTarget": "",
                "IsNeedManualAudit": False,
                "MinuteTarget": -1,
                "IsNameNumberComfirm": False,
            })
            self.headers = {
                "Host": "api.jielong.com",
                "Connection": "keep-alive",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.Token}",
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.71(0x18004730) NetType/4G Language/zh_CN",
                "Referer": "https://servicewechat.com/wx36ddf2a92cbb7814/914/page-frame.html",
                "X-Api-Request-Referer": "https://servicewechat.com/wx36ddf2a92cbb7814",
                "X-Api-Request-Mode": "cors",
                "PlatForm": "wx",
                "app-version": "v8.14.0.1",
            }
            # 输出构建请求体完成的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 请求体构建完成"
            )
        except Exception as e:
            # 输出构建请求体过程中的异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 构建请求体时出现异常: {e}"
            )

    def RJson(self):
        """读取JSON文件内的信息"""
        try:
            # 获取锁
            lock.acquire()
            # 输出读取JSON文件开始的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 开始读取配置文件"
            )
            file_path = f"自动打卡/Tokens/{self.Name}.json"
            with open(file_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            # 输出读取JSON文件完成的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 配置文件读取完成"
            )
            return data
        except FileNotFoundError:
            # 输出文件未找到的异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 未找到配置文件 {self.Name}.json"
            )
        except json.JSONDecodeError:
            # 输出JSON解析错误的异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 配置文件格式错误，无法解析"
            )
        except Exception as e:
            # 输出读取JSON文件过程中的其他异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 读取配置文件时出现异常: {e}"
            )
        finally:
            # 释放锁
            lock.release()
        return {}

    def WJson(self, data):
        """更新Json文件内的信息"""
        try:
            # 获取锁
            lock.acquire()
            # 输出更新JSON文件开始的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 开始更新配置文件"
            )
            file_path = f"自动打卡/Tokens/{self.Name}.json"
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4, ensure_ascii=False)
            # 输出更新JSON文件完成的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 配置文件更新完成"
            )
        except FileNotFoundError:
            # 输出文件未找到的异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 未找到配置文件 {self.Name}.json"
            )
        except Exception as e:
            # 输出更新JSON文件过程中的其他异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 更新配置文件时出现异常: {e}"
            )
        finally:
            # 释放锁
            lock.release()

    def UpdataJsonToken(self, Token):
        """更新JSON文件内此对象的Token"""
        try:
            # 输出更新JSON文件中Token开始的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 开始更新配置文件中的Token"
            )
            data = self.RJson()
            data["Token"] = Token
            self.WJson(data)
            # 输出更新JSON文件中Token完成的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 配置文件中的Token更新完成"
            )
        except KeyError as e:
            # 输出配置文件中用户信息缺失的异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 配置文件中缺少必要字段: {e}"
            )
        except Exception as e:
            # 输出更新JSON文件中Token过程中的其他异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 更新配置文件中的Token时出现异常: {e}"
            )

    def RTS(self):
        """打卡，根据最新的信息重新构建请求体+发送请求"""
        try:
            # 输出打卡开始的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 开始打卡操作"
            )
            self.BuildRequest()
            response = requests.request("POST",
                                        self.url,
                                        headers=self.headers,
                                        data=self.payload)
            response.raise_for_status()
            # 输出打卡完成的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 打卡操作完成"
            )
            return response
        except requests.RequestException as e:
            # 输出请求异常的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 打卡请求时出现异常: {e}"
            )
        except Exception as e:
            # 输出打卡过程中的其他异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 打卡操作时出现异常: {e}"
            )
        return None

    def DuplicateToken(self):
        """对于获取Token失败时，重新发送授权邮件获取Token，获取成功返回True，失败返回False"""
        try:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 开始重新获取Token"
            )
            self.UpdateEmail()
            Token = 自动打卡.WechatTokenWorkflow.AllFlow(self.Email,
                                                     self.Name)  # 21:30邮件到
            attempts = 0
            while Token is None and attempts < 6:
                # 根据尝试次数动态调整等待时间
                if attempts < 2:  # 第1-2次等待25分钟
                    wait_time = 1500
                elif attempts == 2:  # 第3次等待10小时25分钟（跨天逻辑）
                    自动打卡.Sendmail.Sendmail().sendFailMail(
                        self.Email, self.Name)  # 提醒用户手动打卡
                    wait_time = 37500  # 10h25m=37500秒 [5]()
                else:  # 第4-5次等待1小时
                    wait_time = 3600

                time.sleep(wait_time)
                self.UpdateEmail()
                Token = 自动打卡.WechatTokenWorkflow.AllFlow(self.Email, self.Name)
                attempts += 1

            if Token is None:
                # 最终失败处理（对应原函数次日12:05逻辑）
                自动打卡.Sendmail.Sendmail().sendEndlMail(self.Email, self.Name)
                print(
                    f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: Token获取失败或已失效，保留用户配置，请在 Web 控制台重新扫码授权登录"
                )
                return False

            self.UpdataJsonToken(Token)
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 重新获取Token成功"
            )
            return True
        except Exception as e:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 重新获取Token时出现异常: {e}"
            )
            return False

    def Main(self):
        """打卡主流程"""
        try:
            # 输出主流程开始的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 开始执行打卡主流程"
            )
            config_data = self.RJson()
            if config_data.get("Status") == "paused":
                print(
                    f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] ⏸️ {self.Name}: 当前打卡配置处于【已暂停】状态 (原因: {config_data.get('LastError', '多次打卡失败')})，跳过执行，等待用户更新配置。"
                )
                return

            if self.Token == "":  # JSON文件内的Token如果为空则先获取Token
                isRun = (self.DuplicateToken())  # 最终还是未获取到Token，则直接退出整个程序
                if isRun == False:
                    fail_cnt = config_data.get("FailCount", 0) + 1
                    config_data["FailCount"] = fail_cnt
                    config_data["LastError"] = "微信授权Token已失效且未能自动刷新"
                    config_data["LastFailTime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if fail_cnt >= 3:
                        config_data["Status"] = "paused"
                        print(
                            f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] ⚠️ {self.Name}: 连续失败达 {fail_cnt} 次，已自动暂停打卡，等待用户在 Web 页面重新扫码！"
                        )
                    self.WJson(config_data)
                    return

            response = self.RTS()
            resp_json = None
            if response:
                try:
                    resp_json = response.json()
                    print(
                        f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 服务器响应: {response.text}"
                    )
                except Exception:
                    print(
                        f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 服务器响应代码: {response.status_code}"
                    )

            is_success = False
            desc = ""
            if resp_json:
                desc = str(resp_json.get("Description", ""))
                data_val = str(resp_json.get("Data", ""))
                type_code = str(resp_json.get("Type", ""))
                if ("打卡成功" in desc or "打卡成功" in data_val or "成功" in desc or
                    "已完成当期打卡" in desc or "已完成当期打卡" in data_val or type_code in ["000001", "000020"]):
                    is_success = True

            if is_success:
                print(
                    f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 打卡成功！({resp_json.get('Data', '成功')})"
                )
                config_data["Status"] = "active"
                config_data["FailCount"] = 0
                config_data["LastError"] = ""
                config_data["LastSuccessTime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.WJson(config_data)
                自动打卡.Sendmail.Sendmail().sendSucceedMail(self.Email, self.Name)
            else:
                print(
                    f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 首次打卡响应异常 ({desc})，尝试刷新Token后重试..."
                )
                retry_success = False
                if self.DuplicateToken():
                    response = self.RTS()
                    resp_json = None
                    if response:
                        try:
                            resp_json = response.json()
                            print(
                                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 重试服务器响应: {response.text}"
                            )
                        except Exception:
                            pass
                    
                    if resp_json:
                        desc = str(resp_json.get("Description", ""))
                        data_val = str(resp_json.get("Data", ""))
                        type_code = str(resp_json.get("Type", ""))
                        if ("打卡成功" in desc or "打卡成功" in data_val or "成功" in desc or
                            "已完成当期打卡" in desc or "已完成当期打卡" in data_val or type_code in ["000001", "000020"]):
                            retry_success = True

                if retry_success:
                    print(
                        f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 重试打卡成功！({resp_json.get('Data', '成功')})"
                    )
                    config_data["Status"] = "active"
                    config_data["FailCount"] = 0
                    config_data["LastError"] = ""
                    config_data["LastSuccessTime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.WJson(config_data)
                    自动打卡.Sendmail.Sendmail().sendSucceedMail(
                        self.Email, self.Name)
                else:
                    err_msg = desc or (resp_json.get("Data") if resp_json else "网络或服务器错误")
                    print(
                        f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 打卡失败: {err_msg}"
                    )
                    fail_cnt = config_data.get("FailCount", 0) + 1
                    config_data["FailCount"] = fail_cnt
                    config_data["LastError"] = str(err_msg)
                    config_data["LastFailTime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    # 连续失败达 3 次，或遇到明确的Token失效/未登录等不可自愈错误，自动熔断暂停
                    if fail_cnt >= 3 or any(w in str(err_msg) for w in ["登录", "Token", "失效", "过期", "401"]):
                        config_data["Status"] = "paused"
                        print(
                            f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] ⚠️ {self.Name}: 连续打卡失败已达 {fail_cnt} 次（{err_msg}），系统已自动将该配置设为【暂停】状态，停止后续打卡，等待用户在 Web 页面更新！"
                        )
                    self.WJson(config_data)
                    自动打卡.Sendmail.Sendmail().sendFailMail(
                        self.Email, self.Name)
            # 输出主流程完成的日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 打卡主流程执行完成"
            )
        except ValueError:
            # 输出JSON解析错误的异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 解析响应JSON数据时出现错误"
            )
        except Exception as e:
            # 输出主流程执行过程中的其他异常日志
            print(
                f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] {self.Name}: 执行打卡主流程时出现异常: {e}"
            )
            try:
                config_data = self.RJson()
                fail_cnt = config_data.get("FailCount", 0) + 1
                config_data["FailCount"] = fail_cnt
                config_data["LastError"] = f"执行异常: {str(e)[:100]}"
                config_data["LastFailTime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if fail_cnt >= 3:
                    config_data["Status"] = "paused"
                    print(
                        f"[{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}] ⚠️ {self.Name}: 连续异常达 {fail_cnt} 次，系统已自动暂停该配置！"
                    )
                self.WJson(config_data)
            except Exception:
                pass
