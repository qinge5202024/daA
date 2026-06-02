# A 股板块龙头观察名单工具

一个本地运行的 A 股研究工作台，用于从“资金进入的板块”里筛选具备龙头特征、基本面质量、估值纪律和分红可持续性的观察名单。

本项目只输出研究观察、评分、风险和条件化复核，不提供买卖信号、仓位建议或自动交易。

## 作者与合作

作者：qinge5202024

这是一个面向 A 股个人研究者的观察名单工具，目标是把公开行情、板块热度、资金验证、技术参考价位、持仓复核和 AI 解释放到同一个本地工作台里。项目不承诺预测涨跌，也不输出买卖指令，只帮助使用者更有结构地整理信息。

合作、功能共建、数据源适配、私有化部署、策略模块合作和问题反馈，可以通过以下方式联系：

```text
邮箱：haliqinge@gmail.com
微信：黄金（关于页面可扫码添加）
https://github.com/qinge5202024/daA/issues
```

## 功能概览

- 数据导入：支持 CSV 股票池导入和字段标准化。
- 免费数据源：支持东方财富公开接口、AkShare、腾讯行情、Baostock、同花顺和新浪等公开源兜底。
- 财务补全：可批量补充 ROE、营收增长、利润增长、现金流比、股息率、分红支付率、营收和净利润。
- 资金验证：展示个股和板块资金净额、净占比、资金验证结论；不识别具体“庄家”。
- 热点板块：按板块涨跌幅、成交额、量比、上涨家数占比和资金流生成热点榜。
- 策略评分：板块资金、龙头地位、长期质量、估值纪律、分红持续、行业风险。
- 技术价位：生成支撑位、压力位、趋势概率和 K 线形态参考。
- 持仓复核：录入持仓后，按短线或长线周期生成条件化观察区和风险复核位。
- AI 研究复核：支持 OpenAI 兼容接口，例如 DeepSeek；AI 只生成解释和复核，不参与原始评分。
- 本地缓存：行情、财务、评分、配置和导入数据都保存在本地 `data/` 目录。

## 技术栈

- 后端：Python, FastAPI, Pandas
- 前端：React, TypeScript, Vite
- 数据源：AkShare、东方财富公开接口、腾讯公开行情、Baostock 等
- AI：OpenAI 兼容 Chat Completions 接口

## 快速开始

### 1. 克隆项目

```powershell
git clone <your-repo-url>
cd gupiao
```

### 2. 安装依赖

```powershell
python -m pip install -r requirements.txt
npm run frontend:install
```

### 3. 配置 AI（可选）

复制示例配置：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```env
AI_BASE_URL=https://api.deepseek.com
AI_API_KEY=replace-with-your-key
AI_MODEL=deepseek-v4-flash
```

未配置 `AI_API_KEY` 时，系统仍可运行，会返回本地规则复核结果。

### 4. 启动开发环境

一键启动：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-dev.ps1
```

或分开启动：

```powershell
npm run backend
npm run dev
```

打开浏览器：

```text
http://127.0.0.1:5173
```

后端 API：

```text
http://127.0.0.1:8000
```

## 常用命令

```powershell
# 后端测试
python -m unittest discover backend/tests

# 前端构建
npm run build

# 仅启动后端
npm run backend

# 仅启动前端
npm run dev
```

## 数据工作流

1. 在“数据”页导入 CSV，或点击“刷新免费行情”。
2. 点击“补充财务指标”，补全 ROE、增长、股息率、现金流等字段。
3. 如需资金字段，点击“补充资金流”。
4. 在“策略”页调整权重、阈值和谨慎行业清单。
5. 点击“重新评分”，生成观察名单。
6. 在“结果”“热点”“详情”“持仓”页面做进一步研究复核。

## CSV 字段

支持中文或英文别名，常用字段包括：

```text
代码, 名称, 板块, 行业
总市值, 成交额, 涨跌幅, 量比
市盈率, 市净率, 股息率, ROE
营收增长, 利润增长, 现金流, 分红支付率
营业收入, 净利润, 历史PE分位
板块涨跌幅, 板块成交额, 板块成交额增速
主力净流入, 主力净占比, 大单净流入, 大单净占比
板块主力净流入, 板块主力净占比
```

可以使用 [data/sample_stocks.csv](data/sample_stocks.csv) 体验导入流程。

## 数据源说明

刷新顺序会优先选择可用公开源，并在失败时使用本地缓存兜底：

```text
东方财富公开 JSON
-> AkShare 东方财富 A 股接口
-> 腾讯全 A 行情
-> 腾讯行情 + Baostock 行业映射
-> 同花顺行业成分股
-> 新浪行业成分股
-> 新浪基础行情
```

财务字段优先通过 AkShare 批量公开接口补充。公开免费源可能存在延迟、缺字段、限流或字段变更，项目会尽量保留最近一次可评分缓存，避免低质量刷新覆盖本地数据。

## AI 使用边界

AI 只做解释性备注和研究复核：

- 不参与原始评分计算。
- 不生成买入、卖出、仓位或自动交易指令。
- 不编造新闻、公告或财报。
- 只能基于输入的评分、指标、价位、风险和本地规则结果输出条件化分析。

## 本地数据与隐私

以下内容默认不会提交到 Git：

- `.env` 和任何真实 API key
- `data/cache/` 行情缓存
- `data/results/` 评分和 AI 结果
- `data/imports/` 导入文件
- `data/holdings.json` 持仓数据
- `frontend/dist/` 构建产物
- 运行日志和依赖目录

公开仓库或发 issue 前，请确认没有把个人持仓、API key 或本地缓存文件贴出来。

## 版权与使用限制

Copyright © 2026 qinge5202024. 项目名称、界面设计、筛选逻辑、文档和源码版权归作者所有。

允许：

- 个人学习、研究和自用部署。
- 非商业内部试用。
- 提交 Issue、建议和改进 PR。
- 在保留作者署名、版权声明、免责声明和禁止转售说明的前提下进行非商业二次开发。

禁止：

- 将本项目或改名后的衍生版本作为软件、课程资料、训练营赠品、会员工具、SaaS 服务或源码包进行售卖、出租、转授权或付费分发。
- 删除、隐藏或篡改作者署名、版权说明、免责声明和禁止二次出售说明。
- 使用本项目包装成投资建议、荐股服务、自动交易服务或任何承诺收益的产品。

任何商业合作、商业部署、付费分发或授权使用，必须先获得作者书面许可。

## API 摘要

```text
GET  /api/health
POST /api/import/csv
POST /api/data/refresh
POST /api/data/financial-metrics/refresh
POST /api/data/fund-flow/refresh
GET  /api/data/status
GET  /api/config
PUT  /api/config
POST /api/screen/run
GET  /api/screen/results
GET  /api/sectors/hot
GET  /api/stocks/{code}/technical-levels
GET  /api/stocks/{code}/technical-analysis
POST /api/ai/remarks
POST /api/ai/analyze-watchlist
GET  /api/holdings
PUT  /api/holdings
POST /api/holdings/analyze
```

## 免责声明

本项目仅用于学习、研究和观察，不构成任何投资建议。股市有风险，公开免费数据可能不完整、不准确或延迟。任何交易决策都应由使用者独立判断并自行承担风险。

## License

Custom Source-Available Non-Resale License. See [LICENSE](LICENSE).
