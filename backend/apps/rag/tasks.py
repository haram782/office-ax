from celery import current_app


@current_app.task(name="rag.train_asset", queue="celery")
def train_rag_asset(asset_id: int) -> dict:
    """
    RAG 자산 파일을 벡터 DB에 학습(인덱싱)하는 Celery 태스크 스텁.
    실제 임베딩/인덱싱 로직은 ax-engine에서 처리 예정.
    완료 시 RagAsset.trained = True로 갱신한다.
    """
    from .models import RagAsset

    try:
        asset = RagAsset.objects.get(pk=asset_id)
        # TODO: ax-engine 임베딩 태스크 연동 후 실제 구현
        asset.trained = True
        asset.save(update_fields=["trained"])
        return {"asset_id": asset_id, "status": "trained"}
    except RagAsset.DoesNotExist:
        return {"asset_id": asset_id, "status": "not_found"}
