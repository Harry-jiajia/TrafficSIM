from typing import cast

from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QNetworkReply
from ui.api_client.rest_client import RestApiClient


class _RawResponse:
    def __init__(self, value: bytes) -> None:
        self._value = value

    def data(self) -> bytes:
        return self._value


class _FakeReply:
    def __init__(self, raw: bytes, error: QNetworkReply.NetworkError) -> None:
        self._raw = raw
        self._error = error
        self.deleted = False

    def readAll(self) -> _RawResponse:
        return _RawResponse(self._raw)

    def error(self) -> QNetworkReply.NetworkError:
        return self._error

    def errorString(self) -> str:
        return "server replied: Service Unavailable"

    def deleteLater(self) -> None:
        self.deleted = True


def test_readiness_503_is_delivered_as_structured_status_not_network_failure() -> None:
    QCoreApplication.instance() or QCoreApplication([])
    client = RestApiClient("http://127.0.0.1:8000")
    succeeded: list[tuple[str, object]] = []
    failed: list[tuple[str, str]] = []
    client.request_succeeded.connect(
        lambda operation, payload: succeeded.append((operation, payload))
    )
    client.request_failed.connect(lambda operation, message: failed.append((operation, message)))
    reply = _FakeReply(
        (
            b'{"ready":false,"components":[{"component":"carla","status":"DEGRADED",'
            b'"required":true,"message":"validation deferred"}]}'
        ),
        QNetworkReply.NetworkError.ServiceUnavailableError,
    )

    client._finish("ready", cast("QNetworkReply", reply))

    assert succeeded == [
        (
            "ready",
            {
                "ready": False,
                "components": [
                    {
                        "component": "carla",
                        "status": "DEGRADED",
                        "required": True,
                        "message": "validation deferred",
                    }
                ],
            },
        )
    ]
    assert failed == []
    assert reply.deleted
