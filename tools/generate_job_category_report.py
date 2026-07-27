"""Generate an interactive HTML summary for displayed jobs scoring at least 50."""

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


CATEGORIES = [
    {
        "id": "llm-agent",
        "name": "大模型与智能体",
        "terms": ["大模型", "llm", "语言模型", "智能体", "agent", "aigc", "生成式", "自然语言", "nlp", "rag", "提示词", "多模态"],
        "title_terms": ["ai", "agi", "世界模型", "基座模型", "生成模型", "模型训练", "模型优化", "ai infra"],
        "fallback_role": "围绕大模型应用、智能体系统、知识检索与多模态能力开展算法研发、平台建设和业务落地。",
        "fallback_req": "通常要求 Python、深度学习框架和大模型应用经验，熟悉 RAG、Agent、Prompt 或模型训练部署者更有优势。",
    },
    {
        "id": "robotics",
        "name": "具身智能与机器人",
        "terms": ["具身", "机器人", "机械臂", "vla", "ros", "运动规划", "路径规划", "导航", "抓取", "机器人控制", "运动控制"],
        "title_terms": ["robotics", "robotic"],
        "fallback_role": "面向机器人感知、规划、控制和软硬件协同，完成算法设计、系统集成、仿真验证及真实设备部署。",
        "fallback_req": "常见要求包括 C++、Python、ROS、运动学或控制理论，具备机械臂、移动机器人或仿真平台项目经验更有竞争力。",
    },
    {
        "id": "vision",
        "name": "计算机视觉与感知",
        "terms": ["计算机视觉", "视觉", "图像", "点云", "感知", "slam", "目标检测", "识别", "三维重建", "3d", "标定", "激光雷达"],
        "title_terms": ["cv", "camera"],
        "fallback_role": "负责图像、视频、点云或多传感器数据的感知算法研发，并推进模型训练、评测、优化和工程部署。",
        "fallback_req": "通常要求掌握 Python 或 C++、深度学习和 OpenCV，熟悉检测、分割、跟踪、SLAM 或三维视觉中的一个或多个方向。",
    },
    {
        "id": "ml-algorithm",
        "name": "机器学习与算法",
        "terms": ["强化学习", "模仿学习", "机器学习", "深度学习", "算法工程师", "推荐算法", "预测算法", "优化算法", "数据挖掘", "算法研究"],
        "title_terms": ["算法", "规控", "modeling"],
        "fallback_role": "针对业务或研发问题建立算法方案，完成数据处理、模型训练、离线评估、性能优化和上线验证。",
        "fallback_req": "普遍看重算法与数学基础、Python 和主流机器学习框架，研究经历、竞赛或完整模型落地经验能够显著加分。",
    },
    {
        "id": "testing",
        "name": "软件测试与质量",
        "terms": ["测试开发", "软件测试", "测试工程", "自动化测试", "测开", "质量保障", "质量工程", "qa", "验证工程", "测试平台"],
        "title_terms": ["测试", "质量管理", "质检", "validation"],
        "fallback_role": "负责测试方案、自动化框架、质量平台和缺陷闭环，覆盖功能、接口、性能、稳定性及软硬件联调。",
        "fallback_req": "常要求掌握 Python、C++ 或 Java 中至少一种语言，理解测试方法、Linux 和自动化工具，具备平台或框架建设经验更佳。",
    },
    {
        "id": "embedded-control",
        "name": "嵌入式与控制",
        "terms": ["嵌入式", "单片机", "mcu", "驱动开发", "电机控制", "控制算法", "自动化控制", "底层软件", "autosar", "车载软件", "固件", "硬件开发"],
        "title_terms": ["控制工程", "firmware"],
        "fallback_role": "面向设备端、控制器或车载平台完成底层软件、驱动、控制算法和系统联调，并满足实时性与可靠性要求。",
        "fallback_req": "核心要求集中在 C/C++、MCU 或嵌入式 Linux、通信接口与调试能力，控制理论、RTOS 或汽车电子经验常作为加分项。",
    },
    {
        "id": "cpp-systems",
        "name": "C++与系统软件",
        "terms": ["c++", "系统软件", "客户端", "基础软件", "中间件", "高性能", "编译器", "操作系统", "linux", "软件开发", "服务端", "后端开发"],
        "title_terms": ["开发工程师", "软件工程师", "后台开发", "研发工程师", "software engineer"],
        "fallback_role": "负责核心软件模块、系统组件或高性能服务的设计开发，关注架构、并发、性能、稳定性和可维护性。",
        "fallback_req": "通常要求扎实的 C++、数据结构和计算机基础，熟悉 Linux、网络、并发或工程化开发流程者更匹配。",
    },
    {
        "id": "data-platform",
        "name": "数据与平台工程",
        "terms": ["数据开发", "数据分析", "数据工程", "平台开发", "云计算", "数据库", "运维开发", "devops", "大数据", "数据平台", "基础设施"],
        "title_terms": ["数字化", "平台工程", "数据"],
        "fallback_role": "建设数据处理、研发平台或基础设施，支撑数据流转、服务治理、监控运维和业务系统稳定运行。",
        "fallback_req": "常见技能包括 Python、Java、SQL、Linux、数据库和分布式系统，具备平台工程或数据链路实践更受青睐。",
    },
    {
        "id": "manufacturing",
        "name": "机械与智能制造",
        "terms": ["机械设计", "机械工程", "智能制造", "工艺", "结构设计", "机电", "自动化工程", "工业工程", "设备开发", "仿真工程"],
        "title_terms": ["机械", "结构", "工艺", "制造"],
        "fallback_role": "围绕机械结构、制造工艺、自动化设备和产线数字化开展设计、验证、优化及现场问题闭环。",
        "fallback_req": "通常要求机械、自动化或机电背景，熟悉 CAD、仿真、工艺分析或设备调试，并具备跨软硬件协作能力。",
    },
    {
        "id": "other-rd",
        "name": "其他相关研发",
        "terms": [],
        "title_terms": [],
        "fallback_role": "覆盖与目标技术方向相关但难以归入单一领域的研发、技术支持和交叉工程岗位。",
        "fallback_req": "重点考察专业基础、编程或工程实践、快速学习能力，以及将技术方案落到具体业务场景的能力。",
    },
]

SKILLS = [
    "C++", "C", "Python", "Java", "Go", "Rust", "Linux", "ROS", "OpenCV", "PyTorch",
    "TensorFlow", "CUDA", "TensorRT", "SQL", "Git", "Docker", "Kubernetes", "RTOS", "MCU",
    "AUTOSAR", "SLAM", "强化学习", "深度学习", "机器学习", "大模型", "RAG", "Agent",
    "多模态", "自动化测试", "数据分析", "控制理论", "运动规划", "点云", "目标检测",
    "三维视觉", "网络编程", "数据结构", "分布式系统", "PLC", "MATLAB", "Simulink",
]

DETAILS = {
    "cpp-systems": {
        "overview": "这一类不是简单的“会写 C++”。岗位主要交付可长期维护的核心软件，包括桌面客户端、设备上位机、SDK、后台服务、基础组件和机器人端侧模块。工作通常从需求拆解、接口设计和模块编码开始，延伸到性能分析、线上问题定位、跨平台适配和版本交付。",
        "requirements": "招聘方最看重的是语言基本功与系统理解的组合。除了语法，还会检查内存管理、数据结构、并发、网络、操作系统和调试能力。岗位越靠近基础软件、机器人或高性能计算，对 Linux、编译工具链、线程模型和性能优化的要求越高。",
        "evidence": ["可运行的中大型 C++ 项目，并能说明模块边界和技术取舍", "定位过内存、并发、崩溃或性能问题，有可量化结果", "熟悉 Linux 开发调试链路，能够阅读日志、调用栈和性能剖析结果", "有跨平台、SDK、客户端、机器人软件或高并发服务经历之一"],
        "risk": "仅有算法题或课程级 C++ 代码通常不足。标题相同的岗位可能分别偏客户端、后台、设备软件或基础设施，投递前必须继续核对 JD 的运行平台和交付形态。",
        "roles": [("核心模块设计与开发", ["模块开发", "软件开发", "功能开发", "核心模块"]), ("架构与接口设计", ["架构设计", "接口设计", "系统设计", "软件架构"]), ("性能与稳定性优化", ["性能优化", "稳定性", "高性能", "故障定位"]), ("Linux与跨平台工程", ["linux", "跨平台", "windows", "qt"]), ("联调、发布与维护", ["系统联调", "版本发布", "问题定位", "维护"] )],
        "reqs": [("C/C++编程", ["c++", "c语言", "c/c++"]), ("数据结构与算法", ["数据结构", "算法基础"]), ("操作系统与Linux", ["操作系统", "linux"]), ("并发与网络", ["多线程", "并发", "网络编程", "socket"]), ("调试与性能工具", ["gdb", "调试", "性能分析", "内存"] )],
    },
    "ml-algorithm": {
        "overview": "岗位围绕一个可衡量的问题建立算法闭环：定义目标、准备数据、训练模型、设计指标、验证效果，再把算法接入真实系统。具体方向包含预测、推荐、决策优化、强化学习、搜索和通用机器学习，交付物既包括模型，也包括评测报告和可上线代码。",
        "requirements": "数学、算法和实验能力是共同底座。招聘方通常要求 Python、至少一个深度学习框架、概率统计或优化基础，并希望候选人能独立完成数据处理到模型评估的全过程。研究型岗位会进一步要求论文阅读、复现或硕博背景。",
        "evidence": ["完整讲清一个模型从数据、训练、指标到部署的闭环", "有基线对比、消融实验、误差分析或线上效果提升", "能解释模型为什么有效，而不是只调用现成接口", "强化学习岗位需说明状态、动作、奖励设计和仿真到真实迁移"],
        "risk": "“算法工程师”覆盖面很大。推荐、控制、视觉、运筹和大模型所需知识不同，不能用同一份泛化简历覆盖。只罗列模型名称而没有实验与指标，会被判断为停留在使用层。",
        "roles": [("数据处理与特征工程", ["数据处理", "特征工程", "数据清洗"]), ("模型训练与调优", ["模型训练", "模型优化", "训练优化", "调参"]), ("评测与误差分析", ["模型评估", "效果评估", "误差分析", "评测"]), ("算法工程化部署", ["工程化", "模型部署", "上线", "推理优化"]), ("前沿研究与复现", ["前沿研究", "论文", "算法研究", "技术预研"] )],
        "reqs": [("Python编程", ["python"]), ("机器学习与深度学习", ["机器学习", "深度学习"]), ("数学与统计基础", ["概率统计", "线性代数", "数学基础", "优化理论"]), ("PyTorch或TensorFlow", ["pytorch", "tensorflow"]), ("实验设计能力", ["实验设计", "消融", "评估指标", "模型评估"] )],
    },
    "testing": {
        "overview": "测试岗位的核心不是执行测试用例，而是建立可重复的质量保障机制。职责覆盖需求评审、测试方案、自动化脚本、接口与性能测试、软硬件联调、缺陷分析和质量平台建设。测试开发岗位还要直接开发框架、工具和流水线。",
        "requirements": "基础门槛包括测试方法、至少一门编程语言、Linux 和问题定位能力。面向机器人、汽车或智能制造的岗位还要求理解设备通信、传感器或控制系统。高级匹配通常来自自动化框架、CI/CD、性能测试和复杂故障定位经验。",
        "evidence": ["独立设计过测试方案，能说明覆盖范围、风险和退出标准", "开发过自动化框架或测试工具，而非只写零散脚本", "能从日志、接口、数据库、网络或硬件链路定位根因", "给出缺陷发现率、回归时间、覆盖率或效率提升等结果"],
        "risk": "同名岗位可能偏功能测试、测试开发、硬件验证或质量管理。若目标是测开，应优先筛选明确要求编程、框架和平台建设的 JD，避免大量纯执行型测试。",
        "roles": [("测试方案与用例设计", ["测试方案", "测试用例", "需求评审"]), ("自动化框架建设", ["自动化测试", "测试框架", "测试平台"]), ("性能与稳定性测试", ["性能测试", "稳定性测试", "压力测试", "可靠性"]), ("缺陷定位与质量闭环", ["缺陷", "问题定位", "根因分析", "质量分析"]), ("持续集成与回归", ["持续集成", "ci/cd", "jenkins", "回归测试"] )],
        "reqs": [("Python/C++/Java编程", ["python", "c++", "java"]), ("Linux与脚本能力", ["linux", "shell"]), ("测试理论与方法", ["测试方法", "测试理论", "测试流程"]), ("接口、数据库与网络", ["接口测试", "数据库", "网络协议"]), ("自动化与CI工具", ["pytest", "selenium", "jenkins", "自动化测试"] )],
    },
    "llm-agent": {
        "overview": "岗位主要分为模型层和应用层。模型层负责数据构建、预训练、微调、对齐、推理与评测；应用层负责 RAG、智能体编排、工具调用、多模态交互和业务系统集成。共同交付物是可评测、可部署并能持续迭代的大模型能力。",
        "requirements": "Python、深度学习与 Transformer 是技术底座。模型岗更看重 PyTorch、训练优化、分布式计算和论文能力；应用岗更看重 RAG、向量检索、Agent 框架、工程接口和效果评测。仅会调用聊天接口通常达不到校招研发岗位要求。",
        "evidence": ["完成过 RAG 或 Agent 项目，并说明检索、编排、评测和失败处理", "有 LoRA、SFT、偏好对齐或推理优化实践之一", "建立过自动评测集，能分析幻觉、召回、延迟和成本", "理解工具调用、上下文管理、记忆机制和安全边界"],
        "risk": "岗位名称都可能写 AI，但模型训练、算法研究、应用开发和 AI Infra 的技能树不同。应根据是否出现训练集群、微调、RAG、Agent、推理服务等词进一步拆分简历。",
        "roles": [("数据构建与治理", ["数据构建", "数据清洗", "数据治理", "高质量数据"]), ("训练、微调与对齐", ["预训练", "微调", "sft", "对齐", "lora"]), ("RAG与知识检索", ["rag", "向量检索", "知识库", "检索增强"]), ("Agent与工具调用", ["agent", "智能体", "工具调用", "mcp"]), ("推理部署与评测", ["推理优化", "模型部署", "模型评测", "大模型评测"] )],
        "reqs": [("Python与PyTorch", ["python", "pytorch"]), ("Transformer与大模型基础", ["transformer", "大模型", "llm"]), ("RAG或Agent实践", ["rag", "agent", "智能体"]), ("训练与分布式系统", ["分布式训练", "deepspeed", "训练框架"]), ("评测与效果分析", ["评测", "幻觉", "准确率", "召回率"] )],
    },
    "robotics": {
        "overview": "岗位交付的是能够在真实设备上稳定运行的机器人能力，通常横跨感知、定位、规划、控制和系统集成。日常工作包括算法开发、ROS 节点与通信、仿真验证、传感器和执行器联调，以及现场问题定位。",
        "requirements": "C++、Python、ROS 和机器人学基础是高频组合。规划控制岗需要运动学、动力学、轨迹规划或控制理论；具身方向还可能要求强化学习、模仿学习、VLA 和仿真数据。工程岗位非常看重真实机器人调试经验。",
        "evidence": ["在真实机器人或机械臂上完成闭环任务，而不只是仿真演示", "能描述感知、规划、控制之间的数据流和时序", "处理过坐标系、标定、通信延迟、轨迹抖动或安全约束", "有 ROS2、MoveIt、Gazebo/Isaac Sim 或硬件驱动经验"],
        "risk": "具身智能研究岗与传统机器人软件岗差异明显。前者偏学习算法和数据，后者偏 C++、ROS、实时系统与设备联调，应分别准备项目叙述。",
        "roles": [("机器人软件架构", ["机器人软件", "软件架构", "ros2", "ros"]), ("运动规划与决策", ["运动规划", "路径规划", "轨迹规划", "决策规划"]), ("控制与执行", ["运动控制", "控制算法", "执行器", "伺服"]), ("仿真与算法验证", ["仿真", "gazebo", "isaac sim", "算法验证"]), ("系统集成与实机调试", ["系统集成", "实机", "联调", "机器人调试"] )],
        "reqs": [("C++与Python", ["c++", "python"]), ("ROS/ROS2", ["ros", "ros2"]), ("机器人学基础", ["机器人学", "运动学", "动力学"]), ("规划与控制算法", ["运动规划", "路径规划", "控制理论"]), ("强化或模仿学习", ["强化学习", "模仿学习", "vla"] )],
    },
    "vision": {
        "overview": "视觉与感知岗位从图像、视频、点云或多传感器数据中提取环境信息。职责通常包括数据准备、模型训练、检测分割跟踪、三维重建或 SLAM、指标评估、推理优化和端侧部署。机器人与汽车岗位还要求和定位规划模块联调。",
        "requirements": "图像处理、几何视觉或深度学习基础是核心。常见工具为 Python、C++、OpenCV、PyTorch、PCL、CUDA 和 TensorRT。偏三维与 SLAM 的岗位会加强坐标变换、相机模型、点云和优化理论要求。",
        "evidence": ["明确任务、数据集、评价指标和模型改进幅度", "处理过真实数据中的遮挡、光照、类别不平衡或传感器噪声", "完成过模型部署、量化、TensorRT 加速或端侧优化", "三维岗位应展示标定、坐标系、点云或 SLAM 实践"],
        "risk": "视觉算法不能只写“使用 YOLO”。招聘方更关注数据问题、模型选择理由、指标提升和部署约束。二维视觉、三维点云与 SLAM 也应分开准备。",
        "roles": [("检测、分割与跟踪", ["目标检测", "图像分割", "目标跟踪", "识别算法"]), ("三维视觉与点云", ["点云", "三维重建", "3d视觉", "pcl"]), ("SLAM与定位", ["slam", "视觉定位", "建图", "位姿"]), ("模型训练与评估", ["模型训练", "算法评估", "数据集", "模型优化"]), ("推理加速与部署", ["tensorrt", "推理加速", "端侧部署", "模型部署"] )],
        "reqs": [("Python/C++", ["python", "c++"]), ("OpenCV与图像处理", ["opencv", "图像处理"]), ("PyTorch与深度学习", ["pytorch", "深度学习"]), ("几何视觉与标定", ["相机标定", "多视几何", "坐标变换"]), ("CUDA/TensorRT", ["cuda", "tensorrt"] )],
    },
    "embedded-control": {
        "overview": "岗位面向 MCU、嵌入式 Linux、控制器、汽车电子或自动化设备，交付驱动、固件、实时任务和控制算法。工作包含硬件接口、通信协议、状态机、控制逻辑、实时性优化、板级调试和系统联调。",
        "requirements": "C/C++、计算机体系结构和硬件接口是基础。固件岗偏 MCU、RTOS、驱动和通信总线；控制岗偏经典控制、状态估计、MPC/PID 和 MATLAB/Simulink；车载岗还会要求 AUTOSAR、功能安全或 CAN。",
        "evidence": ["有板卡、传感器、电机或控制器实物调试经历", "能解释中断、任务调度、内存、实时性和通信协议", "使用示波器、逻辑分析仪、JTAG 或日志定位过问题", "控制项目需给出稳定性、响应时间、误差或轨迹效果"],
        "risk": "“嵌入式”内部差异很大。Linux 应用、内核驱动、MCU 固件和控制算法不能混为一类，简历需要突出和 JD 对应的硬件平台与工具链。",
        "roles": [("驱动与固件开发", ["驱动开发", "固件", "底层驱动", "bsp"]), ("实时任务与系统软件", ["rtos", "实时系统", "任务调度", "嵌入式软件"]), ("通信与接口", ["can", "spi", "i2c", "通信协议"]), ("控制算法开发", ["pid", "mpc", "控制算法", "状态估计"]), ("板级与系统联调", ["板级调试", "硬件调试", "系统联调", "示波器"] )],
        "reqs": [("C/C++", ["c++", "c语言", "c/c++"]), ("MCU或嵌入式Linux", ["mcu", "嵌入式linux", "单片机"]), ("RTOS与实时性", ["rtos", "实时性", "freertos"]), ("硬件通信总线", ["can", "spi", "i2c", "uart"]), ("控制理论或AUTOSAR", ["控制理论", "autosar", "simulink"] )],
    },
    "manufacturing": {
        "overview": "该类岗位连接机械设计、自动化设备、制造工艺和数字化系统。常见交付物包括结构方案、工艺文件、仿真模型、自动化设备方案、产线优化结果和现场问题闭环。智能制造岗位还会使用数据或 AI 改进生产效率。",
        "requirements": "机械、自动化、机电或工业工程基础最重要。岗位通常要求 CAD/CAE、机械原理、材料工艺、设备调试或 PLC 能力，并强调跨部门协作和现场执行。偏数字化的岗位会增加 Python、数据分析和系统集成要求。",
        "evidence": ["展示从需求、方案、建模、加工装配到验证的完整机械项目", "能说明公差、材料、强度、工艺和成本之间的取舍", "有设备调试、产线改善、节拍提升或故障闭环数据", "智能制造方向可补充 PLC、机器视觉、数字孪生或数据分析"],
        "risk": "机械设计、工艺、设备和数字化岗位的工作现场差异较大。只写软件项目无法证明制造岗位所需的工程落地能力。",
        "roles": [("机械结构与方案设计", ["结构设计", "机械设计", "方案设计"]), ("工艺与制造优化", ["工艺优化", "制造工艺", "工艺设计"]), ("仿真与验证", ["仿真分析", "有限元", "cae", "强度分析"]), ("自动化设备开发", ["自动化设备", "设备开发", "产线"]), ("现场调试与问题闭环", ["现场调试", "设备调试", "问题闭环", "持续改善"] )],
        "reqs": [("机械与自动化基础", ["机械原理", "自动化", "机械工程"]), ("CAD/CAE工具", ["solidworks", "creo", "cad", "ansys"]), ("材料、公差与工艺", ["材料", "公差", "制造工艺"]), ("PLC与设备调试", ["plc", "设备调试"]), ("项目与现场能力", ["项目管理", "现场", "跨部门"] )],
    },
    "data-platform": {
        "overview": "岗位建设研发平台、数据管道、云基础设施或运维工具，为算法和业务团队提供稳定的数据与服务能力。职责包括数据采集清洗、任务编排、接口服务、数据库设计、监控告警、发布流程和成本性能优化。",
        "requirements": "Python、Java、Go 或 SQL 是常见语言，Linux、数据库、网络和分布式系统构成基础。平台岗还会要求容器、云服务、CI/CD 和可观测性；数据岗更强调数据仓库、ETL 和数据质量。",
        "evidence": ["构建过端到端数据管道或平台服务，并能说明吞吐与稳定性", "有数据库设计、任务调度、失败重试和监控告警实践", "使用 Docker/Kubernetes 或云平台完成部署", "能够量化查询性能、处理时延、资源成本或研发效率提升"],
        "risk": "平台开发、数据工程和运维开发虽然技术重叠，但交付物不同。简历需要明确自己负责的是服务、数据链路还是基础设施。",
        "roles": [("数据采集与ETL", ["数据采集", "etl", "数据清洗", "数据管道"]), ("平台服务开发", ["平台开发", "接口开发", "微服务"]), ("数据库与数据治理", ["数据库设计", "数据治理", "数据质量"]), ("部署、监控与运维", ["监控告警", "devops", "持续交付", "运维平台"]), ("性能与成本优化", ["性能优化", "资源优化", "成本优化"] )],
        "reqs": [("Python/Java/Go", ["python", "java", "golang", "go语言"]), ("SQL与数据库", ["sql", "数据库"]), ("Linux与网络", ["linux", "网络"]), ("分布式系统", ["分布式", "消息队列", "微服务"]), ("Docker/Kubernetes", ["docker", "kubernetes", "k8s"] )],
    },
    "other-rd": {
        "overview": "这一组包含技术预研、解决方案、研发管理、交叉学科和标题信息不足的岗位。共同点是仍与目标技术方向相关，但仅凭标题无法确定主要交付物，需要逐条阅读 JD 后再判断。",
        "requirements": "要求通常由具体业务场景决定，可能同时涉及软件、算法、硬件和沟通协作。相比专门岗位，这一类更强调快速学习、跨团队推进和把模糊需求转化为技术方案。",
        "evidence": ["能够处理开放问题，并形成可验证的技术方案", "有跨软件、算法或硬件边界的项目协作经历", "清楚说明自己在团队中的实际负责范围", "针对具体 JD 重新提炼关键词，避免直接使用通用简历"],
        "risk": "该类是分类后的待精读区，不代表岗位质量低。标题过于笼统时，必须以职责和任职要求判断是否值得投递。",
        "roles": [("技术预研", ["技术预研", "前沿技术", "可行性研究"]), ("解决方案与集成", ["解决方案", "系统集成", "方案设计"]), ("跨团队项目推进", ["跨部门", "项目推进", "协同"]), ("应用研发", ["应用开发", "产品研发"]), ("技术支持与交付", ["技术支持", "项目交付", "客户现场"] )],
        "reqs": [("编程与工程基础", ["编程能力", "软件开发", "python", "c++"]), ("专业领域知识", ["专业知识", "相关专业"]), ("学习与研究能力", ["学习能力", "研究能力", "技术预研"]), ("沟通协作", ["沟通能力", "团队协作"]), ("项目落地能力", ["项目经验", "工程实践", "落地"] )],
    },
}


def classify(item: dict) -> dict:
    job = item["job"]
    title = (job.get("title") or "").casefold()
    jd = (job.get("jd_raw") or "").casefold()
    best = CATEGORIES[-1]
    best_score = 0
    for category in CATEGORIES[:-1]:
        title_hits = sum(1 for term in category["terms"] if term.casefold() in title)
        jd_hits = sum(1 for term in category["terms"] if term.casefold() in jd)
        title_only_hits = sum(
            1 for term in category.get("title_terms", [])
            if contains_term(title, term)
        )
        score = title_hits * 7 + title_only_hits * 5 + min(jd_hits, 5)
        if score > best_score:
            best, best_score = category, score
    return best


def contains_term(text: str, term: str) -> bool:
    term = term.casefold()
    if term.isascii() and term.replace(" ", "").isalnum():
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text))
    return term in text


def cohort_name(job: dict) -> str:
    return reporter._cohort_label(job)


def skill_counts(items: list[dict]) -> Counter:
    counter = Counter()
    for item in items:
        text = f"{item['job'].get('title', '')} {item['job'].get('jd_raw', '')}".casefold()
        for skill in SKILLS:
            if skill.casefold() in text:
                counter[skill] += 1
    return counter


def top_values(items: list[dict], field: str, limit: int = 6) -> list[tuple[str, int]]:
    values = Counter()
    for item in items:
        raw = item["job"].get(field) or ""
        parts = re.split(r"[,，/、;；|\s]+", raw)
        for value in parts:
            value = value.strip()
            if value and value not in {"不限", "全国", "待填写", "-"}:
                values[value] += 1
    return values.most_common(limit)


def education_summary(items: list[dict]) -> str:
    texts = [item["job"].get("jd_raw") or "" for item in items]
    bachelor = sum(bool(re.search(r"本科|学士", text)) for text in texts)
    master = sum(bool(re.search(r"硕士|研究生|博士", text)) for text in texts)
    if master > bachelor * 0.55:
        return "本科是常见门槛，算法研究类岗位对硕士及以上学历偏好明显"
    if bachelor:
        return "多数岗位以本科及以上为主，研究型岗位会进一步偏好硕士背景"
    return "学历描述不统一，实际筛选更强调专业基础与项目经历"


def signal_metrics(items: list[dict], definitions: list[tuple[str, list[str]]]) -> list[tuple[str, int]]:
    result = []
    for label, terms in definitions:
        count = 0
        for item in items:
            text = f"{item['job'].get('title', '')} {item['job'].get('jd_raw', '')}".casefold()
            if any(contains_term(text, term) for term in terms):
                count += 1
        result.append((label, count))
    return sorted(result, key=lambda value: value[1], reverse=True)


def score_distribution(items: list[dict]) -> list[tuple[str, int]]:
    bands = Counter()
    for item in items:
        score = (item.get("analysis") or {}).get("match_score", 0)
        if score >= 80:
            bands["80分及以上"] += 1
        elif score >= 70:
            bands["70至79分"] += 1
        elif score >= 60:
            bands["60至69分"] += 1
        else:
            bands["50至59分"] += 1
    return [(label, bands[label]) for label in ("80分及以上", "70至79分", "60至69分", "50至59分")]


def prepare_groups(items: list[dict]) -> list[dict]:
    buckets = {category["id"]: [] for category in CATEGORIES}
    for item in items:
        buckets[classify(item)["id"]].append(item)
    groups = []
    for category in CATEGORIES:
        rows = sorted(
            buckets[category["id"]],
            key=lambda item: (item.get("analysis") or {}).get("match_score", 0),
            reverse=True,
        )
        if not rows:
            continue
        scores = [(item.get("analysis") or {}).get("match_score", 0) for item in rows]
        detail = DETAILS[category["id"]]
        groups.append({
            "category": category,
            "items": rows,
            "avg": round(sum(scores) / len(scores), 1),
            "top": max(scores),
            "current": sum(cohort_name(item["job"]) not in {"26届", "25届", "24届"} for item in rows),
            "skills": skill_counts(rows).most_common(12),
            "cities": top_values(rows, "city"),
            "companies": Counter(item["job"].get("company") or "" for item in rows).most_common(6),
            "education": education_summary(rows),
            "jd_coverage": sum(bool(item["job"].get("jd_raw")) for item in rows),
            "role_metrics": signal_metrics(rows, detail["roles"]),
            "requirement_metrics": signal_metrics(rows, detail["reqs"]),
            "score_distribution": score_distribution(rows),
        })
    groups.sort(key=lambda group: len(group["items"]), reverse=True)
    return groups


def bars(values: list[tuple[str, int]], total: int) -> str:
    return "".join(
        f'<li><span>{escape(name)}</span><b>{count}<small>{count / max(total, 1) * 100:.0f}%</small></b><i style="--w:{max(4, count / max(total, 1) * 100):.1f}%"></i></li>'
        for name, count in values
    ) or '<li class="muted">数据不足</li>'


def render(groups: list[dict], total: int) -> str:
    nav = "".join(
        f'<a href="#{group["category"]["id"]}"><span>{escape(group["category"]["name"])}</span><b>{len(group["items"])}</b></a>'
        for group in groups
    )
    sections = []
    for index, group in enumerate(groups, 1):
        category = group["category"]
        detail = DETAILS[category["id"]]
        chips = "".join(f"<span>{escape(name)}</span>" for name, _ in group["skills"][:8])
        evidence = "".join(f"<li>{escape(value)}</li>" for value in detail["evidence"])
        sample_rows = "".join(
            "<tr>"
            f'<td><a href="{escape(item["job"].get("jd_url") or "#")}" target="_blank" rel="noopener">{escape(item["job"].get("title") or "")}</a></td>'
            f'<td>{escape(item["job"].get("company") or "")}</td>'
            f'<td>{escape(item["job"].get("city") or "-")}</td>'
            f'<td><strong>{(item.get("analysis") or {}).get("match_score", "-")}</strong></td>'
            "</tr>"
            for item in group["items"][:10]
        )
        sections.append(f"""
<section id="{category['id']}" class="category" data-search="{escape(category['name'])}">
  <header class="category-head">
    <div><span class="index">{index:02d}</span><h2>{escape(category['name'])}</h2></div>
    <div class="category-metrics"><span><b>{len(group['items'])}</b> 个岗位</span><span>当前届 <b>{group['current']}</b></span><span>往届 <b>{len(group['items']) - group['current']}</b></span><span>平均 <b>{group['avg']}</b></span><span>最高 <b>{group['top']}</b></span></div>
  </header>
  <div class="summary-grid">
    <div class="summary-block"><h3>岗位描述与实际交付</h3><p>{escape(detail['overview'])}</p></div>
    <div class="summary-block"><h3>招聘要求与能力边界</h3><p>{escape(detail['requirements'])}</p><p class="education">学历判断：{escape(group['education'])}</p></div>
  </div>
  <div class="signals">{chips}</div>
  <div class="signal-grid">
    <div><h3>JD 中明确出现的工作内容</h3><ul class="bars">{bars(group['role_metrics'], len(group['items']))}</ul></div>
    <div><h3>JD 中明确出现的能力要求</h3><ul class="bars">{bars(group['requirement_metrics'], len(group['items']))}</ul></div>
  </div>
  <div class="guidance-grid">
    <div><h3>简历和面试应提供的证据</h3><ul class="evidence-list">{evidence}</ul></div>
    <div><h3>筛选时需要注意</h3><p>{escape(detail['risk'])}</p><p class="coverage">本类 {group['jd_coverage']} / {len(group['items'])} 个岗位保存了完整或部分 JD，可用率 {group['jd_coverage'] / len(group['items']) * 100:.0f}% 。统计比例表示 JD 明确提及，不等于未提及的岗位完全不要求。</p></div>
  </div>
  <div class="evidence-grid">
    <div><h3>高频技术栈</h3><ul class="bars">{bars(group['skills'][:8], len(group['items']))}</ul></div>
    <div><h3>匹配度分布</h3><ul class="bars">{bars(group['score_distribution'], len(group['items']))}</ul></div>
    <div><h3>主要城市</h3><ul class="bars">{bars(group['cities'], len(group['items']))}</ul></div>
    <div><h3>主要公司</h3><ul class="bars">{bars(group['companies'], len(group['items']))}</ul></div>
  </div>
  <details>
    <summary>查看高匹配代表岗位</summary>
    <div class="table-wrap"><table><thead><tr><th>岗位</th><th>公司</th><th>地点</th><th>匹配度</th></tr></thead><tbody>{sample_rows}</tbody></table></div>
  </details>
</section>""")

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>50分以上岗位分类总结</title>
<style>
:root{{--bg:#f4f6f5;--surface:#fff;--ink:#17211f;--muted:#68736f;--line:#dce3e0;--accent:#087f68;--soft:#e7f4f0}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:"Microsoft YaHei UI","Segoe UI",sans-serif;letter-spacing:0}}
.layout{{display:grid;grid-template-columns:250px minmax(0,1fr);min-height:100dvh}}aside{{position:sticky;top:0;height:100dvh;padding:28px 18px;border-right:1px solid var(--line);background:#f9fbfa;overflow:auto}}
.brand{{padding:0 10px 20px;border-bottom:1px solid var(--line)}}.brand strong{{display:block;font-size:18px}}.brand span{{display:block;margin-top:5px;color:var(--muted);font-size:12px}}
nav{{display:grid;gap:3px;margin-top:18px}}nav a{{display:flex;justify-content:space-between;gap:12px;padding:9px 10px;color:#42504c;text-decoration:none;border-radius:6px;font-size:13px}}nav a:hover{{background:var(--soft);color:var(--accent)}}nav b{{color:var(--muted);font-variant-numeric:tabular-nums}}
main{{width:min(1180px,100%);margin:0 auto;padding:44px 36px 80px}}.hero{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:30px;align-items:end;padding-bottom:26px;border-bottom:2px solid var(--ink)}}
.hero h1{{margin:0;font-size:36px;line-height:1.18}}.hero p{{margin:12px 0 0;max-width:720px;color:var(--muted);line-height:1.75}}.hero-stat{{text-align:right}}.hero-stat b{{display:block;font-size:42px;color:var(--accent)}}.hero-stat span{{font-size:12px;color:var(--muted)}}
.toolbar{{display:flex;align-items:center;gap:12px;margin:22px 0}}.toolbar input{{width:min(420px,100%);height:40px;padding:0 13px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink);font:inherit;outline:none}}.toolbar input:focus{{border-color:var(--accent);box-shadow:0 0 0 3px #087f6818}}.toolbar span{{color:var(--muted);font-size:12px}}
.category{{scroll-margin-top:18px;margin-top:22px;padding:26px;background:var(--surface);border:1px solid var(--line);border-radius:6px}}.category[hidden]{{display:none}}
.category-head{{display:flex;justify-content:space-between;gap:20px;align-items:center;padding-bottom:18px;border-bottom:1px solid var(--line)}}.category-head>div:first-child{{display:flex;align-items:center;gap:12px}}.index{{font:600 12px ui-monospace,monospace;color:var(--accent)}}h2{{margin:0;font-size:22px}}.category-metrics{{display:flex;gap:18px;color:var(--muted);font-size:12px}}.category-metrics b{{color:var(--ink);font-size:16px}}
.summary-grid{{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:22px}}h3{{margin:0 0 9px;font-size:13px;color:#43504d}}.summary-block p{{margin:0;color:#394743;line-height:1.8;font-size:14px}}.summary-block .education{{margin-top:9px;color:var(--muted);font-size:12px}}
.signals{{display:flex;flex-wrap:wrap;gap:7px;margin-top:18px}}.signals span{{padding:5px 9px;border:1px solid #bcd8d0;border-radius:999px;background:var(--soft);color:#176252;font-size:12px}}
.signal-grid{{display:grid;grid-template-columns:1fr 1fr;gap:34px;margin-top:24px;padding-top:20px;border-top:1px solid var(--line)}}.guidance-grid{{display:grid;grid-template-columns:1fr 1fr;gap:34px;margin-top:24px;padding:20px;background:#f7faf9;border-left:3px solid var(--accent)}}.guidance-grid p{{margin:0;color:#43504d;font-size:13px;line-height:1.75}}.coverage{{margin-top:10px!important;color:var(--muted)!important;font-size:11px!important}}.evidence-list{{display:grid;gap:7px;margin:0;padding-left:18px;color:#35433f;font-size:12px;line-height:1.6}}
.evidence-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;margin-top:24px;padding-top:20px;border-top:1px solid var(--line)}}.bars{{display:grid;gap:9px;margin:0;padding:0;list-style:none}}.bars li{{position:relative;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;padding-bottom:5px;font-size:12px;overflow:hidden}}.bars span,.bars b{{position:relative;z-index:1}}.bars b{{display:flex;gap:5px;color:var(--muted);font-variant-numeric:tabular-nums}}.bars small{{font-size:10px;font-weight:500;color:#95a09c}}.bars i{{position:absolute;left:0;bottom:0;width:var(--w);height:2px;background:var(--accent)}}
details{{margin-top:22px;border-top:1px solid var(--line);padding-top:15px}}summary{{cursor:pointer;color:var(--accent);font-weight:600;font-size:13px}}.table-wrap{{overflow:auto;margin-top:14px}}table{{width:100%;border-collapse:collapse;font-size:12px}}th,td{{padding:10px 8px;text-align:left;border-bottom:1px solid #edf1ef}}th{{color:var(--muted);font-weight:600}}td a{{color:var(--ink);text-decoration:none}}td a:hover{{color:var(--accent)}}td strong{{color:var(--accent)}}
.empty{{padding:50px;text-align:center;color:var(--muted)}}footer{{padding:28px 0 0;color:var(--muted);font-size:11px;text-align:right}}
@media(max-width:1000px){{.evidence-grid{{grid-template-columns:1fr 1fr}}}}
@media(max-width:850px){{.layout{{display:block}}aside{{position:static;width:100%;height:auto;border-right:0;border-bottom:1px solid var(--line)}}nav{{grid-template-columns:repeat(2,minmax(0,1fr))}}main{{padding:28px 16px 60px}}.hero{{grid-template-columns:1fr}}.hero-stat{{text-align:left}}.summary-grid,.signal-grid,.guidance-grid,.evidence-grid{{grid-template-columns:1fr}}.category-head{{align-items:flex-start;flex-direction:column}}.category-metrics{{flex-wrap:wrap}}}}
@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}}}
</style></head><body><div class="layout"><aside><div class="brand"><strong>岗位方向图谱</strong><span>匹配度 50 分以上</span></div><nav>{nav}</nav></aside>
<main><header class="hero"><div><h1>岗位分类与能力要求总结</h1><p>基于当前数据库中通过正式校招过滤且匹配度不低于 50 分的岗位，按完整 JD 进行互斥分类。统计覆盖当前届与往届校招，用于快速判断不同方向的共同要求。</p></div><div class="hero-stat"><b>{total}</b><span>纳入分析的岗位</span></div></header>
<div class="toolbar"><input id="search" type="search" placeholder="搜索岗位类别或技能要求"><span>{len(groups)} 个技术方向</span></div>{''.join(sections)}
<footer>生成于 {generated} · 由 Codex 基于本地岗位 JD 与统计结果分析 · 未调用外部模型</footer></main></div>
<script>const input=document.getElementById('search');input.addEventListener('input',()=>{{const q=input.value.trim().toLowerCase();document.querySelectorAll('.category').forEach(section=>{{section.hidden=q&&!section.textContent.toLowerCase().includes(q)}})}});</script>
</body></html>"""


def main() -> None:
    conn = db.init_db(ROOT / "data" / "jobs.db")
    try:
        all_items = db.get_all_jobs_with_analysis(conn)
    finally:
        conn.close()
    current, previous, _unknown, _ = reporter._filter_items(all_items)
    selected = [
        item for item in [*current, *previous]
        if (item.get("analysis") or {}).get("match_score", -1) >= 50
    ]
    groups = prepare_groups(selected)
    output = ROOT / "outputs" / "job_category_summary_50plus.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render(groups, len(selected)).replace("—", " · "),
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(output),
        "jobs": len(selected),
        "categories": {group["category"]["name"]: len(group["items"]) for group in groups},
        "analysis": "codex-authored with deterministic JD statistics",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
