import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _docker_available() -> bool:
    return shutil.which("docker") is not None


class LocalBetaOpsStaticContractTest(unittest.TestCase):
    def test_required_scripts_exist_and_are_syntax_valid(self):
        for name in (
            "local_beta_common.sh",
            "local_beta_setup.sh",
            "local_beta_start.sh",
            "local_beta_status.sh",
            "local_beta_stop.sh",
        ):
            script = SCRIPTS / name
            self.assertTrue(script.is_file(), name)
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_scripts_pin_local_beta_compose_inputs(self):
        for name in ("local_beta_setup.sh", "local_beta_start.sh", "local_beta_status.sh", "local_beta_stop.sh"):
            text = (SCRIPTS / name).read_text()
            self.assertIn("local_beta_common.sh", text, name)
        common = (SCRIPTS / "local_beta_common.sh").read_text()
        self.assertIn("docker-compose.beta.yml", common)
        self.assertIn("docker-compose.local-beta.yml", common)
        self.assertIn(".env.local-beta", common)
        self.assertIn("--project-directory", common)

    def test_scripts_do_not_source_production_beta_common(self):
        # 로컬 QA 스크립트가 실수로 운영 beta_common.sh를 source하면 안 된다.
        for name in ("local_beta_setup.sh", "local_beta_start.sh", "local_beta_status.sh", "local_beta_stop.sh"):
            text = (SCRIPTS / name).read_text()
            self.assertNotIn('source "$SCRIPT_DIR/beta_common.sh"', text, name)

    def test_compose_override_forces_volume_replacement(self):
        # docker compose는 기본적으로 volumes 리스트를 병합(concatenate)한다.
        # !override 없이 두면 base의 beta_media/beta_shared_tmp named volume이
        # 남아 MEDIA_ROOT/TMPDIR이 가리키는 bind mount와 별개로 붕 뜬 채 마운트되어
        # "Docker와 호스트가 동일 절대경로를 본다"는 경로 계약이 깨진다.
        text = (ROOT / "docker-compose.local-beta.yml").read_text()
        for service in ("backend-web", "backend-worker", "nginx"):
            block = re.search(rf"^  {service}:.*?(?=^  [a-z][a-z0-9-]*:|\Z)", text, re.M | re.S).group(0)
            self.assertIn("volumes: !override", block, service)

    def test_compose_override_pins_media_and_tmp_paths(self):
        text = (ROOT / "docker-compose.local-beta.yml").read_text()
        for service in ("backend-web", "backend-worker"):
            block = re.search(rf"^  {service}:.*?(?=^  [a-z][a-z0-9-]*:|\Z)", text, re.M | re.S).group(0)
            self.assertIn("MEDIA_ROOT: ${LOCAL_BETA_MEDIA_DIR:?}", block, service)
            self.assertIn("TMPDIR: ${LOCAL_BETA_TMP_DIR:?}", block, service)
            self.assertIn("source: ${LOCAL_BETA_MEDIA_DIR:?}\n        target: ${LOCAL_BETA_MEDIA_DIR:?}", block, service)
            self.assertIn("source: ${LOCAL_BETA_TMP_DIR:?}\n        target: ${LOCAL_BETA_TMP_DIR:?}", block, service)

    def test_compose_override_disables_container_ax_worker_by_default(self):
        text = (ROOT / "docker-compose.local-beta.yml").read_text()
        block = re.search(r"^  ax-worker:.*?(?=^  [a-z][a-z0-9-]*:|\Z)", text, re.M | re.S).group(0)
        self.assertIn("profiles: [container-ax]", block)

    def test_compose_override_binds_redis_to_loopback_only(self):
        text = (ROOT / "docker-compose.local-beta.yml").read_text()
        block = re.search(r"^  redis:.*?(?=^  [a-z][a-z0-9-]*:|\Z)", text, re.M | re.S).group(0)
        self.assertIn("127.0.0.1:${LOCAL_BETA_REDIS_PORT:-6380}:6379", block)

    def test_env_template_defaults_to_open_access_for_local_qa(self):
        text = (ROOT / ".env.local-beta.example").read_text()
        self.assertIn("BETA_ACCESS_MODE=open", text)
        self.assertIn("LLM_PROVIDER=claude_cli", text)

    def test_gitignore_excludes_local_beta_secrets_and_state(self):
        text = (ROOT / ".gitignore").read_text()
        self.assertIn(".env.local-beta", text)
        self.assertIn(".local-beta/", text)
        self.assertIn("!.env.local-beta.example", text)

    def test_worker_and_tunnel_signatures_match_what_start_actually_runs(self):
        # common.sh의 PID 서명이 start.sh가 실제로 실행하는 커맨드와 어긋나면
        # stop/status가 실행 중인 프로세스를 못 찾거나 엉뚱한 프로세스를 판단하게 된다.
        common = (SCRIPTS / "local_beta_common.sh").read_text()
        start = (SCRIPTS / "local_beta_start.sh").read_text()
        worker_sig = re.search(r'AX_WORKER_SIGNATURE="([^"]+)"', common).group(1)
        for token in ("-A celery_app worker -Q ax",):
            self.assertIn(token, worker_sig)
            self.assertIn(token, start)
        tunnel_sig = re.search(r'CLOUDFLARED_SIGNATURE="([^"]+)"', common).group(1)
        self.assertIn(tunnel_sig, start)

    def test_setup_never_overwrites_existing_env_file(self):
        text = (SCRIPTS / "local_beta_setup.sh").read_text()
        self.assertIn('if [[ ! -f "$ENV_FILE" ]]; then', text)

    def test_stop_default_preserves_volumes_purge_is_explicit(self):
        text = (SCRIPTS / "local_beta_stop.sh").read_text()
        self.assertIn("compose stop", text)
        self.assertIn("--purge", text)
        self.assertIn("compose down -v", text)
        self.assertLess(text.index("PURGE=1"), text.index("compose down -v"))

    def test_start_cleans_up_only_what_it_started_on_failure(self):
        text = (SCRIPTS / "local_beta_start.sh").read_text()
        self.assertIn("trap cleanup_on_failure EXIT", text)
        self.assertIn("STARTED_WORKER", text)
        self.assertIn("STARTED_TUNNEL", text)


@unittest.skipUnless(_docker_available(), "docker not installed")
class LocalBetaComposeConfigTest(unittest.TestCase):
    def test_merged_compose_config_is_valid_and_excludes_ax_worker_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env.local-beta.fake"
            env_file.write_text(
                "\n".join(
                    [
                        "BETA_RELEASE_TAG=local-beta-test",
                        "BETA_DB_PASSWORD=x",
                        "VITE_GOOGLE_CLIENT_ID=x",
                        "BETA_ACCESS_MODE=open",
                    ]
                )
            )
            env = dict(os.environ)
            env.update(
                {
                    "BETA_ENV_FILE": str(env_file),
                    "LOCAL_BETA_MEDIA_DIR": str(Path(tmp) / "media"),
                    "LOCAL_BETA_TMP_DIR": str(Path(tmp) / "tmp"),
                    "BETA_RELEASE_TAG": "local-beta-test",
                    "BETA_DB_PASSWORD": "x",
                    "VITE_GOOGLE_CLIENT_ID": "x",
                }
            )
            result = subprocess.run(
                [
                    "docker", "compose",
                    "-f", str(ROOT / "docker-compose.beta.yml"),
                    "-f", str(ROOT / "docker-compose.local-beta.yml"),
                    "config", "--quiet",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            services = subprocess.run(
                [
                    "docker", "compose",
                    "-f", str(ROOT / "docker-compose.beta.yml"),
                    "-f", str(ROOT / "docker-compose.local-beta.yml"),
                    "config", "--services",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.split()
            self.assertIn("backend-web", services)
            self.assertIn("nginx", services)
            self.assertNotIn("ax-worker", services)


class PidSafetyTest(unittest.TestCase):
    """local_beta_common.sh의 pid_matches_signature/stop_pidfile을 실제 프로세스로 검증한다."""

    def _run_with_common(self, script_body: str) -> subprocess.CompletedProcess:
        wrapper = f'source "{SCRIPTS / "local_beta_common.sh"}"\n{script_body}\n'
        return subprocess.run(["bash", "-c", wrapper], text=True, capture_output=True)

    def test_stop_pidfile_kills_matching_process_and_removes_pidfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "proc.pid"
            proc = subprocess.Popen(["sleep", "60"])
            pidfile.write_text(str(proc.pid))
            try:
                result = self._run_with_common(
                    f'stop_pidfile "{pidfile}" "sleep 60" "테스트 프로세스"'
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                time.sleep(0.2)
                self.assertIsNotNone(proc.poll(), "서명이 일치하는 프로세스가 종료되지 않았다")
                self.assertFalse(pidfile.exists())
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

    def test_stop_pidfile_skips_process_with_mismatched_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "proc.pid"
            proc = subprocess.Popen(["sleep", "60"])
            pidfile.write_text(str(proc.pid))
            try:
                result = self._run_with_common(
                    f'stop_pidfile "{pidfile}" "this-signature-does-not-match-anything" "테스트 프로세스"'
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIsNone(proc.poll(), "서명이 다른데도 프로세스를 종료했다 — PID 재사용 시 사고 위험")
                # 서명 불일치 시에도 pidfile 자체는 정리한다(더 이상 신뢰할 수 없으므로).
                self.assertFalse(pidfile.exists())
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()

    def test_pidfile_is_running_false_when_no_pidfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "missing.pid"
            result = self._run_with_common(
                f'if pidfile_is_running "{pidfile}" "anything"; then exit 1; else exit 0; fi'
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_pidfile_is_running_true_for_live_matching_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            pidfile = Path(tmp) / "proc.pid"
            proc = subprocess.Popen(["sleep", "60"])
            pidfile.write_text(str(proc.pid))
            try:
                result = self._run_with_common(
                    f'if pidfile_is_running "{pidfile}" "sleep 60"; then exit 0; else exit 1; fi'
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            finally:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    unittest.main()
