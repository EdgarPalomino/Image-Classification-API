from pathlib import Path


def test_predict_with_bus_image(client):
    """
    Send a valid JPEG image (bus.jpg) to /predict
    and expect a 200 + non-empty predictions list.
    """

    project_root = Path(__file__).resolve().parents[1]
    image_path = project_root / "images" / "bus.jpg"

    assert image_path.exists(), f"Test image not found: {image_path}"

    with image_path.open("rb") as f:
        files = {
            "file": ("bus.jpg", f, "image/jpeg"),
        }
        response = client.post("/predict", files=files)

    assert response.status_code == 200

    data = response.json()

    assert "predictions" in data
    assert isinstance(data["predictions"], list)
    assert len(data["predictions"]) > 0