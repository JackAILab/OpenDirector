# 资产版本与恢复规则

## 存储分工

| 存储 | 内容 | 可见性 |
|---|---|---|
| GitHub | Python/JS/CSS/HTML、轻量配置、测试、部署和清单 | 公开源码 |
| ModelScope `JackAILab/AdvertiseAgent_Assests` | 媒体、参考库 SQLite、分析证据、Skill 数据 | 私有 |
| 本机 Docker 卷与 `outputs/` | 用户账号、积分、项目、生成结果 | 本机私有，不随源码发布 |
| `secrets/` | Director/Kling 凭证 | 本机私有，不上传 |

`showcase` 是案例媒体归档，解压后保持项目相对路径。`library` 以单文件形式存储媒体，使用清单下载，可复用已验证文件。`learning` 是分析和 Skill 资产归档，恢复到素材库目录。

## 为什么用 Hub 下载而不是 MsDataset.load

数据集包含二进制文件与数据库快照，没有训练表格所需的 split/schema。`MsDataset.load('JackAILab/AdvertiseAgent_Assests')` 指向正确的数据集，但不能完成本项目需要的目录恢复与一致性验证。请使用 README 的 `scripts/download_assets.py`，它通过 ModelScope Hub 下载固定 commit 并检查 SHA-256。

## 更新发布流程

1. 在独立发布目录整理源码；不复制 `.env`、账号数据库、会话、任务日志和用户项目。
2. 对素材库和分析库使用 SQLite backup 创建一致性快照；按相对路径去重媒体，保留数据库内的所有引用。
3. 将新数据写入 `releases/YYYY-MM-DD/`。每次发布保留固定 commit，不依赖可变的 master。
4. 核对远端完整分页文件树的路径、大小、SHA-256，实际下载数据库和代表性媒体复验。
5. 把确认完成的资产版本写入 `assets.lock.json`，最后提交和发布源码。
6. 执行 `python scripts/release/check_source.py` 及本次变更对应的测试。

ModelScope 返回的 commit 和 GitHub commit 不是同一种版本号；资产锁文件负责连接两者。第三方素材保留原权利；私有存储不等同于可公开再分发或可训练。

## 本地恢复

先停止正在使用素材库的服务再恢复。下载器拒绝覆盖不同内容的文件或 SQLite 数据库。如需更新已有可写素材库，应下载到新目录、备份当前数据库，再决定迁移方式。中断后重跑会复核已存在媒体并继续缺失文件。

恢复完整广告库需要约 187 GB，再为分析证据、缓存与后续生成预留空间。没有库权限时仍可部署空白工作室，素材库与参考 Skill 功能需取得相应权限后恢复。
