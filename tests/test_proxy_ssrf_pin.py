import os

import responses


@responses.activate
def test_absolute_url_path_is_rejected(client, mocker):
    """A client-supplied absolute URL in the path must not be fetched."""
    mocked_target_base = "http://fake-target-pin/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {}, clear=True)

    responses.add(
        responses.GET,
        f"{mocked_target_base}v1/models",
        json={"upstream": "ok"},
        status=200,
    )

    # The merge_slashes redirect (308) is followed by the client; the
    # collapsed path still parses as an absolute URL in urljoin.
    proxy_response = client.get(
        "/http://127.0.0.1:9002/secret",
        headers={"Authorization": "Bearer CALLER-KEY-123"},
        follow_redirects=True,
    )

    assert proxy_response.status_code == 400
    assert len(responses.calls) == 0


@responses.activate
def test_foreign_redirect_is_not_followed(client, mocker):
    """An upstream redirect off the target host is returned, not fetched."""
    mocked_target_base = "http://fake-target-pin/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {}, clear=True)

    responses.add(
        responses.GET,
        f"{mocked_target_base}redir",
        status=302,
        headers={"Location": "http://127.0.0.1:9002/secret"},
    )

    proxy_response = client.get("/redir")

    assert proxy_response.status_code == 302
    assert proxy_response.headers.get("Location") == "http://127.0.0.1:9002/secret"
    assert len(responses.calls) == 1


@responses.activate
def test_same_host_redirect_is_followed(client, mocker):
    """A redirect staying on the target host still works."""
    mocked_target_base = "http://fake-target-pin/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {}, clear=True)

    responses.add(
        responses.GET,
        f"{mocked_target_base}redir-same",
        status=302,
        headers={"Location": f"{mocked_target_base}v1/models"},
    )
    responses.add(
        responses.GET,
        f"{mocked_target_base}v1/models",
        json={"upstream": "ok"},
        status=200,
    )

    proxy_response = client.get("/redir-same")

    assert proxy_response.status_code == 200
    assert proxy_response.json == {"upstream": "ok"}
    assert len(responses.calls) == 2


@responses.activate
def test_normal_path_still_works(client, mocker):
    """Ordinary proxied paths are unaffected by the pin."""
    mocked_target_base = "http://fake-target-pin/"
    mocker.patch('cot_proxy.TARGET_BASE_URL', mocked_target_base)
    mocker.patch.dict(os.environ, {}, clear=True)

    responses.add(
        responses.GET,
        f"{mocked_target_base}v1/models",
        json={"upstream": "ok"},
        status=200,
    )

    proxy_response = client.get("/v1/models")

    assert proxy_response.status_code == 200
    assert proxy_response.json == {"upstream": "ok"}
    assert len(responses.calls) == 1
