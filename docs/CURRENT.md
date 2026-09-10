# 当前状态

## 已验证能力

- 新版 manifest 3.0 / work model 2.0 已接通系列、单集、独立制作版本、创意段落、Cue、反馈、审阅集合与不可变交付。`afterforge.py` 提供 open/status/update/preview/deliver/resume；CLI 与 Review 使用同一应用层，新模型不调用旧阶段 resolver。
- 无粗剪可先策划；真实预览要求绑定输入和旁白依据。显式 copyFrom 创建新副本，原工程/投放区字节保持，旧批准不成为新授权。系列记忆与视觉默认更新不静默改变已有版本的规范快照。
- 2.0 入口清理：可选视觉语法与粗剪扫描参考已移除活跃旧阶段指令；legacy 副本仅继承视觉默认，已知旧审核模板在新副本替换，旧规范路径/冻结哈希不继承。未知视觉文案保留，其历史流程文字不拥有新版指令权威。
- 受控暂存发布、请求去重、版本锁与跨项目锁次序、并发反馈保留、失败续跑均有回归。显示状态可重建缓存与单操作哈希复用不拥有批准权威；批准与发布复核实际输入。已覆盖包发布响应丢失后的验证接回及 round-trip 基线/决定共同回滚。
- 实际依赖控制 Cue 缓存：说明和未引用素材不使媒体过期，放置起点改变复用媒体，时长/字体/样式/运动变化重建相关 Cue。480p 与原生渲染均来自 canonical composition/motion；局部合成保留全部重叠层、本地时间和粗剪声音。完整范围与重叠 Cue 全时长补充小样共同构成审阅集合，未完成讨论稿不能授权正式发布。
- 正式交付完整覆盖动画，验证 1920×1080 ProRes 4444、源帧率、精确时长与实际 Alpha。协议 2 的层级保持与合成一致，位于原正 lane 之上；原相对媒体引用在新 XML 中依据原目录规范化，原输入不改。FCPXMLD 平铺 XML/MOV，快照和复现源树在包外，重复输入复用经核验的旧包。
- 系列 Review 支持脚本思路、本轮变化、同源 Markdown 脚本导出、完整/局部/静帧、小样对照、整集时间定位、多 Cue/区间反馈、冲突草稿、明确批准与授权、任务恢复、导入包及独立 MOV。客户端回归覆盖小数秒转精确有理数，不再让用户选择 static/motion。
- 已执行 281 项 unittest 全量回归；新增覆盖 legacy 规范副本的视觉/YAML/BOM/换行保留、原目录不变、v3 再复制不变及不调用旧 resolver 的文案起步。Skill quick_validate 与旧 Stage Contract 生成一致性检查通过；本轮独立复核未发现遗留阻塞问题。
- 已用本地离线 HyperFrames 0.8.33 和 FFmpeg 多次完成 60 秒隔离合成样片。最终测试目录为 `/private/tmp/afterforge-work-model-final-20260910`：完整 854×480 / 24fps / 60秒小样含粗剪音频，三条时间修改及布局/样式修改已试做，四条原生透明 MOV 与协议 2 包/快照通过校验；投放文件哈希未变，摆放修改的缓存复用已验证。浏览器实际播放、时间定位与交付入口已检查。

## 验证命令

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
.venv/bin/python scripts/sync_workflow_stage_contract.py --check
```

显式隔离真实回归，输出目录必须不存在，精确 runtime 和本地 GSAP vendor 需已经可用；命令不安装依赖：

```bash
.venv/bin/python -B tests/work_model_real_smoke.py --run --root /private/tmp/afterforge-real-check --runtime 0.8.33 --gsap-source /absolute/local/gsap.min.js
```

## 待验证与下一步

- 协议 2 尚未在 Final Cut Pro 做实际导入及 re-export round-trip；自动包/比较器测试不代替这些动作。首次真实通过后由共享基线判断后续适用性。
- 十分钟以上真实制作验证留到下一次。当前真实回归使用一分钟合成媒体，不声称覆盖任意长片/素材/浏览器组合。
- 当前实现采用独立复制保存快照；没有引入媒体硬链接去重、数据库、云服务、自动转写或训练系统。动态引用仍需明确依赖声明。
- 两份已交付《楚门》legacy 工程（2026-09-01_v1 / runtime 0.8.26 与 2026-09-09_v1 / runtime 0.8.33）保持原位，本次未迁移或修改。继续真实制作时需用户明确选择新工作副本及输入。
- 《楚门》项目级 AGENTS/CLAUDE 与视觉默认已按用户授权同步到 2.0，`工程/frame.md` 已就位；四个历史制作目录保持不变，未创建制作版本或项目索引。用这些实际入口与默认的隔离副本验证了文案起步、规范继承及无需时间线/runtime/旧阶段门。
- 工作保留在 `codex/rework-lifecycle`，基础重构提交为 `89986d9`，入口清理已完成。十分钟以上真实 invocation 完成闭环后再考虑合并。尚未安装或导入真实 FCP 工程。
