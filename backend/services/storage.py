import boto3
from botocore.config import Config
from core.config import settings


def _get_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.DO_SPACES_ENDPOINT,
        aws_access_key_id=settings.DO_SPACES_ACCESS_KEY,
        aws_secret_access_key=settings.DO_SPACES_SECRET_KEY,
        config=Config(s3={"addressing_style": "virtual"}),
    )


def _object_key(tenant_id: str, source_id: str) -> str:
    return f"ai-chatbot/{tenant_id}/{source_id}.pdf"


def upload_pdf(tenant_id: str, source_id: str, file_bytes: bytes) -> str:
    key = _object_key(tenant_id, source_id)
    client = _get_client()
    client.put_object(
        Bucket=settings.DO_SPACES_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType="application/pdf",
    )
    return key


def get_presigned_url(tenant_id: str, source_id: str, expires: int = 3600) -> str:
    key = _object_key(tenant_id, source_id)
    client = _get_client()
    return client.generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": settings.DO_SPACES_BUCKET,
            "Key": key,
            "ResponseContentType": "application/pdf",
        },
        ExpiresIn=expires,
    )


def delete_pdf(tenant_id: str, source_id: str) -> None:
    key = _object_key(tenant_id, source_id)
    client = _get_client()
    client.delete_object(Bucket=settings.DO_SPACES_BUCKET, Key=key)
