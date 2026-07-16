import {
  ArrowRight,
  Bot,
  Boxes,
  BrainCircuit,
  Database,
  FileText,
  GitBranch,
  KeyRound,
  Layers3,
  Network,
  RefreshCcw,
  Search,
  ShieldCheck,
  Workflow,
} from "lucide-react"

const layers = [
  {
    icon: FileText,
    title: "数据源接入层",
    subtitle: "先只接飞书 Lark CLI",
    body: "把飞书 Wiki、云文档、表格、附件按项目导出，保留来源、时间、负责人和路径。",
  },
  {
    icon: Database,
    title: "原始资料层",
    subtitle: "raw sources",
    body: "所有导出的资料先原样保存，不直接覆盖。后续任何 wiki 页面都能追溯到原始来源。",
  },
  {
    icon: BrainCircuit,
    title: "知识加工层",
    subtitle: "解析、清洗、LLM 结构化",
    body: "把长文档切成可处理片段，提炼成 wiki 页面、摘要、FAQ、关键规则和项目术语。",
  },
  {
    icon: Network,
    title: "知识组织层",
    subtitle: "目录、链接、图谱",
    body: "用项目分类、页面类型、wikilink、标签和关系图，把散文档变成可导航的知识网络。",
  },
  {
    icon: Search,
    title: "检索服务层",
    subtitle: "搜索、引用、API",
    body: "对外提供搜索、读取页面、引用原文、问答上下文组装等能力，上层应用不用关心底层文档细节。",
  },
  {
    icon: Bot,
    title: "应用消费层",
    subtitle: "toC 应用和 Agent",
    body: "项目问答、标注助手、审核助手、SOP 查询、复盘报告都从同一个知识库底座取知识。",
  },
]

const steps = [
  {
    title: "1. 建项目",
    body: "先按业务创建项目知识库，例如 Rubric 标注、爬虫项目、语音采标、视频采标。",
  },
  {
    title: "2. 收资料",
    body: "用 Lark CLI 从飞书导出项目资料。黑客松阶段不做复杂导入器，先把飞书链路跑通。",
  },
  {
    title: "3. 变知识",
    body: "系统把原始文档解析成 wiki 页面：每页有标题、摘要、正文、来源、标签和关联页面。",
  },
  {
    title: "4. 建索引",
    body: "同时生成关键词索引、向量索引和关系图，支持精确查找、语义查找和路径探索。",
  },
  {
    title: "5. 给应用用",
    body: "上层应用通过统一 API 拿知识，不需要自己读飞书文档，也不需要重复整理同一套资料。",
  },
  {
    title: "6. 自生长",
    body: "用户提问、Agent 使用、审核反馈和项目变更会回流成修订任务，知识库持续更新。",
  },
]

const knowledgeFlow = [
  "飞书导出",
  "原始资料",
  "解析清洗",
  "LLM 生成页面",
  "目录和图谱",
  "搜索索引",
  "知识库 API",
  "业务应用",
]

const loopFlow = [
  "用户提问",
  "检索相关知识",
  "组装上下文",
  "Agent 作答",
  "标注或审核",
  "反馈问题",
  "修订知识库",
]

const roles = [
  {
    title: "底层 AI 知识库",
    body: "负责项目分类、资料接入、知识生成、索引检索、权限与 API。目标是做成通用平台，而不是只服务一个黑客松项目。",
  },
  {
    title: "上层云文档应用",
    body: "继续做云文档和面向用户的项目应用。它可以把底层知识库当作统一知识 API 来调用。",
  },
  {
    title: "黑客松项目：试点场景",
    body: "先选一个真实项目跑通闭环，比如 Rubric 标注知识库。试点证明流程可用，再扩展到更多项目分类。",
  },
]

const capabilities = [
  {
    icon: KeyRound,
    title: "按项目隔离",
    body: "每个项目知识库有自己的资料、索引、权限和更新记录，避免不同客户或项目互相污染。",
  },
  {
    icon: ShieldCheck,
    title: "按人授权",
    body: "系统管理员决定谁能看哪些项目。登录后只展示用户有权限的项目知识库。",
  },
  {
    icon: RefreshCcw,
    title: "可增量更新",
    body: "飞书内容变更后，只重跑受影响的资料和页面，不需要每次全量重建。",
  },
  {
    icon: GitBranch,
    title: "可追溯来源",
    body: "回答不是凭空生成，而是带着来源页面、原始文档和修订历史，方便质检和复核。",
  },
]

function SectionTitle({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string
  title: string
  description: string
}) {
  return (
    <div className="mx-auto max-w-3xl text-center">
      <p className="text-sm font-medium text-blue-700 dark:text-blue-300">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-semibold text-slate-950 dark:text-white md:text-4xl">
        {title}
      </h2>
      <p className="mt-4 text-base leading-7 text-slate-600 dark:text-slate-300">
        {description}
      </p>
    </div>
  )
}

function ArrowConnector() {
  return (
    <div className="hidden items-center justify-center text-slate-300 lg:flex" aria-hidden="true">
      <ArrowRight className="h-5 w-5" />
    </div>
  )
}

function FlowDiagram({
  title,
  description,
  nodes,
  loopText,
}: {
  title: string
  description: string
  nodes: string[]
  loopText?: string
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-950">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-slate-950 text-white dark:bg-white dark:text-slate-950">
          <Workflow className="h-5 w-5" />
        </div>
        <div>
          <h3 className="font-semibold text-slate-950 dark:text-white">{title}</h3>
          <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">{description}</p>
        </div>
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {nodes.map((node, index) => (
          <div className="flex items-stretch gap-3" key={node}>
            <div className="flex min-h-20 flex-1 flex-col justify-between rounded-md border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900">
              <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="mt-3 text-base font-semibold text-slate-950 dark:text-white">{node}</span>
            </div>
            {index < nodes.length - 1 && (
              <div className="hidden w-6 shrink-0 items-center justify-center text-slate-300 xl:flex" aria-hidden="true">
                <ArrowRight className="h-5 w-5" />
              </div>
            )}
          </div>
        ))}
      </div>
      {loopText && (
        <div className="mt-4 flex items-center gap-3 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm leading-6 text-emerald-900 dark:border-emerald-900/70 dark:bg-emerald-950/40 dark:text-emerald-100">
          <RefreshCcw className="h-5 w-5 shrink-0" />
          <span>{loopText}</span>
        </div>
      )}
    </div>
  )
}

export function LlmWikiArchitecturePage() {
  return (
    <main className="min-h-dvh bg-slate-50 text-slate-950 dark:bg-slate-950 dark:text-slate-50">
      <section className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
        <div className="mx-auto flex max-w-7xl flex-col gap-10 px-5 py-10 sm:px-8 lg:px-10 lg:py-14">
          <div className="grid gap-8 lg:grid-cols-[1fr_420px] lg:items-end">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-sm font-medium text-blue-800 dark:border-blue-900/70 dark:bg-blue-950/50 dark:text-blue-200">
                <Layers3 className="h-4 w-4" />
                LLM Wiki 架构说明
              </div>
              <h1 className="mt-6 max-w-4xl text-4xl font-semibold leading-tight text-slate-950 dark:text-white md:text-6xl">
                把散落的项目资料，变成能被人和 Agent 共同使用的知识底座
              </h1>
              <p className="mt-6 max-w-3xl text-lg leading-8 text-slate-600 dark:text-slate-300">
                LLM Wiki 不是一个普通文档仓库。它的底层负责接入资料、生成结构化知识、建立检索索引和开放 API；上层再基于这些能力做项目问答、标注助手、审核助手和云文档应用。
              </p>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-5 dark:border-slate-800 dark:bg-slate-900/70">
              <p className="text-sm font-medium text-slate-500 dark:text-slate-400">一句话</p>
              <p className="mt-3 text-2xl font-semibold leading-snug text-slate-950 dark:text-white">
                底层沉淀项目知识，上层消费项目知识。
              </p>
              <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
                黑客松只是第一个试点。真正要做的是一个通用平台：不同分类、不同项目、不同权限的人，都能在同一套知识底座上协作。
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
        <div className="mx-auto max-w-7xl px-5 py-12 sm:px-8 lg:px-10">
          <SectionTitle
            eyebrow="Architecture"
            title="从资料到应用，分成六层"
            description="每一层只做一件清楚的事：接入、保存、加工、组织、服务、消费。这样后面要换数据源或加新应用，不需要推倒重来。"
          />
          <div className="mt-10 grid gap-3 lg:grid-cols-[1fr_28px_1fr_28px_1fr] xl:grid-cols-[1fr_28px_1fr_28px_1fr_28px_1fr_28px_1fr_28px_1fr]">
            {layers.map((layer, index) => {
              const Icon = layer.icon
              return (
                <div className="contents" key={layer.title}>
                  <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                    <div className="flex h-10 w-10 items-center justify-center rounded-md bg-slate-950 text-white dark:bg-white dark:text-slate-950">
                      <Icon className="h-5 w-5" />
                    </div>
                    <h3 className="mt-5 text-lg font-semibold text-slate-950 dark:text-white">
                      {layer.title}
                    </h3>
                    <p className="mt-1 text-sm font-medium text-blue-700 dark:text-blue-300">
                      {layer.subtitle}
                    </p>
                    <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
                      {layer.body}
                    </p>
                  </article>
                  {index < layers.length - 1 && <ArrowConnector />}
                </div>
              )
            })}
          </div>
        </div>
      </section>

      <section className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
        <div className="mx-auto grid max-w-7xl gap-8 px-5 py-12 sm:px-8 lg:grid-cols-[380px_1fr] lg:px-10">
          <div>
            <p className="text-sm font-medium text-emerald-700 dark:text-emerald-300">Flow</p>
            <h2 className="mt-3 text-3xl font-semibold text-slate-950 dark:text-white">
              端到端流程图
            </h2>
            <p className="mt-4 text-base leading-7 text-slate-600 dark:text-slate-300">
              当前试点先把飞书作为唯一数据源。后续可以继续接本地文件、网页、数据库、工单系统，但核心流程不变。
            </p>
            <div className="mt-6 grid gap-3">
              {steps.map((step) => (
                <div
                  key={step.title}
                  className="rounded-md border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900"
                >
                  <p className="font-medium text-slate-950 dark:text-white">{step.title}</p>
                  <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                    {step.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
          <div className="min-w-0 rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900">
            <FlowDiagram
              title="知识生产链路"
              description="从飞书导出的资料进入系统，先保存原文，再被解析成结构化 wiki，最后变成可搜索、可引用、可调用的服务。"
              nodes={knowledgeFlow}
            />
            <div className="mt-5">
              <FlowDiagram
                title="自生长闭环"
                description="知识库不是一次性产物。真实使用中暴露的问题，会回流到知识修订和索引更新。"
                nodes={loopFlow}
                loopText="反馈会回到知识加工层：补页面、改规则、补来源、重新索引。"
              />
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950">
        <div className="mx-auto max-w-7xl px-5 py-12 sm:px-8 lg:px-10">
          <SectionTitle
            eyebrow="Pilot"
            title="黑客松里怎么落地"
            description="这不是只给一个黑客松临时定制的小工具。黑客松项目只是第一个真实场景，用它验证通用平台的底层能力。"
          />
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {roles.map((role) => (
              <article
                key={role.title}
                className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900"
              >
                <h3 className="text-lg font-semibold text-slate-950 dark:text-white">{role.title}</h3>
                <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
                  {role.body}
                </p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-white dark:bg-slate-950">
        <div className="mx-auto max-w-7xl px-5 py-12 sm:px-8 lg:px-10">
          <div className="grid gap-8 lg:grid-cols-[360px_1fr]">
            <div>
              <p className="text-sm font-medium text-amber-700 dark:text-amber-300">Platform</p>
              <h2 className="mt-3 text-3xl font-semibold text-slate-950 dark:text-white">
                通用平台必须具备的能力
              </h2>
              <p className="mt-4 text-base leading-7 text-slate-600 dark:text-slate-300">
                首页可以选择知识库分类，分类下面再进入具体项目。项目之间隔离，人员按权限访问，API 面向上层应用复用。
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {capabilities.map((item) => {
                const Icon = item.icon
                return (
                  <article
                    key={item.title}
                    className="rounded-lg border border-slate-200 bg-slate-50 p-5 dark:border-slate-800 dark:bg-slate-900"
                  >
                    <div className="flex items-start gap-4">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-white text-slate-950 shadow-sm dark:bg-slate-800 dark:text-white">
                        <Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="font-semibold text-slate-950 dark:text-white">{item.title}</h3>
                        <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                          {item.body}
                        </p>
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          </div>

          <div className="mt-10 rounded-lg border border-slate-200 bg-slate-950 p-6 text-white dark:border-slate-800">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="flex items-center gap-2 text-sm font-medium text-slate-300">
                  <Workflow className="h-4 w-4" />
                  最终形态
                </div>
                <p className="mt-3 max-w-4xl text-xl font-semibold leading-relaxed">
                  底层 LLM Wiki 负责让项目知识持续变干净、可检索、可引用；上层业务应用负责把这些知识放到具体工作流里，让标注、审核、交付和复盘更快。
                </p>
              </div>
              <div className="flex items-center gap-3 rounded-md border border-white/15 bg-white/10 px-4 py-3 text-sm text-slate-200">
                <Boxes className="h-5 w-5" />
                一套底座，多类项目，多种应用
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  )
}
