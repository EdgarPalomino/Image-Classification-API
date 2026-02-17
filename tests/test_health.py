def test_health_endpoint_basic(client):
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()

    assert "status" in data
    assert data["status"] == "healthy"


    assert "model_loaded" in data
    assert data["model_loaded"] is True