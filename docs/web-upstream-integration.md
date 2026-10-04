# 网页与MathModelAgent的具体融合

读取基线为 vendor/MathModelAgent 固定提交 `487f350`。以下来自实际源文件；网页交互、接口适配和执行后端分别实施，文件存在或界面相似不计作调用成功。

| 能力 | 已读取的上游文件 | 适配与验收 |
| --- | --- | --- |
| 项目入口 | `frontend/src/router/index.ts`（首页、chat、task路由） | 办公室工作台接六种工作方向；沿用项目/任务导航思想，不伪造已有项目或成员数据 |
| 题面与材料 | `frontend/src/components/UserStepper.vue`、backend modeling路由 | 原题/资料/空结果样表分类，完整性与读取限制分别展示；仅选择文件不标已解析 |
| 比赛选择 | `frontend/src/apis/submitModelingApi.ts`、`backend/app/schemas/enums.py` | 修正提交时硬编码CHINA；真实选择国赛、美赛、东北联赛与其他当届赛制，模板来源与年份待核项保留 |
| 阶段编排 | `backend/app/core/workflow.py`、`backend/app/core/flows.py` | 四Agent编排接本skill的6阶段合同；显式读取所需入口/引用，逐问科学输出核验通过后才能写结论 |
| 过程与停止 | `frontend/src/stores/task.ts`、task WebSocket与messages/cancel接口 | 实际后端事件驱动状态；取消、失败、接续及输出版本可核验；不用动画/工具调用次数代替完成 |
| 模型配置 | `frontend/src/pages/chat/components/ApiDialog.vue`、save-api-config与key store | 不能原样迁移浏览器key持久化或全局settings修改到多人协会网站；服务端/用户/任务隔离，保持套餐客户端授权范围 |
| 代码/论文/图件 | `frontend/src/pages/task/index.vue`、`frontend/src/components/AgentEditor/WriterEditor.vue`、`skills/mathmodel-figure-templates/references/figure-catalog.md` | 复用编辑/预览与模板规划；目录实际为11类，当前本skill5类真实CSV入口先接。Python、Jupyter、统计量及PDF编译要独立执行记录 |
| 成果下载 | `frontend/src/pages/task/components/FileSheet.vue`、files/download接口 | 将写死localhost的下载地址改为授权服务地址；生成与下载同版文件，原题每问ID、来源与真实执行共同验收 |

可在首版实际实现方向/模板选择、材料台账、配置导出和已有合成图件查看；AI求解、OCR、图件重算、PDF编译与支撑包完成在服务接通前保持待执行。办公室名称与网站风格只用于工作台，不自动注入匿名论文。
