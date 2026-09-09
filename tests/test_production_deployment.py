"""Static deployment-contract tests."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TestProductionDeployment(unittest.TestCase):
    def test_compose_keeps_apps_private_and_mounts_durable_database(self) -> None:
        compose = (ROOT / "deployment/compose.yaml").read_text(encoding="utf-8")
        self.assertIn("TW_ETF_DATABASE_PATH: /data/tw_etf.db", compose)
        self.assertIn("TW_ETF_OWNER_TOKEN", compose)
        self.assertIn("RELEASE_SHA: ${RELEASE_SHA:?set RELEASE_SHA}", compose)
        self.assertNotIn('"8000:8000"', compose)
        self.assertNotIn('"8501:8501"', compose)
        self.assertIn('"443:443"', compose)
        self.assertEqual(1, compose.count("read_only: false"))
        self.assertEqual(3, compose.count("read_only: true"))
        self.assertEqual(3, compose.count("no-new-privileges:true"))
        self.assertEqual(3, compose.count("- ALL"))
        self.assertIn("NET_BIND_SERVICE", compose)
        self.assertIn("pids_limit: 256", compose)

    def test_all_runtime_images_are_pinned_and_non_root(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        caddyfile = (ROOT / "deployment/Caddy.Dockerfile").read_text(
            encoding="utf-8"
        )
        compose = (ROOT / "deployment/compose.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("FROM python:3.13.14-slim", dockerfile)
        self.assertIn("apt-get upgrade --yes", dockerfile)
        self.assertIn("USER appuser", dockerfile)
        self.assertIn("FROM golang:1.27.0-alpine3.24 AS builder", caddyfile)
        self.assertIn("FROM alpine:3.24", caddyfile)
        self.assertIn(
            "CADDY_COMMIT=8ec11a4b7e39a5fd00da2fc5cb9b543e31fd7926",
            caddyfile,
        )
        self.assertIn("golang.org/x/crypto@v0.55.0", caddyfile)
        self.assertIn("golang.org/x/net@v0.58.0", caddyfile)
        self.assertIn("golang.org/x/text@v0.41.0", caddyfile)
        self.assertIn("google.golang.org/grpc@v1.83.2", caddyfile)
        self.assertIn("USER 10001:10001", caddyfile)
        self.assertNotIn("image: caddy:", compose)

    def test_proxy_blocks_api_docs_and_sets_edge_boundaries(self) -> None:
        caddyfile = (ROOT / "deployment/Caddyfile").read_text(
            encoding="utf-8"
        )
        self.assertIn("max_size 64KB", caddyfile)
        self.assertIn("respond @api_docs 404", caddyfile)
        self.assertIn("X-Frame-Options \"DENY\"", caddyfile)
        self.assertIn("Content-Security-Policy", caddyfile)
        self.assertIn("Permissions-Policy", caddyfile)
        self.assertIn('X-Release-Sha "{$RELEASE_SHA}"', caddyfile)
        backend_matcher = next(
            line for line in caddyfile.splitlines() if line.strip().startswith(
                "@backend path"
            )
        )
        self.assertNotIn("/docs", backend_matcher)
        self.assertNotIn("/openapi.json", backend_matcher)

        workflow = (ROOT / ".github/workflows/security.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("caddy validate", workflow)
        self.assertIn('RELEASE_SHA="$GITHUB_SHA"', workflow)
        self.assertIn("--tmpfs /data:rw,noexec,nosuid", workflow)

    def test_secrets_are_ignored_and_example_is_placeholder(self) -> None:
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        example = (ROOT / "deployment/.env.example").read_text(encoding="utf-8")
        self.assertIn("deployment/.env", ignore)
        self.assertIn("replace-with", example)
        self.assertNotIn("correct-owner-token", example)

    def test_docker_context_is_allowlisted_to_runtime_source(self) -> None:
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn("**\n", dockerignore)
        self.assertIn("!requirements.lock", dockerignore)
        self.assertIn("!backend/**", dockerignore)
        self.assertIn("!frontend/**", dockerignore)
        self.assertNotIn("!database/", dockerignore)
        self.assertNotIn("!deployment/", dockerignore)

    def test_locked_versions_match_verified_environment(self) -> None:
        locked = (ROOT / "requirements.lock").read_text(encoding="utf-8")
        self.assertIn("fastapi[standard]==0.140.7", locked)
        self.assertIn("streamlit==1.60.0", locked)


if __name__ == "__main__":
    unittest.main()
