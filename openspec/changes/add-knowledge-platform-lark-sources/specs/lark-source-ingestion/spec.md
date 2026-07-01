## ADDED Requirements

### Requirement: Lark 资料由外部 Codex skill 产出
系统必须把飞书/Lark 项目资料视为由外部 Codex skill 产出的资料文件；该 skill 使用 Lark CLI，LLM Wiki 应用本身不实现应用内 Lark 导入器。

#### Scenario: Skill 写入 Lark 项目资料
- **WHEN** Codex skill 为某个 LLM Wiki 项目导出飞书/Lark 项目资料
- **THEN** 导出文件存储在项目本地 `raw/sources/lark/` 路径下
- **AND** LLM Wiki 应用将这些文件视为普通项目资料

#### Scenario: 用户查看托管连接器选项
- **WHEN** 用户在 LLM Wiki 应用中打开资料控制区域
- **THEN** 系统在本变更中不展示钉钉、飞连、直接飞书 OpenAPI 同步、定时同步、通用连接器配置或应用内 Lark CLI 导入器

### Requirement: 应用不执行 Lark CLI
系统必须不在 LLM Wiki 应用中解析、配置或执行 Lark CLI。

#### Scenario: 应用所在机器没有 Lark CLI
- **WHEN** LLM Wiki 运行在未安装 Lark CLI 的机器上
- **THEN** 正常目录、项目、资料和知识提取功能仍然可用
- **AND** 应用不显示 Lark CLI 安装失败，除非未来 skill 或外部工作流在应用外部报告该问题

### Requirement: Skill 产出的 Lark 资料具备可追溯来源
系统必须定义一个项目本地来源追踪约定，用于描述 skill 产出的 Lark 资料文件。

#### Scenario: Skill 导出 Lark 文档或消息集合
- **WHEN** Codex skill 在 `raw/sources/lark/` 下写入 Lark 来源文件
- **THEN** skill 同时写入项目本地来源记录
- **AND** 每条记录包含 channel、原始 Lark 标识符或 URL（如可用）、导出/导入时间、生成的项目相对文件路径和内容 hash

#### Scenario: Skill 产出的文件名冲突
- **WHEN** skill 产出的 Lark 资料将要写入一个已经存在的路径
- **THEN** 产出的资料使用唯一且确定性的路径
- **AND** 来源元数据指向实际写入文件

### Requirement: Skill 产出的 Lark 资料进入现有知识提取管线
系统必须依赖现有资料监控器、资料生命周期逻辑和知识提取队列处理 skill 产出的 Lark 资料文件。

#### Scenario: Skill 在可用 LLM 配置下写入文件
- **WHEN** skill 产出的 Lark 资料文件出现在活动项目已监控的 `raw/sources/lark/` 目录树下
- **THEN** 系统使用现有资料监控器行为把可知识提取文件加入队列
- **AND** 文件夹上下文标识这些文件来自 Lark 项目资料

#### Scenario: Skill 在没有可用 LLM 配置时写入文件
- **WHEN** skill 产出的 Lark 资料文件出现，但项目没有可用 LLM 配置
- **THEN** 系统保留原始资料文件和来源元数据
- **AND** 系统不得错误报告 wiki 知识提取已开始

### Requirement: 无效 skill 输出不破坏现有项目
系统必须在 skill 产出的 Lark 资料输出无效或不完整时，避免破坏现有项目资料、wiki 页面或元数据。

#### Scenario: Skill 输出不完整
- **WHEN** 来源记录引用了缺失文件，或 skill 产出的文件不可知识提取
- **THEN** 系统不为缺失或无效资料文件创建知识提取队列项
- **AND** 除现有资料监控诊断行为可能产生的记录外，已有项目文件保持不变
