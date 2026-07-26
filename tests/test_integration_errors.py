import httpx

from astromesh.integrations import errors


def test_401_and_403_are_credential_invalid():
    assert errors.classify_status(401) == errors.CREDENTIAL_INVALID
    assert errors.classify_status(403) == errors.CREDENTIAL_INVALID


def test_429_is_rate_limited():
    assert errors.classify_status(429) == errors.RATE_LIMITED


def test_408_and_5xx_are_upstream():
    assert errors.classify_status(408) == errors.UPSTREAM_ERROR
    assert errors.classify_status(500) == errors.UPSTREAM_ERROR
    assert errors.classify_status(503) == errors.UPSTREAM_ERROR


def test_other_4xx_is_bad_request():
    assert errors.classify_status(400) == errors.BAD_REQUEST
    assert errors.classify_status(404) == errors.BAD_REQUEST
    assert errors.classify_status(422) == errors.BAD_REQUEST


def test_timeout_and_network_are_upstream():
    assert errors.classify_exception(httpx.ConnectTimeout("t")) == errors.UPSTREAM_ERROR
    assert errors.classify_exception(httpx.ConnectError("c")) == errors.UPSTREAM_ERROR


def test_unknown_exception_is_upstream():
    assert errors.classify_exception(RuntimeError("boom")) == errors.UPSTREAM_ERROR


def test_retry_after_numeric_seconds():
    assert errors.retry_after_seconds({"Retry-After": "30"}) == 30.0


def test_retry_after_is_case_insensitive():
    assert errors.retry_after_seconds({"retry-after": "12"}) == 12.0


def test_retry_after_absent_or_unparseable():
    assert errors.retry_after_seconds({}) is None
    assert errors.retry_after_seconds({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}) is None
