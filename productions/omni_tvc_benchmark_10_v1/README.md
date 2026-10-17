# Omni TVC 十案例对比输入

每个案例将整个 cases/<case_id> 文件夹交给被测框架。prompt.txt 是统一简报；input.json 保存商品、人物、场景、时间段、媒体规格和评审条件；references 中是实际参考图。不要把本框架生成的视频提供给其他框架。

统一目标：15 秒、16:9、1080p、原生环境音/同步音效，无配乐、无旁白、无可读 UI。用户要求直接生成，无预览审批步骤。技术与内容审核在生成后执行，训练资格仍为 false。

参考案例采用手表微距、生活动作和多镜头产品展示；这十个案例是原创扩展，不复制原作者的人物或商品图片。

参考图实际模型为 CodeBuddy hunyuan-image-v3.0（技能中 gpt2-img 的兼容链路），视频目标为 Kling 3.0 Omni。Kling 登录已恢复，已开始提交实际视频任务。实时进度以 benchmark.json 和各案例生成记录为准；preflight 文件保留此前失败状态，不代表当前登录状态。

## 案例
- 01_smartwatch：智能手表｜从晨光到山脊
- 02_action_camera：运动相机｜穿过浪尖
- 03_perfume：香水｜夜色琥珀
- 04_sports_car：电动跑车｜雨后弯道
- 05_headphones：头戴耳机｜城市静下来
- 06_sneaker：运动鞋｜第一步
- 07_coffee_machine：咖啡机｜清晨的第一杯
- 08_skincare：精华液｜光穿过一滴
- 09_lounge_chair：休闲椅｜给自己一刻
- 10_rain_shell：冲锋衣｜风雨有形

## 使用入口

- `comparison-inputs-10-cases-v1.zip`：已齐全的十案例输入，可直接发给其他框架。
- `delivery-status.json`：根据真实生成记录与审核证据汇总，不把技术通过等同内容通过。
- 本地制作台：`http://127.0.0.1:50442/tvc`，成片逐条投影，不展示虚假可播放占位视频。
- 每条源视频与生成记录位于 `outputs/artifacts/omni_tvc_benchmark_10_v1/<case_id>/`，相对于仓库根目录。
- `media-review` 中技术证据包括完整解码、时长/分辨率/音轨、半秒抽帧与音量测量；独立视觉检查记录在 `semantic.json`。音轨测量不能替代连续听审，未验证的同步/配乐/语音判断明确保留为未验证。

## 本轮实际结果

已完成 5/10：运动相机、香水、电动跑车、头戴耳机、咖啡机。回执累计 900 点；Kling 当前剩余 179 点，精华液提交因不足 180 点失败且没有 generation ID。剩余五条预计需 900 点，按该余额预计至少补 721 点。`completed-videos-05-v1.zip` 是五条实际视频与审片记录，解压后打开 index.html 播放；不是十条完整交付。所有后台付费队列已停止，等待额度恢复。
