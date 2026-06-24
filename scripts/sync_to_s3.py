from __future__ import annotations

import argparse
from pathlib import Path

import boto3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync local artifacts to S3.")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--prefix", default="law-chatbot", help="S3 prefix")
    parser.add_argument(
        "--source-dir",
        default=str(Path(__file__).resolve().parents[1] / "models" / "vector_store"),
        help="Local directory to upload",
    )
    return parser.parse_args()


def upload_dir_to_s3(source_dir: Path, bucket: str, prefix: str) -> None:
    s3 = boto3.client("s3")

    for file_path in source_dir.rglob("*"):
        if not file_path.is_file():
            continue

        relative_path = file_path.relative_to(source_dir).as_posix()
        s3_key = f"{prefix.rstrip('/')}/{relative_path}"

        s3.upload_file(str(file_path), bucket, s3_key)
        print(f"Uploaded: {file_path} -> s3://{bucket}/{s3_key}")


def main() -> None:
    args = parse_args()
    source_dir = Path(args.source_dir)

    if not source_dir.exists():
        raise FileNotFoundError(f"Source dir not found: {source_dir}")

    upload_dir_to_s3(source_dir, args.bucket, args.prefix)


if __name__ == "__main__":
    main()