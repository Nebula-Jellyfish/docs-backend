import pytest
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def reset_store() -> None:
    main.books.clear()
    main.next_id = 1


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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


def test_list_books() -> None:
    client.post("/books", json={"title": "Effective Python", "total": 3})
    client.post("/books", json={"title": "Fluent Python", "total": 2})

    response = client.get("/books")
    assert response.status_code == 200
    assert [book["title"] for book in response.json()] == ["Effective Python", "Fluent Python"]


def test_not_found() -> None:
    response = client.get("/books/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "book not found"}


def test_validation_error() -> None:
    response = client.post("/books", json={"title": "", "total": 0})
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert {error["loc"][-1] for error in errors} == {"title", "total"}
