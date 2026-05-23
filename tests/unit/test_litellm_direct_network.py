from __future__ import annotations

import os
import subprocess
import sys


def test_litellm_import_uses_local_cost_map_when_proxy_env_is_set() -> None:
    env = dict(os.environ)
    env["ALL_PROXY"] = "socks5://127.0.0.1:7897"
    env["HTTPS_PROXY"] = "http://127.0.0.1:7897"
    env["HTTP_PROXY"] = "http://127.0.0.1:7897"
    env.pop("LITELLM_LOCAL_MODEL_COST_MAP", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from wolven_hunt.llm.provider import _litellm_module;"
                "litellm=_litellm_module();"
                "import os;"
                "print(os.environ['LITELLM_LOCAL_MODEL_COST_MAP']);"
                "print(getattr(litellm.client_session, '_trust_env', None));"
                "print(getattr(litellm.aclient_session, '_trust_env', None))"
            ),
        ],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "socksio" not in result.stderr.lower()
    assert result.stdout.splitlines() == ["true", "False", "False"]
