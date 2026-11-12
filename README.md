# Long Task Monitor Skill

让 Codex、使用 DeepSeek 的 harness 或其他 AI 工具，在 goal 任务或用户明确要求时，把任务进展上报到监控服务器。普通对话不上报，安装与配置也不上报。

本仓库只分发 skill 和安装器。需要 Python 3.10+；无需安装额外依赖，不包含服务器密钥、用户配置或任务数据。

## 让 harness 自己安装

把仓库链接交给 harness，并说：

> 阅读这个仓库的 README，按“供 harness 执行的安装步骤”安装 long-task-monitor。识别你实际使用的 skills 目录，不要根据模型名称猜目录。安装过程中不要上报任务。服务器地址由我提供，上报密钥通过环境变量或私有配置提供。

### 供 harness 执行的安装步骤

1. Clone 仓库到用户允许的工作目录，读取此 README 和 `skills/long-task-monitor/SKILL.md`。
2. 确认实际运行的 harness 和它的 skills 目录。模型为 DeepSeek 不代表安装目录固定：如果 DeepSeek 运行在其他 harness 中，使用那个 harness 的目录。从当前已加载 skill 的路径、harness 配置或其文档确认目录；不能确定时向用户询问目录。
3. 执行安装器。Codex 可使用 `--codex`；其他 harness 将实际 skills 根目录传给 `--dest`，安装器会在里面创建 `long-task-monitor` 子目录。

   ```text
   python install.py --codex
   python install.py --dest "/actual/harness/skills"
   ```

4. 用户先用 Owner 或管理员创建的账号登录监控网页，修改初始密码，在“我的账号 → 个人上报密钥”生成自己的密钥，也可下载 `client.env`。用户提供服务器时，可以同时配置连接。密钥只从 `MONITOR_TOKEN` 环境变量读取；不要通过命令参数或聊天索要密钥或登录密码。

   ```text
   python install.py --dest "/actual/harness/skills" --server https://ionthruster.xyz/monitor
   ```

   配置写入 `~/.config/long-task-monitor/client.env`，可用 `--config` 或 `MONITOR_CONFIG` 指定其他文件。安装器不会覆盖已有配置。缺少密钥时返回 `configuration: needs_token`，skill 会安装，但不会生成缺少密钥的配置文件；密钥就绪后再运行同一命令。
5. 检查安装器的 JSON 输出和目标目录。相同内容已安装时返回 `already_installed`；不同内容不会被覆盖。`kept_existing` 只表示原配置被保留，不表示它已通过联网认证。不要为安装验收发送任何任务或连接测试事件。
6. 如 harness 需要重新加载 skill，提示用户在新会话或下一次加载时使用。支持 `SKILL.md` 的 harness 可自行发现它；不支持 skill 发现的 harness，需要在适当的任务上下文读取该文件并执行上报脚本，安装器不会注入原生生命周期回调。

用户也可手动创建连接配置：

```ini
MONITOR_URL=https://自己的服务器地址/monitor
MONITOR_TOKEN=登录后自行生成的个人上报密钥
```

## 运行规则

仅当前实际 goal 任务或用户明确要求时上报。用户明确说不上报时优先遵从；之前完成的 goal 不会为新工作触发上报。剩余时间由 harness 根据剩余任务量评估，未评估时页面显示“未完成评估”。

上报用法、心跳、暂停、完成和错误处理见 [SKILL.md](skills/long-task-monitor/SKILL.md)。`--harness` 标注真实来源，其他 harness 无需修改服务器接口。

当前服务器使用 Owner、管理员和普通用户三种账号。普通用户只能查看、上报和删除自己的任务；上报密钥仅用于上报，删除需要网页登录。密钥完整内容只在生成时显示一次，遗失可重新生成；重新生成会让旧密钥立即失效，请同步更新所有使用此账号的 harness 配置。

## 安装器验证

```text
python -m unittest discover -s tests -p test_installer.py -v
```

这些检查只验证本地安装和配置，不向监控服务器上报。
