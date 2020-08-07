import json
import logging
import math
import random
import re
import time

import requests
from flask import Flask, request

app = Flask(__name__)
config = {
    "group_id": "114514",
    "host": "http://127.0.0.1:5700",
    "active_duration": 60,
    "task_valid_duration": 300,
    "cooldown": 300
}
toupiaoapps = []
help_menber = '''!!禁言 @被仲裁的人 - 对被@的人发起仲裁禁言(要@蓝)
!!投票 仲裁id 0/1 - 对某个仲裁id进行投票("0"为同意,"1"为不同意)
!!帮助 - 获得命令帮助'''
help_admin = '''
!!禁止使用投票禁言 @被禁用的人 - 禁止某人使用投票禁言功能
!!允许使用投票禁言 @被允许的人 - 允许某人使用投票禁言功能
!!投票禁言黑名单列表 - 查看禁言黑名单列表'''
help_owner = ''''''


class task_info:
    def __init__(self, task_id, initiator, target, neednum):
        self.starttime = time.time()
        self.task_id = task_id
        self.initiator = initiator
        self.target = target
        self.neednum = neednum
        self.progress = 0
        self.voted = []

    def agree(self, user_id):
        if user_id not in self.voted:
            if user_id == self.initiator or user_id == self.target:
                return 0, "[CQ:at,qq={0}]你是发起者/被仲裁者, 无法投票".format(user_id)
            self.progress += 1
            self.voted.append(user_id)
            if self.progress >= self.neednum:
                return self.target, "投票 {0} 的进度 ({1}/{2})\n目标已达成".format(self.task_id, self.progress, self.neednum)
            else:
                return 0, "投票 {0} 的进度 ({1}/{2})".format(self.task_id, self.progress, self.neednum)
        else:
            return "[CQ:at,qq={0}]您已经投过票了".format(user_id)

    def disagree(self, user_id):
        if user_id not in self.voted:
            if user_id == self.initiator or user_id == self.target:
                return "[CQ:at,qq={0}]你是发起者/被仲裁者, 无法投票".format(user_id)
            self.progress -= 1
            self.voted.append(user_id)
            return "投票 {0} 的进度 ({1}/{2})".format(self.task_id, self.progress, self.neednum)
        else:
            return "[CQ:at,qq={0}]您已经投过票了".format(user_id)


class toupiao:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.msgrecode = {}  # {user_id(str): last_speak_time(int)}
        self.tasklist = {}  # {task_id(str): task(task_info)}
        self.cooldown = {}
        self.logger.info(config["group_id"] + " 开始运行")

    def send_msg(self, message):
        requests.post(config["host"] + "/send_group_msg", data={"group_id": self.config["group_id"], "message": message})
        self.logger.debug("发送信息: " + message)

    def ban(self, user_id):
        requests.post(config["host"] + "/set_group_ban", data={"group_id": self.config["group_id"], "user_id": user_id, "duration": 2592000})

    def on_info(self, info):
        self.logger.debug("from " + str(info["group_id"]) + " by " + str(info["user_id"]) + ": " + info["message"])
        if str(info["group_id"]) != self.config["group_id"]:
            return
        if info["group_id"] == 2854196306:
            return
        if info["message"].startswith("!!") or info["message"].startswith("！！"):
            args = info["message"].split(" ")
            cmd = args[0][2:len(args[0])]  # 去除"!!"或"！！"
            args = args[1:len(args)]
            self.on_command(cmd, args, info)
        else:
            self.updaterecode(info)

    def updaterecode(self, info):
        needdel = []
        for k, v in self.msgrecode.items():
            if time.time() > v + self.config["active_duration"]:
                needdel.append(k)
                self.logger.debug(k + " 已经{0}s没说话了".format(self.config["active_duration"]))
        for a in needdel:
            del (self.msgrecode[a])
        self.msgrecode[str(info["user_id"])] = info["time"]
        self.logger.debug(str(self.msgrecode))

    def check_tasklist(self):
        needdel = []
        for k, v in self.tasklist.items():
            if time.time() > v.starttime + self.config["task_valid_duration"]:
                needdel.append(k)
        for a in needdel:
            del (self.tasklist[a])

    def update_cooldown(self):
        needdel = []
        for k, v in self.cooldown.items():
            if time.time() > v + 300:
                needdel.append(k)
        for a in needdel:
            del (self.cooldown[a])

    def on_command(self, cmd, args, info):
        self.check_tasklist()
        self.update_cooldown()
        if cmd == "禁言":
            f = open("blacklist.json", "r", encoding="utf-8")
            blacklist = json.load(f)
            if str(info["user_id"]) in blacklist.keys():
                self.send_msg("[CQ:at,qq={0}]你不能使用该功能, 理由:{1}, 执行人:{2}".format(info["user_id"], blacklist["user_id"]["reason"], blacklist["user_id"]["from"]))
                return
            for t in self.tasklist.values():
                if t.initiator == info["user_id"]:
                    self.send_msg("[CQ:at,qq={0}]你有一个仲裁请求在队列中, id:{1}, 目标:{2}".format(info["user_id"], t.task_id, t.target))
                    return
            matchobj = re.match(r"^\[CQ:at,qq=(\d+)\]$", args[0])
            if matchobj is None:
                self.send_msg("[CQ:at,qq={0}]参数错误".format(info["user_id"]))
                return
            targetuser = matchobj[1]
            if str(info["user_id"]) in self.cooldown.keys():
                self.send_msg("[CQ:at,qq={0}]操作过于频繁,请等待{1}秒".format(info["user_id"], str(int(300 - (time.time() - self.cooldown[str(info["user_id"])])))))
                return
            if info["sender"]["role"] == "owner" or info["sender"]["role"] == "admin":
                self.ban(targetuser)
                return
            msg = str(info["user_id"]) + " 发起对 " + targetuser + " 的仲裁,在线情况:\n"
            neednum = len(self.msgrecode.keys())
            if info["user_id"] in self.msgrecode.keys():
                neednum -= 1  # 减去发起投票人
            if targetuser in self.msgrecode.keys():
                neednum -= 1  # 减去被仲裁人
            neednum = math.ceil(neednum / 2)
            if neednum < 3:  # 不足3个人
                self.send_msg("[CQ:at,qq={0}]目前活跃人数不足".format(info["user_id"]))
                return
            for k, v in self.msgrecode.items():
                msg += k + " - 距上次发言: " + str(time.time() - v) + "s\n"
            while True:
                task_id = str(random.randint(0, 9999)).zfill(4)
                if task_id not in self.tasklist.keys():
                    break
            task = task_info(task_id, info["user_id"], targetuser, neednum)
            self.tasklist[task_id] = task
            msg += "目标:{0}人".format(neednum)
            self.logger.info(msg)
            self.cooldown[str(info["user_id"])] = time.time()
            self.send_msg(str(info["user_id"]) + " 发起对 {0} 的仲裁,进度 (0/{1})\n发送(\"!!投票 {2} <0/1>\"来投票(\"0\"为同意,\"1\"为不同意))".format(targetuser, neednum, task_id))

        elif cmd == "投票":
            if len(args) < 2:
                self.send_msg("[CQ:at,qq={0}]参数错误".format(info["user_id"]))
                return
            if args[0] not in self.tasklist:
                self.send_msg("[CQ:at,qq={0}]投票id不存在".format(info["user_id"]))
                return
            f = open("blacklist.json", "r", encoding="utf-8")
            blacklist = json.load(f)
            if str(info["user_id"]) in blacklist.keys():
                self.send_msg("[CQ:at,qq={0}]你不能使用该功能, 理由:{1}, 执行人:{2}".format(info["user_id"], blacklist["user_id"]["reason"], blacklist["user_id"]["from"]))
                return
            if args[1] == "0":
                if info["sender"]["role"] == "owner" or info["sender"]["role"] == "admin":
                    self.send_msg("管理员参与了投票" + args[0])
                    self.ban(self.tasklist[args[0]].target)
                    del (self.tasklist[args[0]])
                else:
                    result = self.tasklist[args[0]].agree(info["user_id"])
                    if result[0] != 0:
                        self.ban(result[0])
                        del (self.tasklist[args[0]])
                    self.send_msg(result[1])
            elif args[1] == "1":
                if info["sender"]["role"] == "owner" or info["sender"]["role"] == "admin":
                    self.send_msg("管理员参与了投票" + args[0])
                    del (self.tasklist[args[0]])
                else:
                    self.send_msg(self.tasklist[args[0]].disagree(info["user_id"]))
            else:
                self.send_msg("[CQ:at,qq={0}]参数2只能为\"0\"(同意)或\"1\"(不同意)".format(info["user_id"]))

        elif cmd == "禁止使用投票禁言":
            if len(args) == 0:
                self.send_msg("[CQ:at,qq={0}]参数错误".format(info["user_id"]))
                return
            if info["sender"]["role"] != "owner" and info["sender"]["role"] != "admin":
                self.send_msg("[CQ:at,qq={0}]你不是管理/群主".format(info["user_id"]))
                return
            matchobj = re.match(r"^\[CQ:at,qq=(\d+)\]$", args[0])
            if matchobj is None:
                self.send_msg("[CQ:at,qq={0}]参数错误".format(info["user_id"]))
                return
            targetuser = matchobj[1]
            f = open("blacklist.json", "r", encoding="utf-8")
            blacklist = json.loads(f.read())
            f.close()
            if targetuser in blacklist.keys():
                self.send_msg("[CQ:at,qq={0}]{1}已经在黑名单中了, 执行人:{2}, 理由:{3}".format(info["user_id"], targetuser, blacklist[targetuser]["from"], blacklist[targetuser]["reason"]))
            else:
                blacklist[targetuser] = {}
                blacklist[targetuser]["from"] = info["user_id"]
                reason = ""
                if len(args) > 1:
                    for s in args[1:len(args)]:
                        reason += s + " "
                blacklist[targetuser]["reason"] = reason.rstrip()
                self.send_msg("[CQ:at,qq={0}]{1}成功被添加到投票禁言黑名单".format(info["user_id"], targetuser))
                self.logger.warning("{0} 被 {1} 拉入黑名单, 理由: {2}".format(targetuser, info["user_id"], blacklist[targetuser]["reason"]))
                f = open("blacklist.json", "w", encoding="utf-8")
                json.dump(blacklist, f, ensure_ascii=False)
                f.close()

        elif cmd == "允许使用投票禁言":
            if len(args) == 0:
                self.send_msg("[CQ:at,qq={0}]参数错误".format(info["user_id"]))
                return
            if info["sender"]["role"] != "owner" and info["sender"]["role"] != "admin":
                self.send_msg("[CQ:at,qq={0}]你不是管理/群主".format(info["user_id"]))
                return
            matchobj = re.match(r"^\[CQ:at,qq=(\d+)\]$", args[0])
            if matchobj is None:
                self.send_msg("[CQ:at,qq={0}]参数错误".format(info["user_id"]))
                return
            targetuser = matchobj[1]
            f = open("blacklist.json", "r", encoding="utf-8")
            blacklist = json.loads(f.read())
            f.close()
            if targetuser in blacklist.keys():
                del(blacklist[targetuser])
                f = open("blacklist.json", "w", encoding="utf-8")
                json.dump(blacklist, f, ensure_ascii=False)
                f.close()
                self.send_msg("[CQ:at,qq={0}]{1}已被移出黑名单".format(info["user_id"], targetuser))
                self.logger.warning("{0} 被 {1} 移出黑名单".format(targetuser, info["user_id"]))
            else:
                self.send_msg("[CQ:at,qq={0}]{1}不在黑名单内".format(info["user_id"], targetuser))

        elif cmd == "投票禁言黑名单列表":
            f = open("blacklist.json", "r", encoding="utf-8")
            blacklist = json.loads(f.read())
            f.close()
            msg = "====投票禁言黑名单列表====\n"
            for k, v in blacklist.items():
                msg += "{0} - {1} (from{2})\n".format(k, v["reason"], v["from"])
            msg += "======================="
            self.send_msg(msg)

        elif cmd == "帮助" or cmd == "help":
            msg = help_menber
            if info["sender"]["role"] == "admin":
                msg += help_admin
            if info["sender"]["role"] == "owner":
                msg += help_admin + help_owner
            self.send_msg(msg)


@app.route('/api/message', methods=['POST'])
def abaaba():
    data = request.get_data().decode('utf-8')
    data = json.loads(data)
    if data["post_type"] == "message" and data["message_type"] == "group" and data["sub_type"] == "normal":
        for a in toupiaoapps:
            a.on_info(data)
    return ''


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    fh = logging.FileHandler("log.log", mode="a")
    ch.setLevel(logging.DEBUG)
    fh.setLevel(logging.WARNING)
    formatter = logging.Formatter("[%(asctime)s] [%(threadName)s/%(levelname)s]: %(message)s")
    ch.setFormatter(formatter)
    fh.setFormatter(formatter)
    logger.addHandler(ch)
    logger.addHandler(fh)

    toupiaoapps.append(toupiao({**config, **{"group_id": "579879049"}}, logger))
    app.run(host="127.0.0.1", port=5701)
