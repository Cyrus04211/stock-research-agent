# 个股深度分析工具

基于 6 阶段对抗式推理（含 Barra 因子分析）的个股研究工具，调用 DeepSeek API 生成结构化的投资分析报告。

## 功能

- **Barra 风格因子定位**：规模、价值、动量、波动率、质量、成长等 9 因子的量化定位
- **全维度数据采集**：行情估值、财务报表、研报评级、新闻公告、股东持仓、同业对比、宏观背景、一致预期、情绪信号
- **6 阶段对抗式推理**：因子定位 → 共识诊断 → 变体认知 → Alpha 论点 → 压力测试 → 投资决策
- **多市场支持**：A 股、港股、美股

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY

# 3. 运行分析
python agent.py 600519          # A 股
python agent.py AAPL            # 美股
python agent.py 0700            # 港股

# 保存报告到文件
python agent.py 600519 --save

# 仅输出数据（不调用 LLM）
python agent.py 600519 --json
```

## 配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `DEEPSEEK_API_KEY` | (必需) DeepSeek API Key | - |
| `DEEPSEEK_BASE_URL` | API 地址 | `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 模型 | `deepseek-v4-flash` |
| `FINNHUB_API_KEY` | (可选) 美股新闻情绪 | - |
| `FRED_API_KEY` | (可选) 宏观经济数据 | - |

## 项目结构

```
├── agent.py           # 主入口
├── config.py          # 全局配置（从 .env 读取）
├── requirements.txt
├── data/              # 数据采集层（9 个模块）
│   ├── price.py       # 行情与估值
│   ├── financials.py  # 财务报表
│   ├── research.py    # 研报评级
│   ├── news.py        # 新闻公告
│   ├── ownership.py   # 股东持仓
│   ├── peers.py       # 同业对比
│   ├── macro.py       # 宏观背景
│   ├── expectations.py# 一致预期
│   ├── sentiment.py   # 情绪信号
│   ├── barra.py       # Barra 因子计算
│   └── resolver.py    # 数据清洗与校验
├── alpha/             # Alpha 推理管线
│   ├── thesis.py      # 投资论点
│   ├── consensus.py   # 共识诊断
│   ├── variant.py     # 变体认知
│   ├── stress_test.py # 压力测试
│   ├── factor_analysis.py
│   └── bet_sizing.py  # 仓位建议
└── llm/               # LLM 客户端
    ├── client.py
    └── prompts.py     # 6 阶段提示词
```
