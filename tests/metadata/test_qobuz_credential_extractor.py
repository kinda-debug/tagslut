from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from tagslut.metadata.qobuz_credential_extractor import extract_qobuz_credentials


class _Resp:
    def __init__(self, *, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_extract_qobuz_credentials_parses_html_and_js() -> None:
    html = '<html><script src="/static/js/app.bundle.js"></script></html>'
    # Use direct extraction format (production:{api:{appId:"...",appSecret:"..."}})
    js = 'production:{api:{appId:"123456789",appSecret:"abcdef1234567890abcdef1234567890"}'

    get_mock = Mock(side_effect=[_Resp(text=html), _Resp(text=js)])
    with patch("tagslut.metadata.qobuz_credential_extractor.requests.get", get_mock):
        creds = extract_qobuz_credentials()

    assert creds["app_id"] == "123456789"
    assert creds["app_secret"] == "abcdef1234567890abcdef1234567890"
    assert get_mock.call_args_list[0].args[0] == "https://play.qobuz.com/login"
    assert get_mock.call_args_list[1].args[0].endswith("/static/js/app.bundle.js")


def test_extract_qobuz_credentials_raises_when_bundle_missing() -> None:
    get_mock = Mock(return_value=_Resp(text="<html>no bundle here</html>"))
    with patch("tagslut.metadata.qobuz_credential_extractor.requests.get", get_mock):
        with pytest.raises(RuntimeError, match="bundle\\.js"):
            extract_qobuz_credentials()
