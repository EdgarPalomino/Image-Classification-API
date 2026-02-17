def test_predict_with_invalid_file_type(client):
    """
    Send a non-image file to /predict and expect a 4xx error,
    not a 500 internal error.
    """
    fake_content = b"this is not an image at all"

    files = {
        "file": ("not_image.txt", fake_content, "text/plain"),
    }

    response = client.post("/predict", files=files)


    assert response.status_code in (400, 415, 422)

    data = response.json()

    assert isinstance(data, dict)
    assert "detail" in data