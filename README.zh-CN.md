# RPG-ZeroRepo

<p>
  <a href="README.md">English</a> |
  <a href="README.zh-CN.md">简体中文</a>
</p>

**RPG-ZeroRepo 使用 Repository Planning Graph（RPG，仓库规划图）为长周期 AI 编码智能体提供控制层。**

[![RPG-ZeroRepo: arXiv:2509.16198](https://img.shields.io/badge/Paper%201-arXiv%3A2509.16198-b31a1b)](https://arxiv.org/abs/2509.16198)
[![RPG-Encoder: arXiv:2602.02084](https://img.shields.io/badge/Paper%202-arXiv%3A2602.02084-b31a1b)](https://arxiv.org/abs/2602.02084)
[![ICLR 2026](https://img.shields.io/badge/ICLR-2026-blue.svg)](https://arxiv.org/abs/2509.16198)
[![ICML 2026](https://img.shields.io/badge/ICML-2026-blue.svg)](https://arxiv.org/abs/2602.02084)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

🔥 **[CoderMind](CoderMind/) 现已支持 Claude Code、GitHub Copilot、Codex App/CLI/IDE、Pi 和 oh-my-pi（OMP）。**

🧩 **[Domain Graph 0.2.0](https://github.com/KiwataHoko/RPG-ZeroRepo/releases/tag/domain-graph-v0.2.0) 新增可溯源内容转换与 Markdown/HTML 渲染。**

编码智能体执行长周期仓库任务时容易丢失仓库级上下文：需求发生漂移、架构决策消失、编辑遗漏隐藏依赖。

CoderMind 为智能体提供**持久化 RPG 工作区**。智能体通过共享图完成仓库规划、生成、理解和更新，不必只依赖临时对话历史与文件搜索。

本仓库还包含研究代码：

- **[ZeroRepo](#zerorepo需求--rpg--仓库)**：正向流水线（需求 → RPG → 仓库）。
- **[RPG-Encoder](#rpg-encoder仓库--rpg)**：反向流水线（仓库 → RPG）。
- **[RepoCraft](#repocraft-基准测试)**：仓库级代码生成评测。

---

## 文档

- [Domain Graph 指南](domain_graph/README.md) — 安装、公共 API、Schema、查询和适配器
- [Domain Graph 兼容性策略](domain_graph/COMPATIBILITY.md) — v1 格式契约、黄金样本、迁移和适配器验收
- [Domain Graph 更新日志](domain_graph/CHANGELOG.md)
- [CoderMind 完整指南](CoderMind/README.zh-CN.md) — 安装、Agent Skills、命令和 MCP 工具
- [宿主驱动的智能体](CoderMind/docs/host-driven-agents.md) — Codex/Pi/OMP 的无嵌套智能体执行方式
- [CoderMind 命令参考](CoderMind/docs/commands.md)
- [CoderMind CLI 参考](CoderMind/docs/cli-reference.md)
- [CoderMind 配置](CoderMind/docs/configuration.md)
- [ZeroRepo 流水线](docs/zerorepo-pipeline.md)
- [RPG-Encoder 模块](zerorepo/rpg_encoder/README.md)
- [RepoCraft 基准测试](repocraft/README.md)

---

## CoderMind

CoderMind 把 Repository Planning Graph 变成长周期 AI 编码智能体的控制层。RPG 将需求、功能、架构、文件、代码实体和依赖关系连接起来，形成可以持续查询、更新和复用的仓库级规划状态。

### CoderMind 能解决什么问题？

| 任务 | 输入 | CoderMind 工作流 | 产出 |
| --- | --- | --- | --- |
| **构建新仓库** | 自然语言需求 | 创建 RPG，细化架构与任务，然后生成代码 | 面向多文件生成的持久化计划 |
| **理解已有仓库** | 现有代码库 | 把仓库编码为 RPG，再通过 MCP 搜索和浏览 | 可查询的结构化仓库地图 |
| **更新已有仓库** | 代码库与变更请求 | 定位受影响节点，规划编辑，同步更新代码与图 | 考虑跨文件依赖的图感知编辑 |

### 支持的编码智能体

| 智能体 | 集成方式 | 状态 |
| --- | --- | --- |
| Claude Code | Commands 与 MCP | ✅ 已验证 |
| GitHub Copilot | 自定义 agents 与 MCP | ✅ 已验证 |
| Codex App / CLI / IDE | Agent Skills、MCP、宿主驱动执行 | 🧪 实验性 |
| Pi | Agent Skills、项目级 MCP bridge、宿主驱动执行 | 🧪 实验性 |
| oh-my-pi（OMP） | 原生 skills、MCP、宿主驱动执行 | 🧪 实验性 |

### 安装

要求 Python 3.12+、[uv](https://docs.astral.sh/uv/) 和 Git。

```bash
uv tool install cmind-cli \
  --from "git+https://github.com/microsoft/RPG-ZeroRepo.git#subdirectory=CoderMind"
cmind check
```

### 在已有仓库中使用 Codex

```bash
cd your-existing-repo
cmind init . --ai codex
```

然后在 Codex App、CLI 或 IDE 中打开该仓库并调用生成的 skill：

```text
$cmind-encode
$cmind-rpg-edit Add rate limiting to all API endpoints
```

其他宿主使用对应参数：

```bash
cmind init . --ai claude
cmind init . --ai copilot
cmind init . --ai pi
cmind init . --ai omp
```

### 宿主驱动执行

Codex、Pi 和 OMP 集成不会让 CoderMind 在内部启动第二个 `codex exec`、`pi -p` 或 `omp -p`。当前智能体会话负责全部模型推理，CoderMind 负责：

- 提供 Agent Skills 与工作流；
- 通过 `cmind-mcp` 提供 RPG 查询工具；
- 执行确定性的 Python 流水线阶段；
- 在旧流水线需要模型响应时，把请求交回当前会话。

生成的宿主配置如下：

| 宿主 | Skills | RPG 工具 |
| --- | --- | --- |
| Codex | `.agents/skills/cmind-*/SKILL.md` | `.codex/config.toml` |
| Pi | `.agents/skills/cmind-*/SKILL.md` | `.pi/extensions/cmind-mcp.ts` |
| OMP | `.omp/skills/cmind-*/SKILL.md` | `.omp/mcp.json` |

旧流水线通过以下协议与当前会话协作：

```text
cmind host start <script> ...
cmind host next <run-id>
cmind host reply <run-id> <request-id>
```

详细协议见 [CoderMind 宿主驱动智能体设计](CoderMind/docs/host-driven-agents.md)。

### 生成新仓库

```bash
cmind init my-project --ai codex
cd my-project
```

在编码智能体中依次运行功能构建、规划与代码生成工作流。不同宿主会把同一套 CoderMind 工作流暴露为 slash commands、自定义 agent 或 Agent Skills。

### RPG 工具

CoderMind 通过 MCP 暴露以下仓库图工具：

- `search_rpg`：按语义搜索 RPG 节点；
- `explore_rpg`：沿关系探索图；
- `get_node_detail`：获取节点详情；
- `list_rpg_tree`：列出 RPG 层级结构。

CoderMind 安装的 post-commit hook 可以在提交后增量更新 RPG，使图与代码变更保持一致。

### CoderMind 实际效果

下图由本仓库运行 `/cmind.encode` 后生成：

![本仓库的 RPG 可视化](docs/cmind_visualized_graph.png)

完整用法见 [CoderMind 中文指南](CoderMind/README.zh-CN.md)。

---

## Domain Graph 核心库

[`domain_graph`](domain_graph/) 是从 CoderMind 中抽取的独立图基础库。它提供
领域无关的节点和边、由 Schema 定义的词汇与层级语义、图遍历、校验以及带
版本号的 JSON 格式，不依赖 CoderMind 或代码领域专用枚举。

直接从 GitHub 安装当前版本：

```bash
python -m pip install \
  https://github.com/KiwataHoko/RPG-ZeroRepo/releases/download/domain-graph-v0.2.0/domain_graph-0.2.0-py3-none-any.whl
```

```python
from domain_graph import DomainGraph, DomainSchema, RelationSpec

schema = DomainSchema(
    "research",
    entity_types=("claim", "evidence"),
    relations=(RelationSpec("supports"),),
)
graph = DomainGraph("paper", schema, strict_schema=True)
graph.add_node("claim-1", "claim")
graph.add_node("evidence-1", "evidence")
graph.add_edge("evidence-1", "claim-1", "supports")
```

`ContentDomainAdapter` 保留文档、章节、内容块和引用到来源研究图节点的联系。
`ResearchToContentMapper` 可生成
带论点覆盖报告的溯源大纲，无运行时依赖的渲染器可进一步输出 Markdown 或
经过安全转义的 HTML。

在 Codex 中，中性的 skills 组成完整的研究发布链路：

```text
$research-build → ResearchDomainGraph → $research-content
                → ContentDomainGraph → $publish-content → Markdown / HTML
```

当输入仍是研究问题或假设时，从 `$research-build` 开始。它会先记录论点、
支持或反驳证据及来源溯源，再进入内容编排阶段。

0.2.0 支持 Python 3.10 及以上版本，无运行时依赖，并可读取 0.1.x 版本线
产生的 v1 JSON 图。详见[包使用指南](domain_graph/README.md)、
[兼容性策略](domain_graph/COMPATIBILITY.md)和
[0.2.0 Release](https://github.com/KiwataHoko/RPG-ZeroRepo/releases/tag/domain-graph-v0.2.0)。

---

## 独立研究代码

ZeroRepo 与 RPG-Encoder 是构建 RPG 的独立研究流水线：

```text
需求 → RPG → 仓库      # ZeroRepo
仓库 → RPG             # RPG-Encoder
```

这些组件无需编码智能体 CLI 即可运行，适合论文复现和基准测试。

### ZeroRepo：需求 → RPG → 仓库

> *RPG: A Repository Planning Graph for Unified and Scalable Codebase Generation* — [arXiv:2509.16198](https://arxiv.org/abs/2509.16198)，ICLR 2026

ZeroRepo 是正向生成框架。它把自然语言项目需求转换为 RPG，将图细化为架构和实现任务，再按照依赖顺序生成完整仓库。

流水线包含三个阶段：

1. **功能规划**：把用户需求分解为结构化功能树和组件。
2. **架构设计**：把功能映射到模块、文件、类、接口和数据流，构建完整 RPG。
3. **图引导代码生成**：按照依赖顺序生成相互关联的文件，以 RPG 作为持久化执行状态。

![ZeroRepo 三阶段流水线](docs/pipeline.png)

```bash
python main.py \
  --config configs/zerorepo_config.yaml \
  --checkpoint ../my_project/checkpoints \
  --repo ../my_project/workspace \
  --phase all \
  --resume
```

阶段说明、检查点文件和配置见 [ZeroRepo 流水线文档](docs/zerorepo-pipeline.md)。

### RPG-Encoder：仓库 → RPG

> *Closing the Loop: Universal Repository Representation with RPG-Encoder* — [arXiv:2602.02084](https://arxiv.org/abs/2602.02084)，ICML 2026

RPG-Encoder 把已有代码库映射回 Repository Planning Graph。生成的 RPG 同时表示语义意图和结构依赖，可以用于功能与文件之间的双向导航、提交级增量更新和结构感知维护。

| 机制 | 模块 | 说明 |
| --- | --- | --- |
| **Encoding** | `rpg_parsing/` | 通过语义提升、结构重组和产物定位从代码库提取 RPG |
| **Evolution** | `rpg_parsing/rpg_evolution.py` | 解析提交级 diff，增量维护 RPG |
| **Operation** | `rpg_agent/` | 提供 SearchNode、FetchNode、ExploreRPG 等导航接口 |

```bash
python parse_rpg.py parse \
  --repo-dir /path/to/repo \
  --repo-name myrepo \
  --save-dir ./output

python parse_rpg.py update \
  --repo-dir /path/to/updated/repo \
  --last-repo-dir /path/to/old/repo \
  --load-path ./output/rpg_encoder.json \
  --save-dir ./output
```

详细说明见 [RPG-Encoder README](zerorepo/rpg_encoder/README.md)。

### RepoCraft 基准测试

RepoCraft 用于评测仓库级代码生成，包含来自 6 个真实 Python 项目的 1,052 个任务：scikit-learn、pandas、sympy、statsmodels、requests 和 django。

| 指标 | 说明 |
| --- | --- |
| **Coverage** | 覆盖参考功能类别的比例 |
| **Accuracy** | 单元测试通过率和语义检查 Voting Rate |
| **Code Statistics** | 文件数、代码行数和 Token 数 |

完整评测流程见 [RepoCraft README](repocraft/README.md)。

---

## 论文

- **RPG / ZeroRepo：** Luo 等，*RPG: A Repository Planning Graph for Unified and Scalable Codebase Generation*，[arXiv:2509.16198](https://arxiv.org/abs/2509.16198)，ICLR 2026。
- **RPG-Encoder：** Luo 等，*Closing the Loop: Universal Repository Representation with RPG-Encoder*，[arXiv:2602.02084](https://arxiv.org/abs/2602.02084)，ICML 2026。

### 引用

```bibtex
@article{luo2025rpg,
  title={RPG: A Repository Planning Graph for Unified and Scalable Codebase Generation},
  author={Luo, Jane and Zhang, Xin and Liu, Steven and Wu, Jie and Liu, Jianfeng and Huang, Yiming and Huang, Yangyu and Yin, Chengyu and Xin, Ying and Zhan, Yuefeng and others},
  journal={arXiv preprint arXiv:2509.16198},
  year={2025}
}

@article{luo2026closing,
  title={Closing the Loop: Universal Repository Representation with RPG-Encoder},
  author={Luo, Jane and Yin, Chengyu and Zhang, Xin and Li, Qingtao and Liu, Steven and Huang, Yiming and Wu, Jie and Liu, Hao and Huang, Yangyu and Kang, Yu and others},
  journal={arXiv preprint arXiv:2602.02084},
  year={2026}
}
```

## 致谢

感谢以下项目提供的启发与基础：

- [Trae Agent](https://github.com/bytedance/trae-agent)
- [GitHub Spec-Kit](https://github.com/github/spec-kit)

## 许可证

MIT License，详情见 [LICENSE](LICENSE)。
