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

    def test_nginx_healthcheck_uses_ipv4_localhost(self):
        # Alpine wget이 "localhost"를 ::1로 먼저 풀면 IPv4만 listen하는 nginx가 연결을 거부한다.
        text = (ROOT / "docker-compose.beta.yml").read_text()
        block = re.search(r"^  nginx:.*?(?=^  [a-z][a-z0-9-]*:|^volumes:)", text, re.M | re.S).group(0)
        self.assertIn("http://127.0.0.1/healthz", block)
        self.assertNotIn("http://localhost/healthz", block)

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

    def test_restore_media_extraction_is_single_gzip_layer(self):
        # gzip -dc가 이미 압축을 해제하므로 뒤의 tar는 -xzf가 아니라 -xf여야 한다.
        # -xzf로 다시 쓰면 이중 gzip 해제를 시도해 media 복원이 항상 실패한다.
        restore = (ROOT / "scripts" / "beta_restore.sh").read_text()
        self.assertIn("tar -C /app/backend/media -xf -", restore)
        self.assertNotIn("tar -C /app/backend/media -xzf -", restore)

    def test_restore_media_extraction_command_handles_real_gzip_tar_stream(self):
        # fake docker가 아니라 실제 gzip/tar 바이너리로 스크립트가 사용하는 파이프라인
        # (gzip -dc | tar -xf -) 자체가 실제 아카이브를 정상 복원하는지 검증한다.
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            (src / "file.txt").write_text("fake-media")
            archive = Path(tmp) / "media.tar.gz"
            subprocess.run(
                f"tar -C {src} -cf - . | gzip -9 > {archive}",
                shell=True,
                check=True,
            )
            dest = Path(tmp) / "dest"
            dest.mkdir()
            result = subprocess.run(
                f"gzip -dc {archive} | tar -C {dest} -xf -",
                shell=True,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((dest / "file.txt").read_text(), "fake-media")

    def test_restore_fail_closed_after_destructive_step_does_not_restart_writers(self):
        # writer 정지(destructive 단계) 이후 실패하면 자동 재기동하지 않고
        # safety_set/target/복구 지침을 명확히 출력해야 한다.
        restore = (ROOT / "scripts" / "beta_restore.sh").read_text()
        self.assertIn("DESTRUCTIVE_STARTED=1", restore)
        self.assertIn("trap on_exit EXIT", restore)
        self.assertIn("safety backup:", restore)
        self.assertIn("restore target:", restore)
        self.assertLess(restore.index("DESTRUCTIVE_STARTED=1"), restore.index("compose stop -t 60"))
        self.assertNotIn("compose start", restore)

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

    def test_restore_failure_after_destructive_step_stays_fail_closed(self):
        # writer 정지 이후(migration plan 단계) 실패하면 writer를 임의로 재기동하지 않고
        # safety_set/target/복구 지침을 stderr에 출력해야 한다.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "docker.log"
            log.write_text("")
            backup_result = self._run_backup(tmp, log)
            self.assertEqual(backup_result.returncode, 0, backup_result.stderr)
            backup_set = next((Path(tmp) / "backups").glob("backup-*"))

            log.write_text("")
            restore_result = self._run_restore(
                tmp, log, backup_set, FAKE_DOCKER_FAIL="showmigrations --plan"
            )
            self.assertNotEqual(restore_result.returncode, 0)
            log_lines = log.read_text().splitlines()
            # destructive 단계(writer 정지, DB 교체)는 진행됐다.
            self.assertTrue(any("dropdb" in line for line in log_lines))
            self.assertTrue(any("createdb" in line for line in log_lines))
            # safety backup(beta_backup.sh) 자체는 자신의 snapshot을 위해 writer를
            # 잠깐 멈췄다 되돌리므로, restore 본체가 실행한 마지막 "stop -t 60" 이후
            # 구간만 봐서 writer가 재기동되지 않았는지 확인한다.
            last_stop_idx = max(
                i for i, line in enumerate(log_lines) if "stop -t 60 backend-web" in line
            )
            after_restore_stop = log_lines[last_stop_idx + 1 :]
            self.assertFalse(any("start backend-web" in line for line in after_restore_stop))
            self.assertFalse(any("up -d backend-web" in line for line in after_restore_stop))
            combined = restore_result.stdout + restore_result.stderr
            self.assertIn("safety backup:", combined)
            self.assertIn("restore target:", combined)
            self.assertIn(str(backup_set), combined)
            sets = sorted((Path(tmp) / "backups").glob("backup-*"))
            self.assertEqual(len(sets), 2)
            safety_set = [s for s in sets if s != backup_set][0]
            self.assertIn(str(safety_set), combined)

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
