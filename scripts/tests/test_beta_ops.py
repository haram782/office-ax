import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = Path(__file__).resolve().parent


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


class BetaOpsFakeDockerExecutionTest(unittest.TestCase):
    """fake docker 실행형 테스트 — 실패 경로에서 실제 명령/종료코드/writer 복구를 관찰한다."""

    def _install_fake_binary(self, bindir: Path, src: Path, name: str) -> None:
        dest = bindir / name
        shutil.copy(src, dest)
        dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def _fake_bin_dir(self, tmp: str, with_df: bool = False) -> Path:
        bindir = Path(tmp) / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        self._install_fake_binary(bindir, TESTS_DIR / "fake_docker.sh", "docker")
        if with_df:
            self._install_fake_binary(bindir, TESTS_DIR / "fake_df.sh", "df")
        return bindir

    def _env_file(self, tmp: str) -> Path:
        env_file = Path(tmp) / ".env.beta.fake"
        env_file.write_text("DB_NAME=officeax_beta\nDB_USER=officeax\nBETA_RELEASE_TAG=deadbeef1234\n")
        return env_file

    def _base_env(self, tmp: str, log: Path, with_df: bool = False, **extra: str) -> dict:
        bindir = self._fake_bin_dir(tmp, with_df=with_df)
        env = dict(os.environ)
        env["PATH"] = f"{bindir}:{env['PATH']}"
        env["BETA_ENV_FILE"] = str(self._env_file(tmp))
        env["BETA_BACKUP_DIR"] = str(Path(tmp) / "backups")
        env["FAKE_DOCKER_LOG"] = str(log)
        env.update(extra)
        return env

    def _run_backup(self, tmp: str, log: Path, **extra: str):
        return subprocess.run(
            ["bash", str(ROOT / "scripts" / "beta_backup.sh")],
            text=True,
            capture_output=True,
            env=self._base_env(tmp, log, **extra),
            stdin=subprocess.DEVNULL,
        )

    def _run_restore(self, tmp: str, log: Path, backup_set: Path, with_df: bool = False, **extra: str):
        return subprocess.run(
            ["bash", str(ROOT / "scripts" / "beta_restore.sh"), str(backup_set), "--confirm"],
            text=True,
            capture_output=True,
            env=self._base_env(tmp, log, with_df=with_df, **extra),
            stdin=subprocess.DEVNULL,
        )

    def test_backup_succeeds_end_to_end_with_fake_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "docker.log"
            log.write_text("")
            result = self._run_backup(tmp, log)
            self.assertEqual(result.returncode, 0, result.stderr)
            sets = list((Path(tmp) / "backups").glob("backup-*"))
            self.assertEqual(len(sets), 1)
            for name in ("database.sql.gz", "media.tar.gz", "manifest.txt", "SHA256SUMS"):
                self.assertTrue((sets[0] / name).is_file(), name)
            self.assertEqual(list((Path(tmp) / "backups").glob(".partial-*")), [])

    def test_backup_pg_dump_failure_restores_writers_and_drops_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "docker.log"
            log.write_text("")
            result = self._run_backup(tmp, log, FAKE_DOCKER_FAIL="pg_dump")
            self.assertNotEqual(result.returncode, 0)
            backup_dir = Path(tmp) / "backups"
            self.assertEqual(list(backup_dir.glob("backup-*")), [])
            self.assertEqual(list(backup_dir.glob(".partial-*")), [])
            log_text = log.read_text()
            self.assertIn("start backend-web backend-worker backend-beat ax-worker", log_text)

    def test_backup_media_tar_failure_restores_writers_and_drops_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "docker.log"
            log.write_text("")
            result = self._run_backup(tmp, log, FAKE_DOCKER_FAIL="tar -C /app/backend/media -czf")
            self.assertNotEqual(result.returncode, 0)
            backup_dir = Path(tmp) / "backups"
            self.assertEqual(list(backup_dir.glob("backup-*")), [])
            self.assertEqual(list(backup_dir.glob(".partial-*")), [])
            log_text = log.read_text()
            self.assertIn("start backend-web backend-worker backend-beat ax-worker", log_text)

    def test_restore_checksum_mismatch_stops_before_destructive_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "docker.log"
            log.write_text("")
            backup_result = self._run_backup(tmp, log)
            self.assertEqual(backup_result.returncode, 0, backup_result.stderr)
            backup_set = next((Path(tmp) / "backups").glob("backup-*"))
            with (backup_set / "database.sql.gz").open("ab") as fh:
                fh.write(b"tampered-after-checksum")

            log.write_text("")
            restore_result = self._run_restore(tmp, log, backup_set)
            self.assertNotEqual(restore_result.returncode, 0)
            log_text = log.read_text()
            self.assertNotIn("dropdb", log_text)
            self.assertNotIn("createdb", log_text)

    def test_restore_corrupt_manifest_stops_before_destructive_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "docker.log"
            log.write_text("")
            backup_result = self._run_backup(tmp, log)
            self.assertEqual(backup_result.returncode, 0, backup_result.stderr)
            backup_set = next((Path(tmp) / "backups").glob("backup-*"))
            manifest = backup_set / "manifest.txt"
            manifest.write_text(manifest.read_text().replace("officeax-beta-backup-v1", "officeax-beta-backup-v0"))
            with (backup_set / "SHA256SUMS").open("w") as sums:
                subprocess.run(
                    ["shasum", "-a", "256", "database.sql.gz", "media.tar.gz", "manifest.txt"],
                    cwd=backup_set,
                    stdout=sums,
                    check=True,
                )

            log.write_text("")
            restore_result = self._run_restore(tmp, log, backup_set)
            self.assertNotEqual(restore_result.returncode, 0)
            log_text = log.read_text()
            self.assertNotIn("dropdb", log_text)
            self.assertNotIn("createdb", log_text)

    def test_restore_insufficient_disk_stops_before_destructive_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "docker.log"
            log.write_text("")
            backup_result = self._run_backup(tmp, log)
            self.assertEqual(backup_result.returncode, 0, backup_result.stderr)
            backup_set = next((Path(tmp) / "backups").glob("backup-*"))

            log.write_text("")
            restore_result = self._run_restore(
                tmp, log, backup_set, with_df=True, FAKE_DF_AVAILABLE_KB="1"
            )
            self.assertNotEqual(restore_result.returncode, 0)
            self.assertIn("disk capacity", restore_result.stdout + restore_result.stderr)
            log_text = log.read_text()
            self.assertNotIn("dropdb", log_text)
            self.assertNotIn("createdb", log_text)
            self.assertNotIn("pg_dump", log_text)

    def test_restore_rejects_symlink_entry_in_media_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "docker.log"
            log.write_text("")
            backup_result = self._run_backup(tmp, log, FAKE_MEDIA_TAR_SYMLINK="1")
            self.assertEqual(backup_result.returncode, 0, backup_result.stderr)
            backup_set = next((Path(tmp) / "backups").glob("backup-*"))

            log.write_text("")
            restore_result = self._run_restore(tmp, log, backup_set)
            self.assertNotEqual(restore_result.returncode, 0)
            self.assertIn("symlink", restore_result.stdout + restore_result.stderr)
            log_text = log.read_text()
            self.assertNotIn("dropdb", log_text)
            self.assertNotIn("createdb", log_text)

    def test_restore_succeeds_end_to_end_with_fake_docker(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "docker.log"
            log.write_text("")
            backup_result = self._run_backup(tmp, log)
            self.assertEqual(backup_result.returncode, 0, backup_result.stderr)
            backup_set = next((Path(tmp) / "backups").glob("backup-*"))

            log.write_text("")
            restore_result = self._run_restore(tmp, log, backup_set)
            self.assertEqual(restore_result.returncode, 0, restore_result.stderr)
            log_text = log.read_text()
            for expected in ("dropdb", "createdb", "showmigrations --plan", "up -d"):
                self.assertIn(expected, log_text)
            # safety backup이 destructive 단계 전에 새 complete set으로 남아야 한다.
            sets = sorted((Path(tmp) / "backups").glob("backup-*"))
            self.assertEqual(len(sets), 2)


if __name__ == "__main__":
    unittest.main()
