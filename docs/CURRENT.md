# 当前状态

## 已验证能力

- 2026-10-18 审核闭环第一轮：完整 Demo 的 CLI preview／缓存／resume 自动返回精确制作版、Demo 页与产物的可用入口；服务身份查找／启动留在 CLI 层。可见空闲页低频发现新片并提示切换，保留旧播放器和草稿。新视频冻结最小场景时序，捕获、导航、反馈批次与明确返修均绑定所审产物；无映射历史视频仍可保存视频／时间／正文，旧对象范围不转给复用技术 ID 的新对象。明确返修在原事务登记新 taskId，普通保存／提交无制作授权；委托状态可查询。合成样例实际完成浏览器返修并生成两版 12 秒／24 fps Demo，A/B 从 1s/7s 改为 7s/1s；原页发现新版后继续审旧片，新意见及提交仍归旧 A，再手动查看新版。返修 A 重建、B 命中缓存，只有两次制作任务，输入哈希不变。最终固定代码 540 项 unittest 通过（138.547 秒），Skill／合同投影／JS 语法／diff 检查通过；19 个交付相关源码和测试与基线逐字节一致，协议 3 与交付合同未改。证据集中于 `work/review-integration-20261018/`。第二轮未施工，等待父级独立验收；本轮无真实作品修改、正式交付或 FCP 操作。

- 2026-10-18 审核页取消独立交付标签、列表及其渲染调用，保留三个核心工作区和可选探索。Demo 的准确 reviewSet 确认及全部后台交付生成、检查、历史、下载能力不变；完成后在线程提供真实交付目录、XML 和全部带 Alpha 通道的动画 MOV，不新增审批。本轮未触发正式交付，实际交付链路及 FCP 导入验收尚未由本轮验证。 定向 Review 16 项通过（11.580 秒，包含 37 个客户端场景和后台下载回归），Skill／合同投影／JS 语法／diff 检查通过；Chrome 实际刷新显示三个核心页，版本及 11 场正常加载，分镜／Demo 可切换，交付确认入口保留。8796 返回的 HTML/JS/CSS 与工作区字节一致，revision 213 未变。

- 2026-10-18 用户确认新版审核页前三页（画面方案、分镜与动画、整片 Demo）没有问题。本条仅记录页面验收，不代表整片批准、交付授权、正式交付生成或 FCP 导入链路通过；用户随后批准取消独立交付页，成品在线程提供；整片 Demo 的明确交付确认保留。

- 2026-10-18 审核页接入定稿原型，沿用真实版本选择与 API：画面方案、分镜与动画和整片 Demo 三个工作区使用连续场景卡；概念候选浏览、采用与确认分开，同卡切换实际静帧与本场视频。静帧／动画单场确认保存内容绑定的 sceneReviews，只是审阅进度，不新增制作门或生产权限。概念 select 原子处理已确认后的明确改选／历史图重用，原图、来源链与反馈保留。此布局取代下方旧三列卡片与按钮文案记录，历史 2.1 确认语义保留。 概念顶部及弹窗主按钮使用“确认方案，继续制作分镜”，成功提示为“方案和本次制作范围已保存。回到对话后可继续制作分镜。”，范围摘要使用“本次制作／暂不制作”；仅文案调整，交棒与回执两个定向客户端场景通过。
- 草稿、保存与提交分别显示；开始输入冻结原图／帧／视频与场景时间。隔离真实 Review 验证切帧后仍保存原帧、Demo 从 03:21 跳到 07:39 后仍保存原时间和场景、刷新恢复单场进度，以及新增反馈显示待处理；提交没有新建 Demo 委托。明确整片合并批准／交付绑定准确 reviewSet，调用现有交付入口，正式协议和发布校验器未修改。本轮没有实际渲染、正式交付或 FCP 操作。
- 未来创作输入沿用本版 `.staging/creative-inputs/<round>/` 中转与 `assets/concepts/` 全候选登记，参考和提示词保存到 `assets/design-inputs/`，制作素材保存到 `assets/materials/`。工具目录与临时路径只作来源追溯，不能是唯一可用副本。历史文件不自动移动、删除或补登记；本轮明确批准的 60 张固定清单归档见下方当前验收证据；开发验收证据统一位于已忽略的 `work/review-integration-20261018/`。

- 2.2 Storyboard 已恢复「通过并开始制作动画」入口：明确勾选制作／暂缓范围，复用 authorize-demo 保存当前静帧依据和 taskId，不直接渲染或重复确认概念。交棒状态刷新保留，Agent 按原 taskId 继续；未保存草稿、旧快照及范围缺口拒绝提交。新增回归先复现缺少入口和快照校验，再验证保存、重复点击、暂缓、刷新和过期依据；507 项完整测试、Skill／合同投影／JS 语法检查通过。实际 Chrome 已核对本版 10 条制作＋五线谱 1 条暂缓的弹窗，未向制作工程提交测试批准。

- 概念大图支持当前 Cue 内的前后箭头、键盘左右键和张数提示，首尾停止；单图及 Storyboard 图片隐藏导航。顶部列出未确认 Cue 的名称和原因，反馈阻塞卡片显示待处理状态。回归先复现缺少导航，再验证候选边界、静帧切换清理及待确认清单；真实 Chrome 验证箭头与键盘切图，504 项完整测试通过。

- 概念 Review 使用桌面固定三列的卡片，窄窗口降为两列或单列；取消主图高度上限，让图片随卡片宽度放大。保留点图放大、说明展开及倒序历史缩略图。实际浏览器核对 1920/1000/700px 宽度分别为 3/2/1 列；此前已验证过程稿放大、原确认与反馈绑定，504 项完整测试通过。本次列数调整为纯 CSS，diff 检查通过。Skill 明确用非推荐候选保留迭代图，未改确认合同或交付基础设施。

- 2026-10-11 概念图制作方法已写入 Skill 主流程与现有设计参考：传递视频情境、参考图角色和时间状态，区分实际约束与开放设计，Agent 自主看图、多轮修改、重起错误方向，并以真实表达差异组织候选。同步 README、Agent 导航及决定记录，修正设计参考残留的旧 Storyboard 首次确认说明。依据本轮实际图像迭代与用户要求完成文本核对，Skill 校验、合同投影和 diff 检查通过；未修改运行时代码或交付基础设施，不把静态候选视为动态验收，也尚未证明新指令在独立新 invocation 中的执行效果。
- 概念图收口：Review 在已确认图片丢失或内容变化时显示“已确认 · 概念图不可用”及恢复原图提示，保留原始确认；图片恢复后恢复制作提示，无需再次确认。复用现有状态，后端与制作门禁未改。Skill 按概念图片、已登记的非空 idea/motion 说明及现有内容／反馈条件描述确认，明确 finalAnimationDescription 不是概念确认条件。新增回归覆盖图片缺失／变化／恢复与缺省／空白最终说明；26 项定向和 504 项完整测试通过，Skill、合同投影、JavaScript 语法及 diff 检查通过。日志 `/private/tmp/afterforge-concept-closeout/unittest.log`。
- 主施工验证：502 项 unittest 全部通过（70.630 秒），新增概念稿公开接口与共享 job 路径测试覆盖候选/采用、批量原子性、原图反馈、改稿轮次、缓存及恢复；客户端延迟响应回归覆盖跨版本确认回执。独立审核发现的回执串版问题已修复并复审通过。Skill、合同投影、JavaScript 语法与 diff 检查通过；7 个受保护交付模块/测试文件与本轮前哈希相同，交付合同字段及协议 3 未改。日志 `/private/tmp/afterforge-concept-implementation/unittest-final.log`。
- 2026-10-11 概念图优先：fresh work model 2.2.0 / manifest 3.0 新增独立概念稿、持久受控图片、推荐/确认/显式改稿轮次和 `confirm-concept` 批量决定。两种图片来源共用事务、Schema、媒体访问与反馈归属；上传候选不取得资格，明确采用可一次导入确认。源码发布、代码探索/采用和既有 `_spec` 预览/缓存/恢复路径读取同一概念依据。Storyboard 检查实际制作，不重复首次设计确认。历史 2.1 与更早证据保持原语义；本节下方旧“Storyboard 首次确认”记录仅描述该历史版本。
- 官方独立 Skills 更新完成：既有 11 组，实际来源提交 `8bca7c4417b59b47fca851183a8d47a4565bad0c`，各目录哈希与该提交一致；有效加载路径为全局 `.agents/skills` 与 `.claude/skills`，旧 Codex 镜像链接由官方安装器移除。精确 runtime 0.8.146 已通过 AfterForge 本地图片/中文字体 PNG、GSAP 0/1 秒 seek、2 秒透明 ProRes 4444、24 fps/48 帧和实际 Alpha 核验。本地 HyperFrames 源码仍为 `0945de83`，历史制作 pin 未改，没有安装插件。前后记录及预检位于 `/private/tmp/afterforge-concept-implementation/` 和 `/private/tmp/afterforge-concept-runtime-0146-browser/evidence.json`。
- 两种来源实际路径：2 张真实 Codex 工具生成图及 1 张真实外部导入图，在隔离 Review 显示/放大/混合批量确认，刷新、服务重启与项目重新打开后图片和关联仍在。读取已保存概念后制作整体海报、关系解释图和原片标注，实际生成 6 张 PNG、3 个局部视频及每条 4 秒/24 fps/96 帧的 MOV；保留主要构图、层级、素材关系，原图哈希全部不变。证据 `/private/tmp/afterforge-concept-acceptance-20261011/` 中 `prepare-evidence.json`、`browser-evidence.json`、`production-evidence.json`、`visual-check-evidence.json` 及页面截图。模拟确认只在隔离工程，不修改旧 invocation 或真实制作，也不冒充正式交付/FCP 验收。

- 2026-09-27 D0002 实际 FCP 往返完成：用户提供的“原样回导”经正常 `update operation: roundtrip` 后端通过，登记 `decision-bce34a7d55a8`，制作版 revision 255，系列 `protocolBaselines["3"]` 指向 D0002。17 个正式媒体哈希/格式/帧率、13 个本轮动画位置/时长、继承动画及原故事线通过；XML 与 MOV 字节未改，没有重渲染。结果记录 `fcpxml-1.14-basic-title-v1` 的 21 个系统颜色转换及 3 个默认选择器省略。492 项完整测试通过，Skill 与合同投影检查通过，实际证据追加至原迁移证据目录。
- 本次兼容依据来自两份实际回导及 macOS ColorSync 复现：Generic RGB → sRGB → Generic RGB 与 FCP 的六位有效数字结果精确匹配；Basic Title 已知默认字体/左对齐选择器只在显式 rich-text 内容、字体/字形/字号及 LTR 左对齐不变时允许省略。Alpha、实际文字/样式、未知参数/模板/版本与时间变化仍拒绝，无校验环境不能跳过。发布前源 XML 不变性验证不使用该兼容规则。新增回归同时证明中途改 XML 不产生往返决定/基线，以及协议 3 的状态不会误读旧协议 2 基线。

- 2026-09-26 交付协议 3：普通浅层目录、完整动画资源图（含继承/嵌套/多次引用）、旧 bookmark/替代定位清除、实际 ProRes 4444 校验、全 AfterForge 正式媒体哈希/inode 唯一性、轻量 release、正式缓存索引和所有发布/复用/恢复入口已接入同一后端。协议 1 新包 writer 关闭；协议 2 仅历史验证。合同、Schema、README 投影和说明同步。该轮 481 项测试通过，Skill 校验与合同投影检查通过；原字幕样式引发的往返阻塞已在上述 2026-09-27 验证中解决。
- 2026-09-26 经用户追加确认 09-01 的 5 处原位硬链接去重后，楚门真实迁移和固定清单清理完成：`AfterForge/交付/片头-D0002/` 直接包含 1 个 XML 与全部 17 个 MOV（13 个当前 + 4 个沿用，共 1,042,500,959 字节）。普通交付后端执行，动画重渲染次数为 0，媒体字节、源时间线、审阅和授权事实不变。迁移完成时制作版 revision 253，仅 D0002 留在当前交付集合；D0001 原记录/XML/manifest、旧任务原文和迁移证据保留。
- 全域正式媒体唯一性检查通过；09-01 的 5 个历史文件保留全部原路径及哈希。已删除 08-25、08-26 工程及固定清单中的旧 D0001 表示、正式缓存媒体和 snapshot 大资产副本；仍被 FCP 引用的 08-26 包、09-09 工程/包、桌面 INBOX、本轮指定保留的 5 个旧 Demo 及当前 `.staging` 保留。按 inode 去重的已分配空间由 15,518,916,608 降至约 11.04 GB，减少约 4.48 GB；同次卷空闲空间实测增加约 4.48 GB。两项口径分别记录，不把硬链接路径数或临时隔离副本计作减量。
- 实际 D0002 的隔离独立性验证通过：副本仅有正式文件和轻量证据，禁止读取真实工程和旧包后仍能验证全部 17 个媒体；临时媒体副本已清除。真实证据位于 `/Users/xiaobaimac/Movies/trumen/AfterForge/工程/episodes/episode-bd459610b45a/version-d7c63089d9f1/releases/d0001/migration-20260926/`，包括前后完整清单、实际删除清单、哈希/inode、硬链接授权与结果。独立自动校验与实际 FCP 验收分别登记，不互相替代。

- 2026-09-26 FCP 排查来源：用户“fcp 验收没有问题了”经统一后端登记 `accept-import`（`decision-177728885e83`，revision 254）。两份回导分别为 `片头-D0002-FCP回导.fcpxmld` 和未编辑的 `片头-D0002-原样回导.fcpxmld`，均只含 XML 1.14 的 `Info.fcpxml`。初版严格比较在全部 17 个媒体/时间核对通过后，被同样的 21 处颜色与 3 个省略参数阻塞；项目改名不参与比较。原失败回执、逐项差异和两份输入的只读证据保持原文，新机制及成功记录另行追加，没有把旧失败结果改成成功。

- 2026-09-26 随机缓冲排查：视频 Range 请求此前调用完整 status，状态缓存失效时在真实工程测得首字节等待 16.57 秒。媒体读取改用只读登记索引并保留 allowlist／路径检查，正式服务冷请求降至 0.17 秒；不改变资格及 writer 核验。新增回归阻止 Range 请求调用完整状态，且验证素材移除立即生效；452 项回归及 Skill／合同校验通过。保存意见按钮移至取当前播放时间旁。此结果证明该阻塞已消除，不宣称排除所有浏览器卡顿原因。

- 2026-09-26 Demo 编码改为 H.264 CRF 23、受限峰值、约两秒 GOP、faststart 与 AAC 128k。8 项媒体回归（真实有理帧率、音轨、图层时序及 faststart）及完整 451 项测试通过；编码变化不影响 ProRes 4444。楚门本版经正式 preview writer 重合成，13 组均缓存命中，文件从 878,695,649 字节降至 36,299,145 字节，14,903 帧 / 24 fps / 620.958333 秒保持一致；未执行反馈中的动画修改。

- 2026-09-26 Demo UX：沿用现有 Review 样式，动画 Cue 导览只跳转，默认选择最新完整视频，静帧不混入素材列表；紧凑反馈框移至视频下方，开始输入自动暂停并固定播放时间，保存后下一条重新取时；显式整版意见不绑定时间，旧无时间草稿不猜测补时。取时间暂停且不重建播放器，输入区以外空格控制播放／暂停。当前视频意见按保存与提交轮次分开，刷新恢复提交事实；视频意见支持撤回／恢复，复用 feedback-applicability 保留原文与轮次历史，撤回后排除待提交与修改要求，失败不假撤回；效果通过只记录 approve，之后才显示交付操作。历史失败任务置于次级记录，不覆盖当前回执。隔离真实工程副本已通过保存、提交、刷新恢复及宽屏视频／输入区同时可见检查，原制作版 manifest 哈希未变；测试反馈仅存在于 `/private/tmp/afterforge-demo-ux-20260926`。客户端回归覆盖取时间不重播、导航不改反馈、素材过滤、轮次范围、空格输入例外、保存去重与慢刷新／逆序响应、撤回去重／失败保留／恢复及提交历史保留；完整 451 项回归、Skill 校验与合同同步通过。

- Storyboard 新增「确认本轮设计」与页内范围摘要，批量记录待首次确认的完整 Cue；已有资格保留，不跳过缺失／过期或有待处理反馈的 Cue，未保存留言先处理。提交前重新读取状态并核对摘要依据，取消、切版、设计变化和重复点击不会误确认；成功资格由服务端状态恢复。工作意图按版本／页面记忆折叠，Storyboard 默认收起；专用 Cue 导览在宽屏固定侧栏、窄窗横向排列，跳转／滚动高亮不改变反馈目标。该轮 Demo 保留既有布局与批准操作；现以本节 2026-09-26 的 Demo UX 为准。2026-09-24：451 项回归、Skill 校验及合同同步通过；新增批量确认场景经过先失败后通过验证，浏览器检查宽窄布局、末组定位、折叠跨页／刷新记忆及真实范围弹窗（未提交真实确认）。

- Storyboard 局部 `animationNotes` 与逐帧 `narration` 映射已接入：说明支持单帧、多帧、共享帧及无说明帧；映射保存每张图片对应的原句并允许重复，缺失映射明确显示“尚未标注对应旁白”，不从时间、Cue 旁白或说明推断。帧重组须同步引用。总说明、局部说明、逐帧映射、旁白、内容事实与有序帧集合冻结为 `reviewInputKey`；映射文字变更复用 PNG，首次确认仍覆盖完整 Storyboard／创意对象。
- PNG 合同 5 将纯说明与图片输入分开，文字修改可零渲染复用 SHA 一致的 PNG，同时追加不可变产物和审阅快照。合同 4 按原输入核验，无法证明一致或图片损坏时重渲；发布前复核输入及输出文件。旧快照不能确认新内容，旧反馈及已有首次资格保留。
- 本版 `workingIntent.items` 通过受控 `working-intent` upserts/removeIds 持久保存，支持定向覆盖、显式移除、失效定位和并发冲突。写入不升级生产事实、不影响渲染/审阅/首次资格/交付，新版本不继承；Agent 恢复规则与只读展示已同步。
- 逐帧保存结果在本帧按钮下显示，空内容、失败、再次编辑和保存后刷新失败均有就地说明，草稿及跨版本迟到响应隔离保留。连续保存按制作版串行发送写请求，保存回执立即更新 revision；列表刷新不阻塞下一条写入，迟到的旧 revision 不覆盖较新状态。2026-09-22 连续保存修复后 451 项回归通过，覆盖慢刷新、快速两帧保存和刷新响应逆序；隔离真实 Review 服务将状态刷新延迟 4 秒，浏览器未手动刷新连续保存 3 条且无重复，未往制作工程写测试反馈。
- Storyboard 顶部三个按钮共享就地回执，点击后禁用重复操作；反馈提交显示条数／待处理，局部确认显示组数且提示先勾选，静帧生成按本次 requestId 跟踪到完成或失败，历史失败不覆盖本次结果。已提交轮次在刷新页面后仍显示，迟到响应按版本隔离；本轮 451 项回归和隔离真实接口浏览器检查通过（合成图片 fixture，仅验证按钮与任务生命周期），真实工程反馈与确认事实未改写。
- 正式 Review 已采用顶部版本/Cue 导航、桌面三列静帧（窄屏两列）、局部说明与关联高亮、图片放大、默认展开且逐版本/对象/帧记忆的留言框和 sticky 反馈栏。新快照清除旧依据勾选，旧草稿不自动转绑。长任务准备期可持续轮询，临时任务/失败按制作版隔离；切换空白版不残留上一版媒体。后台 hero 规则不变，未增加已保存反馈编辑。
- manifest 3.0 / work model 2.1.0 / 交付协议 3 已实现。`open/status/update/preview/deliver/resume` 与通用 Review 使用同一应用层；兼容读取旧 work model 2.0.0，读取不落盘、不补资格。schema 2.0 保持 legacy 原义，新生产不调用旧阶段 resolver。
- cold-start 从真实 canonical 布局独立生成主审／辅助 PNG，支持中文字体、静态状态及对应原片背景，无需完成 Motion。首次确认引用当前可验证完整帧集合；限定探索、整版 Demo、完整 Review 批准和正式交付授权分别保存事实。
- 首次资格绑定产品创作对象。字体、构图、摆放、运动、重做以及明确的技术改名保持 active；真正新增对象不继承资格。对象关系有实质歧义才询问，不建立阶段回退。
- 工作 Cue、预览时间与 Demo 呈现范围分离。未修改的有效实现默认呈现，缓存缺失可按原实现重建；明确排除和缺少实现单独记录，不能形成完整 Review。局部上下文不扩大创作范围。发布、恢复、缓存和已完成任务返回均核验当前依据。
- Storyboard 承接通用 Review 的旁白、主审／辅助帧、最终说明、就地反馈及批量确认。“提交本轮反馈”固定反馈批次，零评论不产生批准；处理与接受分别记录。草稿保护包括原帧更新、跨版本选择、迟到响应及刷新。
- 视觉探索是可选并列工作区，候选切换无采用副作用；范围明确的采用与 canonical 源更新原子提交，候选不进入正式 Cue 集合，不授予首次确认、Demo、Review 或交付资格。
- 输入候选不按排名自动决定；多 XML／多 Project 不静默取第一个。复制和系列默认使用明确委托，不自动推导跨版本关系。通用记忆初始化中性；完整 Review 不自动接受全部 addressed，明确暂缓事项不阻塞无关成果。
- 原有有理数时间、Cue 本地时间、重叠层、依赖缓存、版本锁、请求去重、失败恢复与不可变交付继续通过回归。正式包保持原生 1920×1080 ProRes 4444、源帧率、实际 Alpha、时间线不变性与协议 3 正式目录核验（旧协议只读）。
- Motion 发布边界由 canonical 源结构及依赖闭包统一判定，覆盖 inline script、事件、CSS／SVG 时间行为、嵌套源、播放媒体及共享依赖；不是只查 `motionSrc` 或动画关键词。独立静态宿主不执行用户脚本或 vendor JS，不能通过移除声明把 Motion 改称静态。
- 当前静帧有效与可首次确认分别投影。旁白和屏幕文字各自区分 present／none／unknown；明确无内容须有依据，未知不能被另一通道掩盖。确认仍要求非空最终说明和无相关待处理反馈。事实来自现有真实文本或关联段落，不生成假占位文字。
- 确认、批准和交付使用同一反馈适用范围解析器。未采用探索意见不阻塞正式成果；采用关联绑定真实候选源／背景指纹与产品对象。同路径修改不会沿用旧候选事实；对象改名、摆放变化不自动解决旧意见。
- runtimeIdentity 区分 bootstrap、旧环境登记、同指纹修复与真实变更。静态 Cue 可以先于首次 runtime 建立；固定 vendor 由 runtime writer 独占，初始化不产生制作依据。
- 有限静态能力模型核验 HTML／CSS／SVG 和图像实际格式；srcset、image-set、嵌套图像和字体资源进入闭包。不可确定的自动播放须改用固定采样或 seekable 实现。隔离渲染宿主用 CSP 拒绝网络，资源拒绝与本地 404 会阻止产物发布。
- 完整 Demo 默认拒绝缺失授权呈现对象，不静默缩小范围；明确 `allowDraft` 的讨论稿仍可生成，但不完成原任务。只有实际履行委托目标才登记 production run；历史误登记通过有证据的追加纠正解除，不重写历史产物。
- 跨版本明确区分 `copyMode: restart` 与逐对象 `objectContinuity`，由 Agent 落实用户决定，backend 不解析原话或猜测关系。延续仅携带有出处的首次资格，不携带整版制作、Review 或交付授权。首次 writer 完整登记缺失对象身份，不补用户批准；`inputSelection` 为公开字段，兼容 `selections`，双字段冲突明确拒绝。

## 当前验收证据

- 2026-10-18 跟进：concept-handoff 将待确认概念和包含／排除范围原子保存为 storyboardHandoffs；全部已确认仍保存，status 恢复最新交棒，失效仅提示。实际写入回执与刷新分开，确认概念／采用候选／单场确认的刷新失败只重试读取。最终关联 69 项通过（23.628 秒，包含真实 Review HTTP 测试与客户端 36 场景），客户端另行 36 场景直跑通过，均为本次定向证据，日志位于 work/review-integration-20261018/followup/。下方 524 项是此前主施工完整回归，未冒充本次跟进的完整回归。
- 经明确批准，固定 60 张历史 PNG（91,597,985 字节）已从对应 .codex/generated_images 会话移入单集 episode-f8eae2f90598 的过程归档/20261018/generated_images/原会话目录；原名和逐项完整 SHA 全部一致。48 张受控概念同字节副本与 12 张未登记会话过程图分开记录，后者未推断 Cue、未补登记。归档索引保留原来源；冻结制作版 manifest SHA 前后同为 8785399dd634caf892d6c8112d539fa296f49627906fd44d1704bfce7a58d700，受控图片字节未改；归档在正式版本外。证据 followup/historical-archive-result.json。

- 2026-10-18 最终完整 unittest：524 项、74.271 秒全部通过，日志 `work/review-integration-20261018/unittest-final.log`；其中客户端 harness 覆盖 34 个交互场景。独立复核发现的切版错投、跨版迟到弹窗、本场视频场外定位和复制谱系反馈逃逸均留有先失败后通过证据，交付重复点击也有专门回归。Skill、合同投影、五份 JavaScript 语法及 diff 检查通过；14 个受保护交付模块／测试文件 SHA 与开工前相同，交付合同对象及协议号未变。
- 隔离审核 UI 副本与证据均在 `work/review-integration-20261018/`：`browser-fixture/prepare-evidence.json`、`candidate-browser-evidence.json`、`browser-evidence.json`、`demo-feedback-desktop.png`。原制作版 manifest SHA 前后相同；单场确认和反馈提交没有改变决定、制作任务或 productionRuns。浏览器决定只属于副本，整片交付弹窗仅查看不提交；没有真实渲染或正式发布。该副本不是新制作资格或 FCP 验收证据。

- 2026-09-22 当前分支复核：最终完整 unittest 运行 451 项并全部通过，日志 `/private/tmp/trumen-unittest-0922-final.log`。逐帧旁白映射另有 `ReviewContentTests.test_frame_narration_mapping_invalidates_review_and_reuses_pngs` 与 legacy fallback 定向回归，覆盖映射变更失效审阅、PNG 复用、多帧同句、缺省映射及无 `reviewInputKey` 历史快照失效。本轮生产实测另验证纯映射更新的3张PNG哈希一致且零重渲，浏览器逐帧旁白显示已核对；生产数据不纳入仓库。
- 2026-09-20 审核页实现：449 项 unittest 通过（原 439 项及新增 10 项，客户端场景同时增加），日志 `/private/tmp/afterforge-review-unittest-final.log`。覆盖说明快照/引用、旧合同与损坏图片、图片输入失效、发布并发、意图对批准后交付依据无影响，以及反馈、批量确认、迟到响应和 hero 原有规则。Skill 校验、旧合同一致性与 diff 检查通过。
- 真实 PNG 复用与隔离页面：`/private/tmp/afterforge-review-content-20260920-r2/evidence.json`。只读 0917 制作源的隔离副本，2 Cue / 13 张实际 PNG；首次 13 次渲染，纯说明更新 0 次，13 个 SHA 一致，产生新 Storyboard，原制作源全文件哈希未变。第一次沙箱 Chromium 启动被 macOS MachPort 权限拒绝；在获准的隔离运行环境中通过，未为此改渲染实现。
- 浏览器实操：同目录 `browser-evidence.json` 与 `browser-desktop.png`。桌面 1440×1000 下六张完整帧可同时可见，反馈栏 top=12px；600px 下为两列且无横向溢出。验证默认展开/逐帧恢复、刷新/任务轮询、说明关联/全部展开、放大/Esc、保存反馈/轮次交棒/完整 Cue 确认、新快照清勾选/保留原依据草稿/显式重绑、旧反馈保留及版本切换。页面模拟决定仅在隔离副本，未安装或迁移真实工程。

下列为既有能力的前轮证据；当前页面实现以上述 2026-09-20 记录为准：

- 第二轮 integration 修复：439 项 unittest 通过，较 383 项基线新增 56 项。日志 `/private/tmp/afterforge-integration2-fix/unittest-complete.log`；定向日志、失败复现与修正后的结果保留在同目录。Review shell、客户端代码及客户端 harness 的字节与修复前审计清单一致。
- 本轮真实 cold-start／active-loop：`/private/tmp/afterforge-integration2-real-r3/evidence.json`，本轮先发布静态 Cue 再初始化 runtime；4 个对象、5 张真实中文主辅帧，静态路径视频渲染／合成调用为 0，后续局部修改、重叠、排除、缓存重建与复用、改名和协议 2 包继续通过。
- 无旁白无文字及固定背景：`/private/tmp/afterforge-integration2-pure-visual-r2/evidence.json`，真实 PNG 可首次确认，未制造旁白或文案；GIF 背景明确记录第 0 秒及源 SHA。实际 renderer 的网络与本地缺失资源拒绝：`/private/tmp/afterforge-integration2-render-guard-r2/evidence.json`。
- 本轮成熟 Storyboard：`/private/tmp/afterforge-integration2-review-r2/evidence.json`，4 Cue／7 帧及 2 个候选；最终实际输入关联复验在同目录 `lineage-evidence.json`。
- 本轮事故恢复：`/private/tmp/afterforge-integration2-recovery/evidence.json`，160 个原文件前后 SHA 一致，历史预览与 reviewSet 原样保留且没有取得合法资格。副本从原 HTML 补齐真实屏幕文字记录后产生新输入键，18 条媒体据此重建；18 份 Storyboard 与新的合法 Review 单独建立，未批准或授权交付。未变输入的缓存复用由上述 active-loop 实测覆盖。
- 本轮 9 个 Agent 场景：`/private/tmp/afterforge-integration2-agent/evidence.json`，含明确无旁白／无文字的新场景。Demo 排除的一次参数纠正轨迹另存于对应 case 的 `trace-failed-attempt.jsonl`，保留原失败证据；结果不声称首次调用全成功。场景使用媒体 stub，不是自然语言模型通用成功率测试。

下列为前轮保留证据，不代替本轮结果：

- 383 项 unittest 通过，较复核基线净增 60 项；Skill 校验、旧 Stage Contract 一致性和 `git diff --check` 通过。日志：`/private/tmp/afterforge-21-repair-evidence/unittest-final.log`。新增定向覆盖结构发布旁路、任务履约／失败恢复、对象延续／writer 升级、反馈与确认、输入字段；原 active-loop、局部讨论、排除和客户端回归继续通过。
- 真正冷启动：`/private/tmp/afterforge-repair-real-20260919-r2/cold-start-evidence.json`。全新 open，4 个动画对象、5 张真实中文 PNG，初始无 Motion 实现；实际视频渲染／整版合成调用均为 0；交棒后确认数为 0。保留了此时 manifest，后续静态确认不倒写到这个快照。
- 创作循环：`/private/tmp/afterforge-repair-real-20260919-r2/evidence.json`。一分钟合成时间线，真实中文字体和原片背景；修改、重叠局部试做、同对象改名、新对象隔离、未修改层呈现、缓存重建、明确排除和最终协议 2 包均已运行。输入哈希未变。
- 成熟 Storyboard 基线：`/private/tmp/afterforge-repair-review-20260919/evidence.json`。从只读 `2026-09-09_v1` 显式建立隔离 fixture，4 个动画 Cue、7 张真实主辅帧及 2 个探索候选，历史源哈希不变。
- 浏览器定向操作：`/private/tmp/afterforge-21-repair-evidence/browser/evidence.json`。真实页面保存当前帧意见后仅相关 Cue 禁止确认；提交反馈只交棒，不批准；随后其他 Cue 独立确认成功，待处理意见仍保留。目录含截图、DOM 和最终 status。既有草稿、批量确认、探索切换及冲突保护由客户端回归继续验证；所有页面决定仅为隔离验收模拟。
- 事故恢复：`/private/tmp/afterforge-repair-recovery-20260919-r2/evidence.json`。同版字节复制，不使用 copyFrom 伪装冷启动；原有 3 个预览产物、2 个 reviewSet 原样保留但无当前资格，旧恢复被拒绝。补齐 18 份 Storyboard 和模拟明确决定后，18 条媒体经实际指纹／SHA／属性核验全部命中缓存，重新合成 620.96 秒 Demo 并建立新 Review。没有批准 Review 或授权交付。源目录 160 个文件前后 SHA 清单相同。
- 8 个实际 Agent 原话场景及调用轨迹：`/private/tmp/afterforge-repair-agent-20260919-r2/evidence.json`。覆盖继续、交棒后处理、批量通过、只改 A、排除 D、整版请求、技术改名及歧义澄清。语义 fixture 使用媒体 stub；它是一次可审计的 Agent 执行证据，不是自然语言路由器或通用成功率测试。

## 验证命令

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" .
.venv/bin/python scripts/sync_workflow_stage_contract.py --check
```

2.2 概念优先真实验收分 prepare / render；prepare 输出目录必须不存在，生成图须实际来自图像工具，外部图须有真实来源。浏览器确认仅在隔离工程模拟，render 读取持久化确认图并产出 PNG/MOV。旧 real/review harness 明确使用 2.1 历史 fixture；事故恢复保持历史源合同，不代替新版验收。

```bash
.venv/bin/python -B tests/work_model_concept_smoke.py prepare --run --root work/concept-check --generated-concept /absolute/generated.png --external-concept /absolute/external.png --annotation-concept /absolute/annotation.png --source-frame /absolute/source.png --poster-frame /absolute/poster.png --font-source /absolute/chinese.woff2 --gsap-source /absolute/gsap.min.js --runtime 0.8.146
.venv/bin/python scripts/serve_workflow_review.py work/concept-check/AfterForge --port 8788
# 在隔离 Review 查看并确认三图，刷新、重启服务、重新 open 后执行：
.venv/bin/python -B tests/work_model_concept_smoke.py render --run --root work/concept-check
```

真实渲染仅使用预先可用的本地精确 runtime、vendor 和中文字体，不安装或升级依赖。所有输出目录必须不存在；本地 Chromium 需具有正常启动权限：

```bash
.venv/bin/python -B tests/work_model_real_smoke.py --run --root work/real-check --runtime 0.8.33 --gsap-source /absolute/local/gsap.min.js --font-source /absolute/local/chinese.woff2
.venv/bin/python -B tests/work_model_real_smoke.py --run --cold-only --root work/cold-check --runtime 0.8.33 --gsap-source /absolute/local/gsap.min.js --font-source /absolute/local/chinese.woff2
.venv/bin/python -B tests/work_model_review_smoke.py --run --root work/review-check
.venv/bin/python -B tests/work_model_review_smoke.py --run --review-content --root work/review-content-check
.venv/bin/python -B tests/work_model_production_recovery.py --run --root work/recovery-check
```

Review 与恢复项读取 harness 中明确列出的《楚门》历史源，只写隔离副本；其他机器需先具备相同只读 fixture，不能用原工程代替输出目录。Review fixture 建成后按返回的 AfterForge 路径运行通用 server，浏览器仅操作副本。

第一轮完整审核闭环使用 opt-in 合成样例，不读用户作品；prepare 的输出目录必须不存在，本地 runtime/vendor 已预先具备：

```bash
.venv/bin/python -B tests/work_model_review_loop_smoke.py prepare --run --root work/review-integration-20261018/round1-loop --vendor /absolute/local/gsap.min.js --runtime 0.8.146
# 浏览器在 first-stdout.json 的 reviewEntry.url 保存意见并明确返修后：
.venv/bin/python -B tests/work_model_review_loop_smoke.py revise --run --root work/review-integration-20261018/round1-loop
```

同页等待新版提示，继续审旧片保存／提交意见后查看新版；不把登记待办视为返修完成。

仅验证审核 UI 时使用独立字节副本，不运行渲染。输出目录必须不存在；副本移除交付及整片批准／交付决定，模拟反馈和确认只留在副本：

```bash
.venv/bin/python -B tests/review_ui_fixture.py --source-version /absolute/read-only-version --root work/review-ui-check
.venv/bin/python scripts/serve_workflow_review.py work/review-ui-check/AfterForge --port 8796
```

Agent 场景先准备独立状态，再由实际 Agent 根据原话选择请求；每个 case 均需 observe/act，不能仅运行 verify 冒充一次 Agent 交互：

```bash
.venv/bin/python -B tests/work_model_agent_scenarios.py prepare --root work/agent-check
.venv/bin/python -B tests/work_model_agent_scenarios.py observe --root work/agent-check --case cold-continue
.venv/bin/python -B tests/work_model_agent_scenarios.py act --root work/agent-check --case cold-continue --action preview --request-file /tmp/agent-request.json
.venv/bin/python -B tests/work_model_agent_scenarios.py verify --root work/agent-check
```

## 边界与后续

- 2026-10-18 原记录的两项衔接问题已在第一轮实现：明确返修原子登记新 Demo 委托，正常 CLI preview／缓存／resume 返回本次可用审核入口。保存留言与普通提交不委托制作；正式批准、交付授权及 FCP 边界未变。第二轮短查询、局部 Cue、批量候选与入口去重尚未施工，须第一轮独立验收通过后推进。
- D0002 实际导入验收与协议 3 往返基线均已完成并登记。后续普通交付沿用该协议基线；交付/FCPXML 语义变化时重验。仅支持上述有机制依据的有限规范化，未知样式差异仍须查证，不能自动泛化为任意字段忽略。
- 当前交付仍要求单 Project sequence；多 Project 输入明确报出歧义，不扩展多 Project 交付。
- 当前正常工作区为 `/Users/xiaobaimac/Developer/fcpxml-animation-pipeline`，当前授权第一轮在同一 checkout 的 `codex/review-loop-round1-20261018` 开发，评审基线为 `c1199f17bcf7cef49bd40c3ed7d5360c6a0956bf`；交父级独立验收，不推送或合并 main。上一轮实现与正式交付边界保护已包含在 `main`（本次封箱前基线 `d58887a`）；已核验 `codex/rework-lifecycle`、`codex/rework-lifecycle-smoke`、`codex/workflow-stage-contract` 全部提交均在 `main` 中，并删除仍存在的本地分支及对应 GitHub 远端引用。失效的 `/private/tmp/fcpxml-animation-pipeline-stage-contract` worktree 登记已清理，仅保留正常工作区。
- 历史开发与迁移记录：此前在 `1ac7` 工作树开展 smoke 开发，以保护性提交 `86b93c5` 保存 Demo UX 与编码改动；后续实现经 `2151f7e` 收口，交付边界保护经 `d58887a` 登记。真实迁移和清理仅按当轮固定清单及追加确认执行；当轮未改 user-inbox 或 FCP Library，未执行 Git 历史操作、安装或部署。上述实际验收与迁移证据继续保留。
- 动态拼接资源仍须声明依赖。没有引入后台 Agent、自动跨版本继承、数据库、云分析或转写。正式媒体的硬链接唯一性由交付后端维护。
