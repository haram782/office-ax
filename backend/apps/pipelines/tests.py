"""
Pipeline CRUD API 테스트.

커버 범위:
  1. GET /api/v1/pipelines/ — 목록 조회 (본인 것만)
  (PipelineStep API 테스트는 파일 하단 참조)
  2. POST /api/v1/pipelines/ — 생성
  3. GET /api/v1/pipelines/{id}/ — 단건 조회
  4. PATCH /api/v1/pipelines/{id}/ — 부분 수정
  5. DELETE /api/v1/pipelines/{id}/ — 삭제
  6. 다른 유저 파이프라인 접근 차단 검증
  7. 인증 없이 접근 시 401 응답 검증
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

User = get_user_model()


def _make_user(username="pipe_tester"):
    return User.objects.create_user(username=username, password="pw")


def _authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class PipelineListCreateTest(TestCase):
    """GET /api/v1/pipelines/ 및 POST 테스트."""

    def setUp(self):
        self.user = _make_user()
        self.client = _authed_client(self.user)

    def test_empty_list(self):
        """파이프라인이 없으면 빈 배열 반환."""
        response = self.client.get("/api/v1/pipelines/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_create_pipeline(self):
        """파이프라인 생성 성공 — 필수 필드 검증."""
        payload = {
            "name": "테스트 파이프라인",
            "type": "A",
            "trigger_meta": {},
            "is_active": True,
        }
        response = self.client.post("/api/v1/pipelines/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["name"], "테스트 파이프라인")
        self.assertEqual(response.data["type"], "A")
        self.assertIn("id", response.data)

    def test_create_pipeline_b_type(self):
        """이메일수신형(B) 파이프라인 생성 — trigger_meta에 이메일 주소 저장."""
        payload = {
            "name": "이메일 수신 파이프라인",
            "type": "B",
            "trigger_meta": {"email": "inbox@officeax.com"},
            "is_active": True,
        }
        response = self.client.post("/api/v1/pipelines/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["trigger_meta"]["email"], "inbox@officeax.com")

    def test_create_pipeline_invalid_type(self):
        """지원하지 않는 type 값이면 400 반환."""
        payload = {"name": "잘못된 타입", "type": "Z"}
        response = self.client.post("/api/v1/pipelines/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_list_shows_only_own_pipelines(self):
        """다른 유저의 파이프라인은 목록에 포함되지 않는다."""
        other_user = _make_user(username="other_pipe")
        other_client = _authed_client(other_user)
        other_client.post(
            "/api/v1/pipelines/",
            {"name": "타인 파이프라인", "type": "A"},
            format="json",
        )

        # 내 계정으로 조회
        self.client.post(
            "/api/v1/pipelines/",
            {"name": "내 파이프라인", "type": "C"},
            format="json",
        )
        response = self.client.get("/api/v1/pipelines/")
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "내 파이프라인")

    def test_unauthenticated_returns_401(self):
        """인증 없이 접근 시 401 반환."""
        response = APIClient().get("/api/v1/pipelines/")
        self.assertEqual(response.status_code, 401)


class PipelineDetailTest(TestCase):
    """GET / PATCH / DELETE /api/v1/pipelines/{id}/ 테스트."""

    def setUp(self):
        self.user = _make_user(username="pipe_detail")
        self.client = _authed_client(self.user)
        # 파이프라인 하나 생성
        res = self.client.post(
            "/api/v1/pipelines/",
            {"name": "상세 테스트 파이프라인", "type": "C", "trigger_meta": {"cron": "0 9 * * 1"}},
            format="json",
        )
        self.pipeline_id = res.data["id"]

    def test_retrieve_pipeline(self):
        """단건 조회 — trigger_meta 포함 응답 검증."""
        response = self.client.get(f"/api/v1/pipelines/{self.pipeline_id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["trigger_meta"]["cron"], "0 9 * * 1")

    def test_patch_pipeline_name(self):
        """PATCH로 이름 부분 수정."""
        response = self.client.patch(
            f"/api/v1/pipelines/{self.pipeline_id}/",
            {"name": "수정된 이름"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "수정된 이름")
        # type은 변경되지 않아야 함
        self.assertEqual(response.data["type"], "C")

    def test_patch_deactivate(self):
        """PATCH로 is_active False 변경."""
        response = self.client.patch(
            f"/api/v1/pipelines/{self.pipeline_id}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])

    def test_delete_pipeline(self):
        """DELETE 후 404 반환 확인."""
        del_resp = self.client.delete(f"/api/v1/pipelines/{self.pipeline_id}/")
        self.assertEqual(del_resp.status_code, 204)
        get_resp = self.client.get(f"/api/v1/pipelines/{self.pipeline_id}/")
        self.assertEqual(get_resp.status_code, 404)

    def test_other_user_cannot_access(self):
        """다른 유저는 단건 조회/수정/삭제 불가 (404)."""
        other_client = _authed_client(_make_user(username="pipe_stranger"))
        self.assertEqual(other_client.get(f"/api/v1/pipelines/{self.pipeline_id}/").status_code, 404)
        self.assertEqual(
            other_client.patch(f"/api/v1/pipelines/{self.pipeline_id}/", {"name": "해킹"}, format="json").status_code,
            404,
        )
        self.assertEqual(other_client.delete(f"/api/v1/pipelines/{self.pipeline_id}/").status_code, 404)

    def test_owner_field_is_read_only(self):
        """owner 필드는 응답에 포함되되, 요청으로 변경 불가."""
        other = _make_user(username="pipe_owner_override")
        response = self.client.patch(
            f"/api/v1/pipelines/{self.pipeline_id}/",
            {"owner": other.pk},
            format="json",
        )
        # 수정 성공해도 owner는 바뀌지 않아야 함
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["owner"], self.user.pk)


# ---------------------------------------------------------------------------
# PipelineStep API 테스트
# ---------------------------------------------------------------------------

def _create_pipeline(client, name="파이프라인", pipeline_type="A"):
    """테스트용 파이프라인을 생성하고 id를 반환한다."""
    res = client.post(
        "/api/v1/pipelines/",
        {"name": name, "type": pipeline_type, "trigger_meta": {}, "is_active": True},
        format="json",
    )
    return res.data["id"]


def _step_url(pipeline_pk, pk=None):
    """step 목록 또는 단건 URL을 반환한다."""
    base = f"/api/v1/pipelines/{pipeline_pk}/steps/"
    return base if pk is None else f"{base}{pk}/"


class StepListCreateTest(TestCase):
    """GET/POST /api/v1/pipelines/{pipeline_pk}/steps/ 테스트."""

    def setUp(self):
        self.user = _make_user(username="step_lc_user")
        self.client = _authed_client(self.user)
        self.pipeline_id = _create_pipeline(self.client)

    def test_create_step(self):
        """step 생성 성공 — 필수 필드 검증."""
        payload = {
            "step_type": "trigger",
            "step_order": 1,
            "label": "트리거 스텝",
            "config": {"key": "value"},
        }
        res = self.client.post(_step_url(self.pipeline_id), payload, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["step_type"], "trigger")
        self.assertEqual(res.data["step_order"], 1)
        self.assertEqual(res.data["label"], "트리거 스텝")
        self.assertEqual(res.data["pipeline"], self.pipeline_id)

    def test_create_step_duplicate_order(self):
        """같은 pipeline에 같은 step_order — 400 반환."""
        payload = {"step_type": "trigger", "step_order": 1, "label": "첫 번째"}
        self.client.post(_step_url(self.pipeline_id), payload, format="json")
        res = self.client.post(_step_url(self.pipeline_id), payload, format="json")
        self.assertEqual(res.status_code, 400)

    def test_other_user_cannot_create_step(self):
        """타인 파이프라인에 step 추가 시도 — 404 반환."""
        other_client = _authed_client(_make_user(username="step_intruder"))
        payload = {"step_type": "rag", "step_order": 1, "label": "침입 스텝"}
        res = other_client.post(_step_url(self.pipeline_id), payload, format="json")
        self.assertEqual(res.status_code, 404)

    def test_list_steps_ordered(self):
        """여러 step이 step_order 오름차순으로 반환된다."""
        for order, stype in [(3, "output"), (1, "trigger"), (2, "rag")]:
            self.client.post(
                _step_url(self.pipeline_id),
                {"step_type": stype, "step_order": order, "label": f"스텝{order}"},
                format="json",
            )
        res = self.client.get(_step_url(self.pipeline_id))
        self.assertEqual(res.status_code, 200)
        orders = [s["step_order"] for s in res.data]
        self.assertEqual(orders, sorted(orders))


class StepDetailTest(TestCase):
    """GET/PATCH/DELETE /api/v1/pipelines/{pipeline_pk}/steps/{pk}/ 테스트."""

    def setUp(self):
        self.user = _make_user(username="step_detail_user")
        self.client = _authed_client(self.user)
        self.pipeline_id = _create_pipeline(self.client)
        res = self.client.post(
            _step_url(self.pipeline_id),
            {"step_type": "aiaction", "step_order": 1, "label": "AI 액션", "config": {}},
            format="json",
        )
        self.step_id = res.data["id"]

    def test_patch_step_label(self):
        """PATCH로 label 수정."""
        res = self.client.patch(
            _step_url(self.pipeline_id, self.step_id),
            {"label": "수정된 레이블"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["label"], "수정된 레이블")

    def test_patch_step_config(self):
        """PATCH로 config 수정."""
        res = self.client.patch(
            _step_url(self.pipeline_id, self.step_id),
            {"config": {"model": "gpt-4o"}},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["config"]["model"], "gpt-4o")

    def test_delete_step(self):
        """DELETE 후 404 확인."""
        del_res = self.client.delete(_step_url(self.pipeline_id, self.step_id))
        self.assertEqual(del_res.status_code, 204)
        get_res = self.client.get(_step_url(self.pipeline_id, self.step_id))
        self.assertEqual(get_res.status_code, 404)

    def test_other_user_cannot_access_step(self):
        """타인은 단건 조회/수정/삭제 불가 — 404."""
        other_client = _authed_client(_make_user(username="step_stranger"))
        url = _step_url(self.pipeline_id, self.step_id)
        self.assertEqual(other_client.get(url).status_code, 404)
        self.assertEqual(other_client.patch(url, {"label": "해킹"}, format="json").status_code, 404)
        self.assertEqual(other_client.delete(url).status_code, 404)

    def test_patch_output_label(self):
        """PATCH로 output_label 저장 후 응답에 반영된다."""
        res = self.client.patch(
            _step_url(self.pipeline_id, self.step_id),
            {"output_label": "GPT 분석 결과 요약"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["output_label"], "GPT 분석 결과 요약")

    def test_pipeline_steps_include_output_label(self):
        """GET steps 목록 응답에 output_label 필드가 포함된다."""
        res = self.client.get(_step_url(self.pipeline_id))
        self.assertEqual(res.status_code, 200)
        self.assertIn("output_label", res.data[0])


class StepReorderTest(TestCase):
    """POST /api/v1/pipelines/{pipeline_pk}/steps/reorder/ 테스트."""

    def setUp(self):
        self.user = _make_user(username="step_reorder_user")
        self.client = _authed_client(self.user)
        self.pipeline_id = _create_pipeline(self.client)
        # 3개 step 생성 (order: 1, 2, 3)
        self.step_ids = []
        for order, stype in [(1, "trigger"), (2, "rag"), (3, "output")]:
            res = self.client.post(
                _step_url(self.pipeline_id),
                {"step_type": stype, "step_order": order, "label": f"스텝{order}"},
                format="json",
            )
            self.step_ids.append(res.data["id"])

    def _reorder_url(self):
        return f"/api/v1/pipelines/{self.pipeline_id}/steps/reorder/"

    def test_reorder_success(self):
        """3개 step 순서 변경 후 step_order가 요청대로 반영된다."""
        # 순서 역전: 기존 1→3, 2→2, 3→1
        payload = [
            {"id": self.step_ids[0], "step_order": 3},
            {"id": self.step_ids[1], "step_order": 2},
            {"id": self.step_ids[2], "step_order": 1},
        ]
        res = self.client.post(self._reorder_url(), payload, format="json")
        self.assertEqual(res.status_code, 200)
        # 응답은 step_order 오름차순 정렬이어야 함
        orders = [s["step_order"] for s in res.data]
        self.assertEqual(orders, [1, 2, 3])
        # step_ids[2]가 order=1이 됐는지 확인
        first = next(s for s in res.data if s["step_order"] == 1)
        self.assertEqual(first["id"], self.step_ids[2])

    def test_reorder_wrong_ids(self):
        """존재하지 않는 id가 포함되면 400 반환."""
        payload = [
            {"id": self.step_ids[0], "step_order": 1},
            {"id": 99999, "step_order": 2},  # 존재하지 않는 id
        ]
        res = self.client.post(self._reorder_url(), payload, format="json")
        self.assertEqual(res.status_code, 400)

    def test_reorder_other_pipeline_steps(self):
        """타인 pipeline에 대한 reorder 요청 — 404 반환."""
        other_client = _authed_client(_make_user(username="step_reorder_stranger"))
        payload = [{"id": self.step_ids[0], "step_order": 1}]
        res = other_client.post(self._reorder_url(), payload, format="json")
        self.assertEqual(res.status_code, 404)


class PipelineWithStepsTest(TestCase):
    """GET /api/v1/pipelines/{id}/ 응답에 steps 배열이 포함되는지 확인."""

    def setUp(self):
        self.user = _make_user(username="pipeline_steps_user")
        self.client = _authed_client(self.user)
        self.pipeline_id = _create_pipeline(self.client)

    def test_pipeline_response_includes_steps(self):
        """파이프라인 단건 조회 시 steps 배열이 포함된다."""
        # step 2개 생성
        for order, stype in [(1, "trigger"), (2, "output")]:
            self.client.post(
                _step_url(self.pipeline_id),
                {"step_type": stype, "step_order": order, "label": f"스텝{order}"},
                format="json",
            )
        res = self.client.get(f"/api/v1/pipelines/{self.pipeline_id}/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("steps", res.data)
        self.assertEqual(len(res.data["steps"]), 2)
        orders = [s["step_order"] for s in res.data["steps"]]
        self.assertEqual(orders, [1, 2])


# ---------------------------------------------------------------------------
# PipelineRun API 테스트
# ---------------------------------------------------------------------------

class PipelineRunListTest(TestCase):
    """GET /api/v1/pipelines/{pipeline_pk}/runs/ 테스트."""

    def setUp(self):
        self.user = _make_user(username="run_list_user")
        self.client = _authed_client(self.user)
        self.pipeline_id = _create_pipeline(self.client, name="실행기록 파이프라인")

    def _seed_runs(self, n=3):
        """테스트용 PipelineRun을 n개 직접 생성한다."""
        from .models import Pipeline, PipelineRun
        pipeline = Pipeline.objects.get(pk=self.pipeline_id)
        for i in range(n):
            PipelineRun.objects.create(
                pipeline=pipeline,
                status="success",
                log=f"실행 로그 {i}",
            )

    def test_list_runs_success(self):
        """본인 파이프라인의 runs 목록을 최신순으로 반환한다."""
        self._seed_runs(3)
        res = self.client.get(f"/api/v1/pipelines/{self.pipeline_id}/runs/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 3)
        # started_at 내림차순 정렬 확인
        dates = [r["started_at"] for r in res.data]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_other_user_gets_empty_list(self):
        """타인 파이프라인의 runs 조회 시도 — 빈 배열 반환."""
        self._seed_runs(2)
        other_client = _authed_client(_make_user(username="run_stranger"))
        res = other_client.get(f"/api/v1/pipelines/{self.pipeline_id}/runs/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, [])

    def test_empty_runs(self):
        """runs가 없을 때 빈 배열 200 반환."""
        res = self.client.get(f"/api/v1/pipelines/{self.pipeline_id}/runs/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, [])
