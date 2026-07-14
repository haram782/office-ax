import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class BetaOpsStaticContractTest(unittest.TestCase):
    def test_required_scripts_exist_and_are_syntax_valid(self):
        for name in ("beta_backup.sh", "beta_restore.sh", "beta_preflight.sh", "beta_deploy.sh", "beta_rollback.sh"):
            script = ROOT / "scripts" / name
            self.assertTrue(script.is_file(), name)
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_scripts_pin_beta_compose_inputs(self):
        for name in ("beta_backup.sh", "beta_restore.sh", "beta_preflight.sh", "beta_deploy.sh", "beta_rollback.sh"):
            text = (ROOT / "scripts" / name).read_text()
            self.assertIn("docker-compose.beta.yml", text, name)
            self.assertIn(".env.beta", text, name)
            self.assertIn("--project-directory", text, name)

    def test_compose_contract(self):
        text = (ROOT / "docker-compose.beta.yml").read_text()
        self.assertNotIn("python manage.py migrate --noinput &&", text)
        self.assertIn("${BETA_RELEASE_TAG:?}", text)
        for service in ("backend-web", "backend-worker", "ax-worker", "nginx"):
            block = re.search(rf"^  {service}:.*?(?=^  [a-z][a-z0-9-]*:|^volumes:)", text, re.M | re.S).group(0)
            self.assertIn("healthcheck:", block, service)
            self.assertIn("mem_limit:", block, service)
            self.assertIn("cpus:", block, service)
            self.assertIn("logging:", block, service)

    def test_nginx_media_is_internal_only(self):
        text = (ROOT / "infra/nginx/beta.conf").read_text()
        self.assertRegex(text, r"location /media/\s*\{[^}]*proxy_pass")
        self.assertRegex(text, r"location /_protected_media/\s*\{[^}]*internal;")

    def test_preflight_rejects_example_placeholders_without_leaking_values(self):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts" / "beta_preflight.sh"), "--env-file", str(ROOT / ".env.beta.example"), "--static-only"],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertNotIn("change-me-to-a-long-random-string", combined)
        self.assertIn("DJANGO_SECRET_KEY", combined)

    def test_restore_requires_confirmation_before_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                ["bash", str(ROOT / "scripts" / "beta_restore.sh"), tmp],
                text=True,
                capture_output=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--confirm", result.stdout + result.stderr)

    def test_backup_and_restore_are_complete_ordered_units(self):
        backup = (ROOT / "scripts" / "beta_backup.sh").read_text()
        for contract in ("database.sql.gz", "media.tar.gz", "manifest.txt", "SHA256SUMS", ".partial-"):
            self.assertIn(contract, backup)
        self.assertLess(backup.index("compose stop"), backup.index("pg_dump"))
        restore = (ROOT / "scripts" / "beta_restore.sh").read_text()
        ordered = ["shasum -a 256 -c", "beta_backup.sh", "compose stop", "dropdb", "gzip -dc \"$BACKUP_SET/media.tar.gz\"", "showmigrations", "compose up"]
        positions = [restore.index(item) for item in ordered]
        self.assertEqual(positions, sorted(positions))

    def test_deploy_and_rollback_require_explicit_release_state(self):
        deploy = (ROOT / "scripts" / "beta_deploy.sh").read_text()
        self.assertLess(deploy.index("beta_backup.sh"), deploy.index("manage.py migrate"))
        self.assertLess(deploy.index("beta_backup.sh"), deploy.index('export BETA_RELEASE_TAG="$RELEASE_TAG"'))
        self.assertIn("check --deploy", deploy)
        self.assertIn(".releases", deploy)
        rollback = (ROOT / "scripts" / "beta_rollback.sh").read_text()
        self.assertIn("--confirm-compatible", rollback)
        self.assertIn("beta_restore.sh", rollback)


if __name__ == "__main__":
    unittest.main()
