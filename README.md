# Elite Dangerous AFK Monitor

Real-time monitoring of Elite Dangerous journal files for logging AFK massacre farming events as they happen. Output is to terminal, Discord channel/thread or Discord with a user ping and each level can be configured on a per-event basis.

| Terminal output | Discord output |
| --- | --- |
| ![Terminal](images/v250205_terminal.png) | ![Discord](images/v250205_discord.png) |

*Screenshots of a simulated log being monitored*

## 说明目录
- [精英危险挂机清剿监控](#监控事件与记录信息)
  - [说明目录](#说明目录)
  - [监控事件与记录信息](#监控事件与记录信息)
  - [开始使用](#开始使用)
    - [EXE版本](#EXE 版本)
    - [Python 版本](#Python 版本)
  - [配置日志级别](#配置日志级别)
  - [常见问题](#常见问题)
    - [I get some output to terminal then nothing else](#i-get-some-output-to-terminal-then-nothing-else)
    - [I'm noticing kills in-game that aren't being logged](#im-noticing-kills-in-game-that-arent-being-logged)
    - [Ships scans not all reported / seem wrong](#ships-scans-not-all-reported--seem-wrong)
    - [Hull was damaged but not reported](#hull-was-damaged-but-not-reported)
    - [I ejected cargo manually and got notified](#i-ejected-cargo-manually-and-got-notified)
    - [There are garbled characters in the terminal output](#there-are-garbled-characters-in-the-terminal-output)

## 监控事件与记录信息
- 舰船扫描（由玩家或由舰载战斗机 NPC 驾驶员完成）
- 赏金记录（击杀记录，包含所属派系及与上次击杀的时间间隔）
- 统计摘要：每10次击杀汇总一次击杀/赏金/功勋数据及平均效率（每小时击杀率）
- 任务状态：已完成的任务击杀数及剩余任务数
- 护盾监控：护盾失效或已恢复
- 损毁监控：母舰/战斗机舰体受损百分比
- 坠毁监控：母舰/战斗机被摧毁记录
- 海盗行为：因货物价值过低而未交火的海盗提醒
- 货物损失：货物被海盗偷取通知
- 燃料预警：燃料储备过低或进入危险状态
- 安全警告：遭到安全部队（警察）攻击的警告
- 效率预警：每小时击杀海盗率过低的提醒
- 日志活性检测：检测游戏日志是否停止更新（例如因游戏崩溃或网络掉线引起）

...plus some other minor things

## 开始使用

### EXE 版本

- Download and extract `afk_monitor_standalone.7z` from [releases](https://github.com/PsiPab/ED-AFK-Monitor/releases) to a folder
- Copy `afk_monitor.example.toml` and rename the copy to `afk_monitor.toml`
- (Optional) For Discord support edit `WebhookURL` and `UserID` under `[Discord]` in `afk_monitor.toml`
- Start Elite Dangerous then run `afk_monitor.exe`

### Python 版本

安装要求: [Python 3.x](https://www.python.org/downloads/), [discord-webhook](https://github.com/lovvskillz/python-discord-webhook) (可选，仅在使用 Discord 推送功能时需要)
- 从 [releases](https://github.com/pz328/ED-AFK-Monitor-chinese/releases) 下载 `Source code (zip)` 并解压到文件夹中。
- 复制 afk_monitor.example.toml 文件，并将副本重命名为 afk_monitor.toml。
- （可选） 若需开启 Discord 支持，请编辑 afk_monitor.toml 文件中 [Discord] 章节下的 WebhookURL 和 UserID 条目。
- 启动《精英：危险》（Elite Dangerous），然后双击运行 afk_monitor.py 或者打开终端并输入命令：py afk_monitor.py

## 配置日志级别

每种事件类型都可以设置为四种累加式输出级别之一：无 (0)、终端输出 (1)、Discord 推送 (2)，以及 Discord 推送并艾特/提醒用户 (3)。

你可以通过编辑 afk_monitor.toml 文件中 [LogLevels] 章节下的数值来进行配置。配置文件中对每种具体的事件类型都附带了详细说明。

默认配置旨在为刚开始尝试 AFK 挂机的指挥官提供最合理的反馈逻辑。例如，“强力敌舰扫描 (Scans of hard ships)”默认会记录到 Discord，以帮助你及时发现并避开那些难度过高、可能导致炸船的挂机点。

## 启动参数

你可以在启动挂机清剿监控时加上启动参数:
```
-p, --profile <profile_name>                  加载指定的配置文件
-j, --journal <journal_folder_path>           Override for path to journal folder
-w, --webhook <webhook_url>                   Override for Discord webhook URL
-r, --resetsession                            预加载完成后，重置本次会话的统计数据
-t, --test                                    测试模式：将本应发送到 Discord 的消息输出到本地终端
-d, --debug                                   调试模式：打印用于排查问题的详细调试信息。
-s, --setfile <journal_file_path>             设置使用指定的日志文件
-f, --fileselect                              显示最近的日志文件列表以供选择
```

## 常见问题

### I get some output to terminal then nothing else

By default AFK Monitor watches your latest journal, so make sure to start it after loading the game or it may process an older journal and produce no further output. If you want to monitor a different journal pass `--fileselect` when starting AFK Monitor and you will be presented with a list of recent journals to chose from.

### I'm noticing kills in-game that aren't being logged

ED does not log all kills/bounties either in-game or to the journal (anywhere from 0-30% are missed). This is a game limitation so there is nothing I can do about it. On the upside, these 'ghost' kills still count towards your mission completions.

### Ships scans not all reported / seem wrong

Scans are recorded in the journal in the same way when targeted by an NPC pilot *or* the player manually. The only reliable data is that a scan was done of a type of ship, so to keep things from being too spammy we only report each ship type once between kills and then reset after a kill.

In addition, if you manually target a type of ship that pirates also use, e.g. system security, those scans will be logged just like any other. For this reason it is best to only use a target key bind for 'select next hostile target' instead if you have AFK Monitor running with scans enabled.

### Hull was damaged but not reported

ED only records hull damage in 20% increments, so if your ship or fighter hull was reduced to 81% for example that wouldn't be reported until it dropped further.

### I ejected cargo manually and got notified

ED's journal does not differentiate between cargo jettisoned by the player or stolen by hatch breaker limpets. As a workaround if you want to get rid of cargo with the script running and not be notified you can use 'Abandon' instead of 'Jettison', or jettison more than one unit at a time.

### There are garbled characters in the terminal output

Windows 10 command prompt doesn't support nice things like colours or emoji. Install and use [Windows Terminal](https://github.com/microsoft/terminal) instead and things will look *a lot* better (see screenshot at top of ReadMe).
