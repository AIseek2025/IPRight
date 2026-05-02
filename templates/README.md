# IPRight 模板目录

本目录存放 Word 文档生成模板和配置文件。

## 子目录

- `manual/`：软件说明书 Word 模板
- `codebook/`：源代码文档 Word 模板

## 模板说明

当前 Word 生成采用 `python-docx` 程序化生成，模板逻辑集中在 `backend/app/services/document/` 中。
后续可扩展为基于 `.docx` 模板文件的 Jinja2 渲染方案（使用 `docxtpl`）。
