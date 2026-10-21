# Library API

Backend 文档的图书借阅示例服务。第 03 章只实现内存中的图书查询与创建，后续章节逐步接入数据库、事务与认证。

## 运行

```bash
uv sync
uv run uvicorn app.main:app --reload
```

服务默认监听 `http://127.0.0.1:8000`。接口文档在 `/docs`，OpenAPI 描述在 `/openapi.json`。

## 测试

```bash
uv run pytest
```

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/health` | 健康检查 |
| `GET` | `/books` | 图书列表 |
| `GET` | `/books/{book_id}` | 单本图书 |
| `POST` | `/books` | 创建图书 |

数据保存在进程内存中，重启后清空。第 07 章会把它替换为 PostgreSQL。
