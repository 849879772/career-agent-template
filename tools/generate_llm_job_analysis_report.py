"""Generate a detailed, model-free analysis of LLM-related campus jobs."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import reporter  # noqa: E402
from tools.generate_job_category_report import (  # noqa: E402
    contains_term,
    score_distribution,
    skill_counts,
    top_values,
)


DIRECTIONS = [
    {
        "id": "agent-application",
        "name": "智能体、RAG与应用开发",
        "short": "Agent与应用",
        "title_terms": ["agent", "智能体", "rag", "ai应用", "大模型应用", "copilot", "ai知识工程", "大模型知识工程"],
        "terms": ["工具调用", "工作流", "知识库", "向量检索", "语义检索", "mcp", "function calling", "业务落地"],
        "positioning": "这是岗位数量最多、校招生最容易通过项目证明能力的方向。工作不是简单套用模型接口，而是把检索、规划、记忆、工具调用、权限、后端服务和评测组成稳定产品。内部可再分为智能体算法与框架、RAG与知识工程、大模型应用工程三个子方向。",
        "responsibilities": ["设计 Agent 工作流、任务规划、记忆与工具选择机制", "建设 RAG 链路，包括切分、索引、召回、重排和答案生成", "把模型能力接入业务系统，完成接口、权限、数据和状态管理", "建立效果、延迟、成本、稳定性和失败恢复评测", "持续分析幻觉、召回失败和复杂任务执行中断"],
        "requirements": ["Python 是主语言，应用工程岗也常接受 Java、Go 或 TypeScript", "理解 Transformer、上下文窗口、Embedding 和模型推理基本机制", "熟悉至少一种 Agent 或 RAG 框架，但更重要的是能解释其内部流程", "具备后端接口、数据库、缓存、消息队列或服务部署经验", "能够设计离线评测集，并对正确率、召回率、延迟和成本做权衡"],
        "projects": ["企业知识库问答：必须展示召回、重排、引用、拒答和评测，不只展示聊天界面", "多工具 Agent：包含任务拆解、工具路由、状态机、失败重试和执行日志", "面向真实业务的 AI 助手：说明权限、数据安全、监控和用户反馈闭环", "MCP 或 Function Calling 项目：展示工具协议、参数校验和异常处理"],
        "interview": ["RAG 各阶段如何影响最终效果，怎样定位召回正确但回答错误", "Agent 如何规划长任务、保存状态、选择工具并从失败中恢复", "如何减少幻觉，以及什么时候应该拒答", "模型调用并发、流式响应、超时、缓存和成本控制", "项目中真正由你设计的部分，而不是框架默认能力"],
        "fit": "与你的 C++/软件开发、测试和智能体兴趣连接最直接。可优先准备 Python 后端、RAG 评测和 Agent 工程项目，再用 C++ 系统能力体现工程深度。",
        "warning": "大量岗位标题都叫 AI 应用工程师，但有的偏算法，有的本质是后端。判断依据是 JD 更强调模型效果、Agent/RAG，还是接口、数据库与业务交付。",
        "role_signals": [("Agent规划与编排", ["智能体", "agent", "任务规划", "工作流"]), ("RAG与知识检索", ["rag", "知识库", "向量检索", "检索增强"]), ("工具调用与系统集成", ["工具调用", "function calling", "mcp", "系统集成"]), ("业务应用与后端服务", ["应用开发", "业务落地", "后端", "接口开发"]), ("效果评测与迭代", ["效果评测", "评测体系", "幻觉", "持续优化"])],
        "req_signals": [("Python或后端语言", ["python", "java", "golang", "go语言"]), ("RAG/Agent实践", ["rag", "agent", "智能体"]), ("数据库与检索", ["数据库", "向量数据库", "elasticsearch", "检索"]), ("服务化与部署", ["微服务", "docker", "部署", "接口"]), ("评测与问题分析", ["评测", "准确率", "召回率", "问题分析"])],
        "matrix": [3, 5, 3, 3, "本科/硕士", "重点"],
    },
    {
        "id": "model-training",
        "name": "基础模型训练与后训练",
        "short": "训练与后训练",
        "title_terms": ["预训练", "后训练", "post-training", "微调", "模型训练", "基座模型", "模型优化", "大模型算法"],
        "terms": ["sft", "lora", "rlhf", "dpo", "对齐", "分布式训练", "预训练", "后训练"],
        "positioning": "这是最接近大模型核心算法的方向，覆盖数据配方、预训练、监督微调、偏好对齐、奖励模型、训练稳定性和能力评估。岗位数量不如应用方向多，但学历和研究门槛明显更高。",
        "responsibilities": ["构建预训练或后训练数据，并设计清洗、采样和配比策略", "开展 SFT、LoRA、DPO、RLHF 或持续预训练实验", "分析训练稳定性、损失曲线、能力退化和灾难性遗忘", "设计基准、消融实验和模型能力评估", "优化训练效率、显存、吞吐和分布式策略"],
        "requirements": ["扎实的机器学习、深度学习、概率统计和优化基础", "熟练使用 Python、PyTorch，并理解 Transformer 结构和训练过程", "了解数据并行、模型并行、流水线并行和混合精度训练", "具备论文阅读、复现、实验设计和结果分析能力", "核心研究岗位通常偏好硕士或博士，且看重论文或大规模训练经历"],
        "projects": ["完成一个小模型持续预训练或领域微调，记录数据配方和消融结果", "比较 LoRA、全参微调、DPO 等方法的效果、显存和训练成本", "搭建自动评测并分析能力提升与通用能力退化", "复现一篇后训练或对齐论文，并说明未复现部分的原因"],
        "interview": ["Transformer、注意力、位置编码、归一化和训练目标", "SFT、DPO、PPO/RLHF 的目标与优缺点", "训练不稳定、梯度爆炸、过拟合和能力退化如何定位", "数据质量、数量、配比和课程学习如何影响模型", "分布式训练的通信、显存和吞吐瓶颈"],
        "fit": "如果你的优势主要是工程开发而缺少论文、训练实验或硕士研究积累，这一方向应作为条件型选择。可以通过小模型训练与严谨实验补足，而不是只做 API 应用。",
        "warning": "岗位名称含“大模型算法”不一定真正训练基座模型。要检查是否明确出现预训练、后训练、对齐、训练集群和模型评测，否则可能仍是应用算法。",
        "role_signals": [("预训练与持续训练", ["预训练", "持续预训练", "基座模型"]), ("监督微调与参数高效训练", ["sft", "lora", "微调"]), ("偏好对齐与强化学习", ["rlhf", "dpo", "偏好对齐", "奖励模型"]), ("训练数据与配方", ["训练数据", "数据配比", "数据清洗"]), ("能力评估与消融", ["模型评估", "能力评测", "消融实验"])],
        "req_signals": [("PyTorch与深度学习", ["pytorch", "深度学习"]), ("Transformer基础", ["transformer", "注意力机制"]), ("数学与优化", ["概率统计", "线性代数", "优化理论"]), ("分布式训练", ["分布式训练", "deepspeed", "megatron"]), ("论文与研究经历", ["论文", "顶会", "研究经历"])],
        "matrix": [5, 3, 3, 5, "硕士优先", "条件型"],
    },
    {
        "id": "multimodal-world",
        "name": "多模态与世界模型",
        "short": "多模态",
        "title_terms": ["多模态", "世界模型", "视频生成", "图文", "视觉语言", "全模态", "生成模型"],
        "terms": ["vlm", "vision-language", "视频理解", "图像生成", "3d生成", "跨模态", "扩散模型"],
        "positioning": "该方向把文本与图像、视频、语音、3D 或传感器数据统一建模。岗位可能偏多模态理解、内容生成、世界模型或多模态数据工程，与计算机视觉和基础模型训练高度交叉。",
        "responsibilities": ["构建图文、视频、语音或 3D 多模态数据集", "训练和优化多模态理解、生成或统一表征模型", "研究模态对齐、融合、时序建模和跨模态检索", "建立多模态评测集并分析不同模态的失败模式", "推进模型推理优化和实际产品部署"],
        "requirements": ["同时理解 Transformer 与计算机视觉、语音或 3D 中至少一个领域", "熟练使用 Python、PyTorch 和多模态训练工具链", "理解对比学习、视觉编码器、扩散模型或视频时序建模", "具备大规模数据处理和模型评测能力", "研究岗普遍偏好硕博、论文或高质量复现经历"],
        "projects": ["视觉语言模型微调：展示数据构建、指令设计、评测与错误分析", "视频理解或生成：说明时序建模、计算成本和指标", "多模态检索：比较编码器、对齐损失和召回策略", "3D或世界模型项目：说明状态表示、预测目标和下游任务"],
        "interview": ["CLIP、视觉编码器和语言模型如何连接与对齐", "多模态数据噪声、配对质量和模态不平衡", "图像、视频生成指标与人工评测如何结合", "长视频、高清图像和多帧输入的算力与上下文问题", "多模态模型幻觉和细粒度感知不足如何改进"],
        "fit": "你的视觉、机器人和大模型兴趣与该方向高度相关。如果具备 OpenCV、目标检测或视觉项目，可进一步补 VLM 微调、多模态数据和统一评测。",
        "warning": "多模态岗位跨度最大。图像生成、视频理解、VLM、世界模型和多模态数据 Infra 的能力要求并不相同，应按标题和交付物继续细分。",
        "role_signals": [("图文理解与生成", ["图文", "视觉语言", "图像理解", "图像生成"]), ("视频理解与生成", ["视频理解", "视频生成", "长视频"]), ("跨模态对齐与融合", ["跨模态", "模态对齐", "多模态融合"]), ("世界模型与预测", ["世界模型", "状态预测", "环境建模"]), ("多模态数据与评测", ["多模态数据", "多模态评测", "数据集"])],
        "req_signals": [("Python与PyTorch", ["python", "pytorch"]), ("计算机视觉基础", ["计算机视觉", "图像处理"]), ("Transformer/VLM", ["transformer", "vlm", "视觉语言模型"]), ("生成模型", ["扩散模型", "生成模型", "diffusion"]), ("大规模数据处理", ["数据处理", "大规模数据", "数据工程"])],
        "matrix": [5, 3, 3, 5, "硕士优先", "次重点"],
    },
    {
        "id": "ai-infra",
        "name": "AI Infra与推理系统",
        "short": "AI Infra",
        "title_terms": ["ai infra", "推理平台", "推理加速", "训练平台", "算力", "serverless", "模型部署"],
        "terms": ["cuda", "tensorrt", "分布式训练", "推理引擎", "模型服务", "gpu", "吞吐", "显存"],
        "positioning": "该方向负责让模型训得动、跑得快、服务稳定。交付物包括训练平台、推理引擎、模型服务、GPU 调度、量化编译和性能工具，是大模型领域中最偏系统工程的一支。",
        "responsibilities": ["开发分布式训练、模型服务或推理平台", "优化算子、显存、批处理、并发、延迟和吞吐", "建设 GPU 资源调度、监控、故障恢复和弹性伸缩", "适配不同模型、硬件和量化方案", "建立性能基准并定位计算、通信和内存瓶颈"],
        "requirements": ["C++、Python、Linux、数据结构与系统基础", "理解 GPU 架构、CUDA、算子、内存层次和并行计算", "熟悉分布式系统、网络通信、容器和服务治理", "具备性能剖析、并发、内存和故障定位能力", "了解模型结构与推理过程，但不一定要求做模型算法研究"],
        "projects": ["实现或改造推理服务，量化比较吞吐、首 Token 延迟和显存", "使用 CUDA/TensorRT/ONNX Runtime 完成模型加速", "开发 GPU 调度、批处理或请求队列模块", "对分布式训练通信、显存和容错进行性能分析"],
        "interview": ["Transformer 推理的计算和 KV Cache 内存瓶颈", "动态批处理、并发请求和延迟吞吐权衡", "CUDA 内存、Kernel、算子融合和性能分析", "数据并行、张量并行、流水线并行的通信代价", "服务故障、资源不足和热点请求如何处理"],
        "fit": "这是与你 C++、Linux、软件开发背景最契合的大模型方向。若补充 CUDA、推理框架、网络并发和性能分析项目，可形成明显差异化。",
        "warning": "部分 AI Infra 岗位接近云平台或运维开发，另一些深入编译器和算子。应根据 CUDA、推理引擎、Kubernetes 或平台服务关键词判断层次。",
        "role_signals": [("推理服务与平台", ["推理服务", "推理平台", "模型服务"]), ("性能与显存优化", ["性能优化", "显存优化", "低延迟", "高吞吐"]), ("GPU与算子加速", ["cuda", "算子优化", "tensorrt", "推理加速"]), ("训练基础设施", ["训练平台", "分布式训练", "训练框架"]), ("资源调度与稳定性", ["资源调度", "故障恢复", "监控", "弹性伸缩"])],
        "req_signals": [("C++/Python/Linux", ["c++", "python", "linux"]), ("CUDA与GPU", ["cuda", "gpu", "并行计算"]), ("分布式系统", ["分布式系统", "分布式训练", "通信"]), ("容器与云平台", ["docker", "kubernetes", "k8s"]), ("性能分析能力", ["性能分析", "profiling", "性能优化"])],
        "matrix": [3, 5, 5, 2, "本科/硕士", "重点"],
    },
    {
        "id": "data-eval-safety",
        "name": "数据、评测、质量与安全",
        "short": "数据与评测",
        "title_terms": ["大模型评测", "模型评测", "对齐评测", "大模型安全", "安全大模型", "训练数据", "大模型数据", "benchmark"],
        "terms": ["数据构建", "数据治理", "模型评测", "红队", "幻觉", "安全对齐", "数据清洗", "高质量数据"],
        "positioning": "该方向连接模型研发与产品质量，负责训练数据、评测集、自动评估、安全测试和问题归因。它不是低技术含量的数据标注，而是建立可重复的模型质量体系。",
        "responsibilities": ["构建和治理训练、微调或评测数据集", "设计能力、安全、幻觉和业务效果评测体系", "开发自动评测、数据清洗、质量检测和分析工具", "分析模型失败样本并推动数据或训练策略改进", "开展红队、安全策略、偏见和鲁棒性测试"],
        "requirements": ["Python、数据处理、统计分析和实验设计能力", "理解大模型训练、推理和常见失败模式", "能够定义指标、构建基准并进行误差归因", "熟悉 SQL、数据管道或测试自动化更有优势", "安全岗还会关注攻击、越权、提示注入和内容风险"],
        "projects": ["构建领域评测集，定义评分规则并验证人工与自动评测一致性", "开发模型回归测试平台，覆盖正确性、安全、延迟和成本", "对幻觉、提示注入或工具误调用进行系统性红队测试", "设计数据清洗、去重、质量评分和难例挖掘流程"],
        "interview": ["怎样证明评测集有代表性且没有数据泄漏", "自动评测与人工评测不一致如何处理", "模型版本更新后怎样做回归和能力退化检测", "提示注入、越权工具调用和敏感内容如何测试", "失败样本怎样归因到数据、模型、检索或提示词"],
        "fit": "与你的软件测试和质量分析背景非常契合。若增加模型评测、RAG回归、安全测试和数据分析项目，可从传统测开自然转向大模型质量工程。",
        "warning": "要区分模型数据与评测工程、普通数据运营和人工质检。优先选择明确要求编程、评测体系、自动化和问题归因的岗位。",
        "role_signals": [("数据构建与治理", ["数据构建", "数据治理", "数据清洗", "数据质量"]), ("模型能力评测", ["模型评测", "能力评测", "benchmark"]), ("自动化回归测试", ["自动化评测", "回归测试", "测试平台"]), ("安全与红队", ["安全评测", "红队", "提示注入", "内容安全"]), ("失败分析与反馈闭环", ["错误分析", "问题归因", "反馈闭环", "难例"])],
        "req_signals": [("Python与数据处理", ["python", "数据处理"]), ("统计与实验设计", ["统计分析", "实验设计", "指标"]), ("大模型基础", ["大模型", "llm", "transformer"]), ("测试与自动化", ["自动化测试", "测试开发", "评测平台"]), ("安全知识", ["安全", "攻击", "提示注入"])],
        "matrix": [3, 4, 2, 5, "本科/硕士", "重点"],
    },
    {
        "id": "embodied-vla",
        "name": "具身智能、VLA与机器人基础模型",
        "short": "具身与VLA",
        "title_terms": ["具身", "vla", "视觉语言动作", "机器人基础模型", "具身交互", "动作大模型"],
        "terms": ["模仿学习", "强化学习", "动作生成", "策略学习", "世界模型", "机械臂", "仿真数据"],
        "positioning": "该方向把大模型、多模态感知与机器人动作连接起来，研究从视觉和语言指令到决策、轨迹和控制的端到端或分层系统。岗位数量较少，但与机器人、视觉、强化学习交叉程度最高。",
        "responsibilities": ["构建视觉、语言、状态和动作轨迹数据", "训练 VLA、策略模型、世界模型或任务规划模型", "开展模仿学习、强化学习和仿真到真实迁移", "把高层任务规划与运动规划、控制系统集成", "在机械臂或移动机器人上完成评测和闭环部署"],
        "requirements": ["Python、PyTorch、多模态模型和强化/模仿学习基础", "理解机器人运动学、控制、规划和 ROS 系统", "具备仿真平台、数据采集和真实机器人调试经验", "熟悉 Transformer、Diffusion Policy、VLM/VLA 等方法", "研究岗通常偏好硕博和机器人或多模态论文经历"],
        "projects": ["机械臂模仿学习：包含示教数据、策略训练、成功率和失败案例", "语言指令到动作：展示 VLM/VLA、任务规划与控制接口", "Isaac Sim/MuJoCo 仿真训练并进行 Sim2Real 验证", "世界模型或策略学习：说明状态、动作、奖励和预测目标"],
        "interview": ["行为克隆、离线强化学习和在线强化学习的差异", "VLA 如何表示动作、处理时序并泛化到新任务", "数据采集质量、长尾失败和任务成功率评测", "高层大模型与低层控制之间如何保证实时性和安全", "Sim2Real 的视觉、动力学和控制偏差如何处理"],
        "fit": "与你对具身智能、机械臂、视觉、VLA、强化学习和模仿学习的兴趣完全一致，但门槛也最高。建议至少准备一个可复现实验和一个真实或高质量仿真机器人项目。",
        "warning": "标题写“具身智能”不代表一定做 VLA，也可能是传统感知、规划或控制。必须检查是否明确包含大模型、多模态、策略学习或世界模型。",
        "role_signals": [("VLA与动作生成", ["vla", "视觉语言动作", "动作生成"]), ("模仿学习与策略学习", ["模仿学习", "行为克隆", "策略学习"]), ("强化学习", ["强化学习", "离线强化学习", "奖励模型"]), ("世界模型与任务规划", ["世界模型", "任务规划", "长程任务"]), ("机器人部署与评测", ["机械臂", "机器人", "实机", "成功率"])],
        "req_signals": [("Python/PyTorch", ["python", "pytorch"]), ("强化与模仿学习", ["强化学习", "模仿学习"]), ("机器人学与ROS", ["机器人学", "ros", "运动规划"]), ("多模态/VLM", ["多模态", "vlm", "视觉语言"]), ("仿真与实机经验", ["isaac sim", "mujoco", "仿真", "实机"])],
        "matrix": [5, 4, 3, 5, "硕士优先", "次重点"],
    },
    {
        "id": "nlp-language",
        "name": "语言智能与NLP融合",
        "short": "NLP与语言",
        "title_terms": ["nlp", "自然语言", "语言理解", "对话", "翻译", "文本生成", "语义搜索"],
        "terms": ["信息抽取", "知识图谱", "文本分类", "机器翻译", "问答系统", "语义理解"],
        "positioning": "传统 NLP 能力正在融入大模型岗位，主要保留在搜索、问答、知识工程、对话、翻译和文本理解等场景。岗位通常要求既理解经典 NLP 方法，也会使用和评测大语言模型。",
        "responsibilities": ["开发文本理解、生成、搜索、问答或信息抽取算法", "建设语料、标签体系、知识结构和语言评测集", "将传统检索、分类模型与大模型结合", "针对领域语言问题进行微调、提示设计和错误分析", "优化准确率、召回率、可解释性和线上效果"],
        "requirements": ["Python、机器学习、Transformer 和 NLP 基础", "熟悉文本分类、序列标注、检索、问答或知识图谱", "掌握数据处理、模型评估和误差分析", "应用岗需要 RAG、Embedding 和搜索系统经验", "研究岗仍偏好硕士、论文或语言模型训练经历"],
        "projects": ["领域信息抽取或文本分类，包含数据标注、模型比较和错误分析", "语义搜索或问答系统，比较关键词、向量和混合检索", "知识图谱与大模型结合，展示实体关系和问答效果", "对话或翻译项目，建立可复现的自动与人工评测"],
        "interview": ["分词、Embedding、注意力、Transformer 和语言模型目标", "分类、序列标注、检索和生成任务如何评估", "BM25、向量检索和重排怎样组合", "领域数据少、标签噪声和长文本怎样处理", "传统 NLP 模型与大模型方案如何选型"],
        "fit": "如果你更关注智能体、视觉或机器人，该方向可作为支撑能力而非主投方向。语义检索和信息抽取仍可直接服务于 RAG 与 Agent。",
        "warning": "纯传统 NLP 校招岗位数量下降，很多已并入大模型应用或搜索。应优先选择同时涉及 LLM、RAG、语义检索或知识工程的岗位。",
        "role_signals": [("文本理解与生成", ["文本理解", "文本生成", "自然语言处理"]), ("搜索与问答", ["语义搜索", "问答系统", "检索"]), ("信息抽取与知识工程", ["信息抽取", "知识图谱", "知识工程"]), ("对话与翻译", ["对话", "机器翻译", "翻译"]), ("语言数据与评测", ["语料", "语言评测", "文本数据"])],
        "req_signals": [("Python与机器学习", ["python", "机器学习"]), ("Transformer/NLP", ["transformer", "nlp", "自然语言处理"]), ("检索与Embedding", ["embedding", "向量检索", "bm25"]), ("数据与误差分析", ["数据处理", "误差分析", "模型评估"]), ("知识图谱", ["知识图谱", "实体", "关系抽取"])],
        "matrix": [4, 3, 2, 4, "本科/硕士", "补充方向"],
    },
]

STRONG_LLM_TERMS = [
    "大模型", "llm", "智能体", "agent", "rag", "多模态", "世界模型", "vlm",
    "vla", "视觉语言", "生成模型", "基座模型", "ai infra", "模型评测",
]

STRICT_TITLE_TERMS = [
    "大模型", "llm", "智能体", "agent", "rag", "多模态", "世界模型", "vlm",
    "vla", "视觉语言", "基座模型", "预训练", "后训练", "post-training", "ai infra",
    "推理平台", "模型评测", "具身智能", "具身模型", "动作大模型", "自然语言处理", "nlp",
]

JD_ONLY_TITLE_GATES = [
    "算法", "研究", "模型", "数据", "训练", "推理", "视觉", "感知", "语言", "生成",
    "搜索", "知识", "具身", "强化学习", "模仿学习", "ai",
]


def text_of(item: dict) -> tuple[str, str]:
    job = item["job"]
    return (job.get("title") or "").casefold(), (job.get("jd_raw") or "").casefold()


def is_llm_related(item: dict) -> bool:
    title, jd = text_of(item)
    if any(contains_term(title, term) for term in STRICT_TITLE_TERMS):
        return True
    jd_hits = sum(contains_term(jd, term) for term in STRONG_LLM_TERMS)
    has_ai_title = bool(re.search(r"(?<![a-z])ai(?![a-z])", title))
    has_related_role = any(contains_term(title, term) for term in JD_ONLY_TITLE_GATES)
    return (jd_hits >= 2 and has_related_role) or (has_ai_title and jd_hits >= 1)


def direction_for(item: dict) -> dict:
    title, jd = text_of(item)
    # Strong title signals are more reliable than generic words buried in JD.
    priority = ["ai-infra", "embodied-vla", "multimodal-world", "data-eval-safety", "model-training", "nlp-language"]
    by_id = {direction["id"]: direction for direction in DIRECTIONS}
    for direction_id in priority:
        direction = by_id[direction_id]
        if any(contains_term(title, term) for term in direction["title_terms"]):
            return direction

    best = by_id["agent-application"]
    best_score = 0
    for direction in DIRECTIONS:
        title_hits = sum(contains_term(title, term) for term in direction["title_terms"])
        jd_hits = sum(contains_term(jd, term) for term in direction["terms"])
        score = title_hits * 8 + min(jd_hits, 5)
        if score > best_score:
            best, best_score = direction, score
    return best


def metric_counts(items: list[dict], definitions: list[tuple[str, list[str]]]) -> list[tuple[str, int]]:
    values = []
    for label, terms in definitions:
        count = 0
        for item in items:
            title, jd = text_of(item)
            if any(contains_term(f"{title} {jd}", term) for term in terms):
                count += 1
        values.append((label, count))
    return sorted(values, key=lambda value: value[1], reverse=True)


def education_counts(items: list[dict]) -> dict:
    result = {"本科": 0, "硕士": 0, "博士": 0}
    for item in items:
        jd = item["job"].get("jd_raw") or ""
        if re.search(r"本科|学士", jd):
            result["本科"] += 1
        if re.search(r"硕士|研究生", jd):
            result["硕士"] += 1
        if "博士" in jd:
            result["博士"] += 1
    return result


def prepare_groups(items: list[dict]) -> list[dict]:
    buckets = {direction["id"]: [] for direction in DIRECTIONS}
    for item in items:
        buckets[direction_for(item)["id"]].append(item)

    groups = []
    for direction in DIRECTIONS:
        rows = sorted(
            buckets[direction["id"]],
            key=lambda item: (item.get("analysis") or {}).get("match_score", 0),
            reverse=True,
        )
        if not rows:
            continue
        scores = [(item.get("analysis") or {}).get("match_score", 0) for item in rows]
        groups.append({
            "direction": direction,
            "items": rows,
            "count": len(rows),
            "avg": round(sum(scores) / len(scores), 1),
            "top": max(scores),
            "current": sum(reporter._cohort_label(item["job"]) not in {"26届", "25届", "24届"} for item in rows),
            "jd_coverage": sum(bool(item["job"].get("jd_raw")) for item in rows),
            "skills": skill_counts(rows).most_common(10),
            "cities": top_values(rows, "city", 6),
            "companies": Counter(item["job"].get("company") or "" for item in rows).most_common(6),
            "scores": score_distribution(rows),
            "roles": metric_counts(rows, direction["role_signals"]),
            "reqs": metric_counts(rows, direction["req_signals"]),
            "education": education_counts(rows),
        })
    return groups


def bar_rows(values: list[tuple[str, int]], total: int) -> str:
    return "".join(
        f'<li><span>{escape(label)}</span><b>{count}<small>{count / max(total, 1) * 100:.0f}%</small></b><i style="--w:{max(3, count / max(total, 1) * 100):.1f}%"></i></li>'
        for label, count in values
    )


def numbered(items: list[str]) -> str:
    return "".join(f"<li>{escape(value)}</li>" for value in items)


def scale(value: int) -> str:
    return '<span class="scale">' + "".join(f'<i class="{"on" if index < value else ""}"></i>' for index in range(5)) + "</span>"


def render(groups: list[dict], total: int) -> str:
    nav = "".join(
        f'<a href="#{group["direction"]["id"]}"><span>{escape(group["direction"]["short"])}</span><b>{group["count"]}</b></a>'
        for group in groups
    )
    compare_rows = "".join(
        f'<tr><td><a href="#{group["direction"]["id"]}">{escape(group["direction"]["short"])}</a></td>'
        f'<td>{group["count"]}</td><td>{scale(group["direction"]["matrix"][0])}</td><td>{scale(group["direction"]["matrix"][1])}</td>'
        f'<td>{scale(group["direction"]["matrix"][2])}</td><td>{scale(group["direction"]["matrix"][3])}</td>'
        f'<td>{escape(group["direction"]["matrix"][4])}</td><td><strong>{escape(group["direction"]["matrix"][5])}</strong></td></tr>'
        for group in groups
    )

    sections = []
    for index, group in enumerate(groups, 1):
        direction = group["direction"]
        samples = "".join(
            "<tr>"
            f'<td><a href="{escape(item["job"].get("jd_url") or "#")}" target="_blank" rel="noopener">{escape(item["job"].get("title") or "")}</a></td>'
            f'<td>{escape(item["job"].get("company") or "")}</td><td>{escape(item["job"].get("city") or "-")}</td>'
            f'<td><strong>{(item.get("analysis") or {}).get("match_score", "-")}</strong></td></tr>'
            for item in group["items"][:12]
        )
        skills = "".join(f"<span>{escape(name)}<b>{count}</b></span>" for name, count in group["skills"][:8])
        edu = group["education"]
        sections.append(f"""
<section class="direction" id="{direction['id']}">
  <header class="direction-head">
    <div><span class="section-index">{index:02d}</span><h2>{escape(direction['name'])}</h2></div>
    <p>{escape(direction['positioning'])}</p>
  </header>
  <div class="metric-row">
    <div class="metric"><span>岗位数量</span><b>{group['count']}</b></div>
    <div class="metric"><span>当前届 / 往届</span><b>{group['current']} / {group['count'] - group['current']}</b></div>
    <div class="metric"><span>平均 / 最高匹配</span><b>{group['avg']} / {group['top']}</b></div>
    <div class="metric"><span>JD可用率</span><b>{group['jd_coverage'] / group['count'] * 100:.0f}%</b></div>
  </div>
  <div class="panel-grid primary-panels">
    <article class="panel"><h3>主要工作内容</h3><ol>{numbered(direction['responsibilities'])}</ol></article>
    <article class="panel"><h3>核心能力要求</h3><ol>{numbered(direction['requirements'])}</ol></article>
  </div>
  <div class="panel-grid data-panels">
    <article class="panel"><h3>当前JD中的职责信号</h3><ul class="bars">{bar_rows(group['roles'], group['count'])}</ul></article>
    <article class="panel"><h3>当前JD中的要求信号</h3><ul class="bars">{bar_rows(group['reqs'], group['count'])}</ul></article>
  </div>
  <div class="skill-strip">{skills}</div>
  <div class="panel-grid proof-panels">
    <article class="panel proof"><h3>建议准备的项目证据</h3><ul>{numbered(direction['projects'])}</ul></article>
    <article class="panel interview"><h3>高频面试考察</h3><ul>{numbered(direction['interview'])}</ul></article>
  </div>
  <div class="panel-grid decision-panels">
    <article class="panel fit"><h3>与你当前背景的连接</h3><p>{escape(direction['fit'])}</p></article>
    <article class="panel warning"><h3>岗位筛选风险</h3><p>{escape(direction['warning'])}</p></article>
  </div>
  <div class="fact-grid">
    <article class="panel"><h3>匹配度分布</h3><ul class="bars">{bar_rows(group['scores'], group['count'])}</ul></article>
    <article class="panel"><h3>学历明确提及</h3><ul class="bars">{bar_rows(list(edu.items()), group['count'])}</ul></article>
    <article class="panel"><h3>主要城市</h3><ul class="bars">{bar_rows(group['cities'], group['count'])}</ul></article>
    <article class="panel"><h3>主要公司</h3><ul class="bars">{bar_rows(group['companies'], group['count'])}</ul></article>
  </div>
  <details><summary>查看高匹配代表岗位</summary><div class="table-wrap"><table><thead><tr><th>岗位</th><th>公司</th><th>地点</th><th>匹配度</th></tr></thead><tbody>{samples}</tbody></table></div></details>
</section>""")

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>大模型校招岗位深度分析</title><style>
:root{{--bg:#f1f4f3;--surface:#fff;--ink:#14201d;--muted:#65716d;--line:#d8e0dd;--accent:#087f68;--soft:#e6f3ef;--soft2:#f7faf9}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Microsoft YaHei UI","Segoe UI",sans-serif;letter-spacing:0}}
.layout{{display:grid;grid-template-columns:248px minmax(0,1fr);min-height:100dvh}}aside{{position:sticky;top:0;height:100dvh;padding:28px 18px;background:#fafcfb;border-right:1px solid var(--line);overflow:auto}}.brand{{padding:0 10px 20px;border-bottom:1px solid var(--line)}}.brand strong{{display:block;font-size:17px}}.brand span{{display:block;margin-top:6px;color:var(--muted);font-size:11px}}nav{{display:grid;gap:4px;margin-top:18px}}nav a{{display:flex;justify-content:space-between;gap:10px;padding:10px;color:#42504c;text-decoration:none;border-radius:6px;font-size:12px}}nav a:hover{{background:var(--soft);color:var(--accent)}}nav b{{color:var(--muted)}}
main{{width:min(1240px,100%);margin:0 auto;padding:44px 40px 90px}}.hero{{display:grid;grid-template-columns:minmax(0,1fr) 190px;gap:40px;align-items:end;padding-bottom:28px;border-bottom:2px solid var(--ink)}}.hero h1{{margin:0;font-size:38px;line-height:1.18}}.hero p{{max-width:800px;margin:13px 0 0;color:var(--muted);font-size:14px;line-height:1.8}}.hero-stat{{text-align:right}}.hero-stat b{{display:block;color:var(--accent);font-size:46px}}.hero-stat span{{color:var(--muted);font-size:11px}}
.scope{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:24px 0 40px}}.scope article{{min-height:104px;padding:18px;background:var(--surface);border:1px solid var(--line);border-radius:6px}}.scope h2{{margin:0 0 8px;font-size:13px}}.scope p{{margin:0;color:var(--muted);font-size:12px;line-height:1.65}}
.comparison{{margin:0 0 52px;padding:26px;background:var(--surface);border:1px solid var(--line);border-radius:6px}}.comparison h2{{margin:0 0 8px;font-size:20px}}.comparison>p{{margin:0 0 18px;color:var(--muted);font-size:12px}}.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:12px}}th,td{{padding:11px 9px;text-align:left;border-bottom:1px solid #e8edeb;white-space:nowrap}}th{{color:var(--muted);font-weight:600}}td a{{color:var(--ink);font-weight:600;text-decoration:none}}td strong{{color:var(--accent)}}.scale{{display:flex;gap:3px}}.scale i{{width:13px;height:4px;background:#dfe7e4}}.scale i.on{{background:var(--accent)}}
.direction{{scroll-margin-top:20px;margin-top:56px;padding-top:34px;border-top:2px solid var(--ink)}}.direction-head{{display:grid;grid-template-columns:minmax(300px,.75fr) 1.25fr;gap:46px;align-items:start}}.direction-head>div{{display:flex;align-items:center;gap:12px}}.section-index{{font:600 12px ui-monospace,monospace;color:var(--accent)}}.direction-head h2{{margin:0;font-size:25px}}.direction-head p{{margin:0;color:#3e4c48;font-size:14px;line-height:1.8}}
.metric-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:24px}}.metric{{padding:15px 17px;background:var(--surface);border:1px solid var(--line);border-radius:6px}}.metric span{{display:block;color:var(--muted);font-size:10px}}.metric b{{display:block;margin-top:6px;font-size:18px}}
.panel-grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}}.panel{{padding:21px 22px;background:var(--surface);border:1px solid var(--line);border-radius:6px;box-shadow:0 5px 18px rgba(27,52,45,.035)}}.panel h3{{margin:0 0 13px;font-size:13px}}.panel ol,.panel ul{{display:grid;gap:9px;margin:0;padding-left:19px;color:#394742;font-size:12px;line-height:1.65}}.panel p{{margin:0;color:#394742;font-size:13px;line-height:1.8}}.primary-panels .panel:first-child{{border-top:3px solid var(--accent)}}.primary-panels .panel:last-child{{border-top:3px solid #4a5c57}}.data-panels{{margin-top:22px}}.data-panels .panel{{background:var(--soft2)}}
.bars{{list-style:none!important;padding:0!important}}.bars li{{position:relative;display:grid!important;grid-template-columns:minmax(0,1fr) auto;gap:10px;padding-bottom:6px;overflow:hidden}}.bars b{{display:flex;gap:5px;color:var(--muted);font-variant-numeric:tabular-nums}}.bars small{{font-size:10px;font-weight:500;color:#95a09c}}.bars i{{position:absolute;left:0;bottom:0;width:var(--w);height:2px;background:var(--accent)}}
.skill-strip{{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 2px;padding:16px 18px;background:#e8efed;border-radius:6px}}.skill-strip span{{display:flex;gap:7px;padding:5px 9px;background:var(--surface);border:1px solid #cbd8d4;border-radius:999px;color:#31544b;font-size:11px}}.skill-strip b{{color:var(--accent)}}.proof-panels,.decision-panels{{margin-top:18px}}.proof{{border-left:3px solid var(--accent)}}.interview{{border-left:3px solid #50635d}}.fit{{background:#edf7f4;border-color:#bdd9d1}}.warning{{background:#fbfaf6;border-color:#ded8c8}}
.fact-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:18px}}.fact-grid .panel{{padding:18px;box-shadow:none}}details{{margin-top:20px;padding:18px 20px;background:var(--surface);border:1px solid var(--line);border-radius:6px}}summary{{cursor:pointer;color:var(--accent);font-size:12px;font-weight:700}}details .table-wrap{{margin-top:13px}}
footer{{margin-top:58px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted);font-size:11px;text-align:right}}
@media(max-width:1050px){{.fact-grid{{grid-template-columns:1fr 1fr}}.direction-head{{grid-template-columns:1fr;gap:14px}}}}
@media(max-width:820px){{.layout{{display:block}}aside{{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line)}}nav{{grid-template-columns:repeat(2,minmax(0,1fr))}}main{{padding:28px 16px 70px}}.hero{{grid-template-columns:1fr}}.hero-stat{{text-align:left}}.scope{{grid-template-columns:1fr}}.metric-row{{grid-template-columns:1fr 1fr}}.panel-grid,.fact-grid{{grid-template-columns:1fr}}.direction{{margin-top:42px}}}}
@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}}}
</style></head><body><div class="layout"><aside><div class="brand"><strong>大模型岗位分析</strong><span>匹配度 50 分以上 · 7 个方向</span></div><nav>{nav}</nav></aside><main>
<header class="hero"><div><h1>大模型校招岗位深度分析</h1><p>基于当前正式校招过滤结果，对大模型相关岗位进行互斥主方向分类。智能体、RAG 与应用开发已合并，并在方向内部保留算法框架与应用工程的差异。</p></div><div class="hero-stat"><b>{total}</b><span>纳入分析的岗位</span></div></header>
<section class="scope"><article><h2>统计口径</h2><p>匹配度不低于 50 分，排除实习、方向外和无有效分析岗位，并补入具身 VLA 等交叉岗位。</p></article><article><h2>分类方法</h2><p>优先使用岗位标题判断主方向，再使用完整 JD 的职责与要求补充。一个岗位只计入一个主方向。</p></article><article><h2>阅读方法</h2><p>先看横向比较确定主投方向，再查看职责、要求、项目证据和面试内容，最后打开代表岗位核对。</p></article></section>
<section class="comparison"><h2>七个方向横向比较</h2><p>五格越多表示要求越强。个人优先级结合 C++、测试、大模型、视觉与机器人背景给出。</p><div class="table-wrap"><table><thead><tr><th>方向</th><th>岗位数</th><th>算法研究</th><th>工程开发</th><th>系统能力</th><th>数据实验</th><th>学历倾向</th><th>建议优先级</th></tr></thead><tbody>{compare_rows}</tbody></table></div></section>
{''.join(sections)}<footer>生成于 {generated} · 由 Codex 基于本地岗位标题、完整 JD 与匹配结果分析 · 未调用外部模型</footer></main></div></body></html>"""


def main() -> None:
    conn = db.init_db(ROOT / "data" / "jobs.db")
    try:
        all_items = db.get_all_jobs_with_analysis(conn)
    finally:
        conn.close()
    current, previous, _unknown, _ = reporter._filter_items(all_items)
    selected = [
        item for item in [*current, *previous]
        if (item.get("analysis") or {}).get("match_score", -1) >= 50 and is_llm_related(item)
    ]
    groups = prepare_groups(selected)
    output = ROOT / "outputs" / "llm_job_analysis_50plus.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(groups, len(selected)).replace("—", " · "), encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "jobs": len(selected),
        "directions": {group["direction"]["name"]: group["count"] for group in groups},
        "analysis": "codex-authored with deterministic JD statistics",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
