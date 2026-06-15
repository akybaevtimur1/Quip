"""One-off: прописать R2-бакету CORS для браузерных PUT (direct upload) + напечатать тест-URL.

Запуск (utf-8 на Windows):
  $env:PYTHONIOENCODING="utf-8"; modal run deploy/modal/r2_setup.py
"""

from __future__ import annotations

import modal

app = modal.App("quip-r2-setup")
image = modal.Image.debian_slim(python_version="3.12").pip_install("boto3>=1.35")


@app.function(image=image, secrets=[modal.Secret.from_name("quip-worker")])
def setup() -> None:
    import os

    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    bucket = os.environ.get("R2_BUCKET", "quip")
    cors = {
        "CORSRules": [
            {
                "AllowedOrigins": [
                    "https://app.quip.ink",
                    "http://localhost:3000",
                    "https://*.vercel.app",
                ],
                "AllowedMethods": ["PUT", "GET", "HEAD"],
                "AllowedHeaders": ["*"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3600,
            }
        ]
    }
    try:
        client.put_bucket_cors(Bucket=bucket, CORSConfiguration=cors)
        print("CORS_SET_OK", client.get_bucket_cors(Bucket=bucket).get("CORSRules"))
    except Exception as e:  # noqa: BLE001 — токен без bucket-admin (CORS ставит фаундер в дашборде)
        print("CORS_SET_FAILED (set it in Cloudflare R2 dashboard):", type(e).__name__, e)
    # Проверка presigned PUT механизма (CORS тут не при чём — это серверный PUT).
    key = "_probe/test.bin"
    url = client.generate_presigned_url(
        "put_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600
    )
    import urllib.request

    req = urllib.request.Request(url, data=b"hello-r2-presigned", method="PUT")
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        print("PRESIGNED_PUT_STATUS", resp.status)
    # подтвердить, что объект записался
    obj = client.get_object(Bucket=bucket, Key=key)
    print("READBACK", obj["Body"].read())
    client.delete_object(Bucket=bucket, Key=key)
    print("PRESIGNED_PUT_URL_SAMPLE", url[:120])


@app.local_entrypoint()
def main() -> None:
    setup.remote()
