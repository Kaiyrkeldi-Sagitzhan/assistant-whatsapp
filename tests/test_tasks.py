
def test_create_task(client):
    """Test creating a task via API."""
    import uuid

    user_id = uuid.uuid4()
    payload = {
        "user_id": str(user_id),
        "title": "Test task",
        "description": "Test description",
        "priority": "high",
    }

    response = client.post("/tasks", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test task"
    assert data["priority"] == "high"


def test_list_open_tasks(client):
    """Test listing open tasks."""
    import uuid

    user_id = uuid.uuid4()
    response = client.get(f"/tasks/open/{user_id}")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
