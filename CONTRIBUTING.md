# Contributing

感谢你对这个项目感兴趣。这个项目定位是本地 A 股研究观察工具，欢迎提交数据源适配、评分逻辑、前端体验、测试和文档改进。

## 开发流程

1. Fork 或创建功能分支。
2. 安装依赖：

```powershell
python -m pip install -r requirements.txt
npm run frontend:install
```

3. 启动开发环境：

```powershell
npm run backend
npm run dev
```

4. 提交前运行：

```powershell
python -m unittest discover backend/tests
npm run build
```

## 提交建议

- 保持改动聚焦，一次 PR 解决一个明确问题。
- 不要提交 `.env`、API key、持仓数据、缓存行情、导入 CSV 或 AI 结果。
- 新增数据源时，请保证接口失败时能降级，不影响已有缓存和评分。
- 新增评分逻辑时，请补充单元测试，并避免输出买卖建议。
- AI 相关改动必须保持“解释性研究复核”定位，不应生成自动交易指令。

## 数据和投资风险

公开免费数据源可能变动、延迟或缺失。贡献代码时请优先考虑异常处理、缓存保护和用户提示。
