# 03丨第一个 FastAPI 服务

第 02 章给出了接口契约，本章把它落成一个可以启动的 FastAPI 工程。先创建项目与依赖，再注册健康检查与图书查询路由，接着用 Pydantic 模型接收正文、用状态码与异常表达结果，最后打开自动生成的接口文档并补上测试。读完之后应当得到一个能在本机运行、能用 curl 调用、能用 pytest 验证的最小服务。

---

## 工程创建

工程的起点是一个声明依赖的 `pyproject.toml` 和一个存放应用代码的包。依赖、Python 版本与测试配置都写在同一个文件里，安装与运行由 `uv` 读取这些声明完成。

### 依赖与目录

**uv** 是 Python 的包与项目管理工具，它读取 `pyproject.toml`，创建虚拟环境、安装依赖并锁定版本。下面的文件声明运行依赖与测试依赖；`fastapi` 提供 Web 框架，`pydantic` 负责数据校验，`uvicorn` 提供 HTTP 服务器，`httpx` 与 `pytest` 只用于测试。

```toml
[project]
name = "library-api"
version = "0.1.0"
description = "Backend 文档的图书借阅示例服务"
requires-python = ">=3.12"
dependencies = [
    "fastapi==0.115.14",
    "pydantic==2.14.1",
    "uvicorn[standard]==0.30.6",
]

[dependency-groups]
dev = [
    "httpx==0.27.2",
    "pytest==8.4.2",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

`dependencies` 是运行服务所需的包，`dependency-groups.dev` 只在本机开发与测试时安装；`requires-python` 限定解释器版本，避免在过旧的 Python 上安装出不兼容的包。`[tool.pytest.ini_options]` 告诉 pytest 去 `tests` 目录收集测试，并把项目根目录加入导入路径，使 `from app import main` 可以正常工作。

工程按下面的结构组织。`app` 是应用包，`main.py` 存放应用对象与路由，`tests` 存放测试；`.venv` 与 `uv.lock` 由 uv 生成，前者不提交，后者记录解析出的精确版本。

```text
library-api/
    pyproject.toml
    README.md
    uv.lock
    app/
        __init__.py
        main.py
    scripts/
        openapi_probe.py
    tests/
        test_books.py
```

创建目录后，在项目根目录执行 `uv sync`，uv 会创建 `.venv` 并安装上面列出的依赖。`uv run` 在该虚拟环境中执行命令，因此不需要手动激活环境；后面的 `uv run uvicorn`、`uv run pytest` 都基于同一套依赖。

### 应用对象

FastAPI 应用由一个模块级对象表示，服务器通过「模块路径 + 对象名」找到它。下面的语句创建应用对象，并把标题与版本写进接口文档；`app` 这个名字由 `uvicorn` 的启动参数引用。

```python
app = FastAPI(title="Library API", version="0.1.0")
```

`FastAPI()` 的 `title` 与 `version` 不是业务数据，它们只出现在 `/openapi.json` 与 `/docs` 页面中，帮助调用方识别服务。应用对象本身不监听端口，监听由 Uvicorn 完成；`uvicorn app.main:app` 的含义是导入 `app.main` 模块，取出其中的 `app` 对象。

### 数据模型

模型用 Pydantic 的 `BaseModel` 定义，字段写成带类型的类属性。**Pydantic** 是 FastAPI 依赖的数据校验库，它在创建模型实例时按字段类型转换并检查数据；类型不匹配或约束不满足时抛出校验错误，FastAPI 再把错误转成 `422` 响应。

图书的响应模型包含编号、书名、总册数与可借册数。四个字段都是必需的，`id` 与 `available` 由服务维护，客户端不能直接写入。

```python
class Book(BaseModel):
    id: int
    title: str
    total: int
    available: int
```

`Book` 用来描述服务返回的完整资源。`response_model=Book` 会让 FastAPI 按这个模型过滤响应字段并生成文档；即使处理函数返回了额外的内部字段，响应中也只保留模型声明的四个字段。

创建请求的模型与响应模型分开，因为客户端提交的字段少于服务返回的字段。下面的 `BookCreate` 只接收书名与总册数，并用 `Field` 给它们加上约束。

```python
class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    total: int = Field(gt=0)
```

`Field` 给字段附加校验规则：`min_length` 与 `max_length` 限制字符串长度，`gt=0` 要求整数大于零。把 `BookCreate` 与 `Book` 分开，可以避免客户端通过请求正文写入 `id` 或 `available`；这两个字段由服务在创建时生成，不在请求模型中声明。

当前实现把图书放在模块级字典中，编号由另一个模块级变量生成。两个声明在导入模块时执行，所有请求共享同一份数据。

```python
books: dict[int, Book] = {}
next_id = 1
```

`books` 以编号为键保存 `Book` 对象，`next_id` 是下一本图书的编号。数据只存在于进程内存，重启后清空；第 07 章会用数据库替换这两个变量。

---

## 路由与路径参数

路由把请求的方法与路径映射到处理函数。装饰器 `@app.get(...)` 把下一行的函数注册到应用对象，FastAPI 在启动时读取函数签名，决定参数从哪里来、返回值怎样序列化。

### 注册读取路由

健康检查不访问数据，只返回服务是否可用。下面的处理函数注册到 `GET /health`，返回一个字典；FastAPI 把字典序列化成 JSON，并设置 `Content-Type: application/json`。

```python
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

`@app.get("/health")` 是装饰器，它在导入模块时执行，把 `health` 函数登记到 `/health` 路径。函数返回的字典不是完整的 HTTP 响应，FastAPI 负责把它转成状态码 `200`、JSON 正文与相应首部；返回值类型 `dict[str, str]` 同时用于生成接口文档。

启动服务后，用 `curl` 请求健康检查。`-s` 关闭进度输出，`-i` 让响应首部一起显示；Windows PowerShell 中命令名写作 `curl.exe`，Linux 与 macOS 中写作 `curl`。

```text
$ curl.exe -s -i http://127.0.0.1:8000/health
HTTP/1.1 200 OK
server: uvicorn
content-length: 15
content-type: application/json

{"status":"ok"}
```

响应首部中的 `content-type` 说明正文是 JSON，`content-length` 是正文字节数；正文 `{"status":"ok"}` 与处理函数返回的字典一致。`date` 等首部随运行时间变化，示例中省略，不影响对结果的判断。

### 集合路由

查询图书列表的处理函数注册到 `GET /books`，返回内存字典中的所有值。`response_model=list[Book]` 告诉 FastAPI 响应是 `Book` 的数组，框架据此生成文档并校验返回结构。

```python
@app.get("/books", response_model=list[Book])
def list_books() -> list[Book]:
    return list(books.values())
```

`list(books.values())` 把字典中的值复制成列表，避免把字典视图直接交给序列化器；返回空字典时得到空数组 `[]`，而不是 `null`。列表顺序是字典的插入顺序，当前实现没有排序参数，第 09 章会在数据库查询中处理排序与分页。

### 路径参数

路径中的花括号表示参数，函数签名中的同名参数接收它的值。下面的处理函数从路径读取 `book_id`，按编号查找图书；类型标注 `int` 让 FastAPI 在调用函数前完成转换，传入非整数时直接返回 `422`，不会进入函数体。找不到图书时抛出 `HTTPException`，它是 FastAPI 提供的异常类型，携带状态码与 `detail`，框架捕获后转成 JSON 响应；状态码使用 `status` 模块的常量，避免在代码中直接写数字。

```python
@app.get("/books/{book_id}", response_model=Book)
def get_book(book_id: int) -> Book:
    book = books.get(book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="book not found")
    return book
```

`books.get(book_id)` 找不到时返回 `None`，代码随即抛出 `HTTPException`，异常之后的语句不会执行。编号存在时直接返回 `Book`，`response_model` 负责生成响应结构。

先创建一本图书，再按编号读取。下面的命令把 JSON 正文放在 `book.json` 中，用 `--data-binary @book.json` 发送，避免不同 shell 对引号的处理差异。

```text
$ curl.exe -s -i -X POST http://127.0.0.1:8000/books \
    -H "Content-Type: application/json" \
    --data-binary @book.json
HTTP/1.1 201 Created
server: uvicorn
content-length: 59
content-type: application/json
location: /books/1

{"id":1,"title":"Effective Python","total":3,"available":3}
```

状态码 `201` 表示资源已创建，`location` 首部给出新资源的路径，正文返回服务生成的编号、书名、总册数与可借册数。`book.json` 的内容是 `{"title":"Effective Python","total":3}`；服务把 `total` 复制到 `available`，因为新入库的图书全部可借。

按编号读取刚创建的图书，响应正文与创建时相同。下面的请求直接使用路径 `/books/1`，服务从内存字典中取出对应对象。

```text
$ curl.exe -s -i http://127.0.0.1:8000/books/1
HTTP/1.1 200 OK
server: uvicorn
content-length: 59
content-type: application/json

{"id":1,"title":"Effective Python","total":3,"available":3}
```

请求成功时返回 `200` 与完整资源；编号不存在时返回 `404`。下面的请求访问一个未创建的编号，服务返回 `HTTPException` 生成的状态码与 `detail`。

```text
$ curl.exe -s -i http://127.0.0.1:8000/books/999
HTTP/1.1 404 Not Found
server: uvicorn
content-length: 27
content-type: application/json

{"detail":"book not found"}
```

`404` 表示资源不存在，正文中的 `detail` 来自 `HTTPException` 的参数。错误正文的字段名由框架决定，当前是 `detail`；第 11 章会把错误响应统一成第 02 章约定的 `application/problem+json` 结构，本章先保留框架默认形式。

---

## 请求正文与校验

创建资源时，客户端把数据放在请求正文中，`Content-Type` 说明格式。FastAPI 根据处理函数参数的类型找到 `BookCreate` 模型，读取 JSON、创建模型实例并执行字段校验；校验通过后才调用函数体。

### 创建资源

下面的处理函数接收 `BookCreate` 与 `Response` 两个参数。`payload` 来自请求正文，`response` 是 FastAPI 注入的响应对象，用来在返回前设置 `Location` 首部；`status_code` 声明成功时的状态码为 `201`。

```python
@app.post("/books", response_model=Book, status_code=status.HTTP_201_CREATED)
def create_book(payload: BookCreate, response: Response) -> Book:
    global next_id
    book = Book(id=next_id, title=payload.title, total=payload.total, available=payload.total)
    books[book.id] = book
    next_id += 1
    response.headers["Location"] = f"/books/{book.id}"
    return book
```

`payload.title` 与 `payload.total` 已经过 Pydantic 校验，函数体不需要再判断类型或范围。`global next_id` 声明修改模块级变量，`book` 存入 `books` 后编号加一；`response.headers["Location"]` 写入新资源路径。当前实现没有加锁，两个请求同时创建时可能拿到相同编号，这一限制在本章末尾说明，第 08 章会用数据库事务解决。

如果正文不满足约束，FastAPI 在调用函数前返回 `422`，函数体不会执行。下面的请求把书名设为空串、总册数设为零，服务返回两条字段错误。

```text
$ curl.exe -s -i -X POST http://127.0.0.1:8000/books \
    -H "Content-Type: application/json" \
    --data-binary @bad_book.json
HTTP/1.1 422 Unprocessable Content
server: uvicorn
content-length: 256
content-type: application/json

{"detail":[{"type":"string_too_short","loc":["body","title"],"msg":"String should have at least 1 character","input":"","ctx":{"min_length":1}},{"type":"greater_than","loc":["body","total"],"msg":"Input should be greater than 0","input":0,"ctx":{"gt":0}}]}
```

`detail` 是错误数组，`loc` 指出出错位置：`["body","title"]` 表示请求正文的 `title` 字段，`["body","total"]` 表示 `total` 字段。`type` 是校验错误的内部名称，`msg` 是英文说明，`ctx` 给出约束值。状态码 `422` 表示正文语法正确，但字段不满足业务规则；原因短语在不同服务器版本中可能是 `Unprocessable Entity` 或 `Unprocessable Content`，判断以状态码为准。如果 JSON 本身无法解析，FastAPI 返回 `400` 或 `422`，具体取决于解析失败的阶段。

---

## 接口文档与调试

FastAPI 从路由、类型标注与 Pydantic 模型自动生成 OpenAPI 描述，并提供两个页面读取它。`/docs` 是 Swagger UI，可以直接在浏览器里填写参数、发送请求；`/redoc` 是只读文档；`/openapi.json` 是机器可读的描述文件。

启动服务后打开 `http://127.0.0.1:8000/docs`，可以看到 `GET /health`、`GET /books`、`GET /books/{book_id}` 与 `POST /books` 四组接口。展开 `POST /books`，页面会根据 `BookCreate` 生成请求体示例与字段约束；点击「Try it out」填写正文，可以直接看到本章前面用 curl 得到的响应。

`/openapi.json` 中的 `info` 记录应用标题与版本，`paths` 列出所有路由。项目中的 `scripts/openapi_probe.py` 读取该文件并打印这两个部分，省略了模型定义与参数细节；输出说明文档内容来自应用对象与处理函数的声明，而不是另写的一份配置。

```text
$ uv run python scripts/openapi_probe.py
200
{
  "title": "Library API",
  "version": "0.1.0"
}
['/books', '/books/{book_id}', '/health']
```

开发阶段用 `uv run uvicorn app.main:app --reload --port 8000` 启动，`--reload` 监听源码变化，保存文件后自动重启进程。重启会清空内存中的 `books`，已创建的记录随之丢失；这是当前实现的限制，不是 FastAPI 的行为。

---

## 测试

测试直接调用应用对象，不经过真实端口。FastAPI 的 **TestClient** 包装了应用，提供与 `httpx` 相同的 `get()`、`post()` 方法；请求在进程内完成，速度比启动服务器快，也不会占用端口。

测试文件顶部先导入应用对象并创建客户端，`TestClient` 的构造参数是应用对象，而不是模块路径。客户端创建一次即可复用，后续测试函数共享同一个实例。

```python
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)
```

`from app import main` 导入应用模块，`main.app` 是第 01 节创建的应用对象；`client` 把请求直接交给它。下面的测试创建一个图书，检查状态码、`Location` 首部与响应正文，再按编号读取并确认两次结果一致。

```python
def test_create_and_get_book() -> None:
    created = client.post("/books", json={"title": "Effective Python", "total": 3})
    assert created.status_code == 201
    assert created.headers["location"] == "/books/1"
    assert created.json() == {
        "id": 1,
        "title": "Effective Python",
        "total": 3,
        "available": 3,
    }

    fetched = client.get("/books/1")
    assert fetched.status_code == 200
    assert fetched.json() == created.json()
```

`client.post()` 的 `json=` 参数把字典序列化成 JSON，并设置 `Content-Type`；`created.json()` 把响应正文解析回字典。第二个请求验证创建后的资源可读，两个响应相等说明服务没有在读取时改变字段。完整测试还覆盖列表、`404` 与校验失败，并用自动启用的 fixture 在每个测试前清空 `books`、重置 `next_id`，避免测试之间互相影响。

在项目根目录运行测试，`-q` 减少输出，`-p no:warnings` 关闭与本节无关的依赖弃用警告。五个测试全部通过时输出如下。

```text
$ uv run pytest -q -p no:warnings
.....                                                                    [100%]
5 passed in 0.21s
```

测试覆盖健康检查、创建后读取、列表、资源不存在与字段校验五条路径。通过测试只说明这些路径符合当前契约，不说明并发安全；创建图书的编号生成与写入没有原子性保证，下一节说明这一边界。

---

## 当前实现的边界

当前服务把数据放在模块级字典中，进程重启后全部丢失；`uvicorn --workers 2` 会启动两个独立进程，各自持有一份字典，同一个编号可能在不同进程中指向不同图书。字典适合验证 HTTP 层与校验逻辑，不适合作为持久化方案。

并发写入也没有保护。`next_id` 的读取、加一与赋值分成多步，两个请求交错执行时可能得到同一个编号，后写入的记录会覆盖先写入的记录。数据库通过主键、唯一约束与事务提供原子性，第 07 章接入 PostgreSQL 后，这一节列出的限制会逐个消失。

---

## 小结

FastAPI 应用由 `FastAPI` 对象、路由处理函数与 Pydantic 模型组成。装饰器把方法与路径绑定到函数，路径参数按类型转换，请求正文按模型校验；返回值由 `response_model` 过滤并序列化，`HTTPException` 把业务失败转成带状态码的 JSON 响应。OpenAPI 文档与 Swagger UI 从这些声明自动生成，测试通过 `TestClient` 在进程内调用应用。

本章的服务只把数据放在内存中，重启与多进程都会破坏状态一致性。下一章回到网络层，说明 TCP 连接、阻塞与消息边界，为后面理解数据库连接与并发模型打基础。
