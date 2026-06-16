from __future__ import annotations


class CodexAppCdpError(RuntimeError):
    pass


class CodexAppCdpConnectionError(CodexAppCdpError):
    pass


class CodexAppCdpDiscoveryError(CodexAppCdpError):
    pass


class CodexAppCdpEvaluationError(CodexAppCdpError):
    pass


class CodexAppCdpProtocolError(CodexAppCdpError):
    pass
