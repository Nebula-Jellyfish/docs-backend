from fastapi import FastAPI, HTTPException, Response, status
from pydantic import BaseModel, Field

app = FastAPI(title="Library API", version="0.1.0")


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    total: int = Field(gt=0)


class Book(BaseModel):
    id: int
    title: str
    total: int
    available: int


books: dict[int, Book] = {}
next_id = 1


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/books", response_model=list[Book])
def list_books() -> list[Book]:
    return list(books.values())


@app.get("/books/{book_id}", response_model=Book)
def get_book(book_id: int) -> Book:
    book = books.get(book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="book not found")
    return book


@app.post("/books", response_model=Book, status_code=status.HTTP_201_CREATED)
def create_book(payload: BookCreate, response: Response) -> Book:
    global next_id
    book = Book(id=next_id, title=payload.title, total=payload.total, available=payload.total)
    books[book.id] = book
    next_id += 1
    response.headers["Location"] = f"/books/{book.id}"
    return book
