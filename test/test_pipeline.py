import json

from rag_core import lambda_handler as ingestion_lambda


def test_lambda_reports_only_failed_sqs_messages(monkeypatch):
    processed = []

    def fake_process(record):
        key = record["s3"]["object"]["key"]
        if "bad" in key:
            raise ValueError("invalid document")
        processed.append(key)

    monkeypatch.setattr(ingestion_lambda, "_process_s3_record", fake_process)

    def envelope(message_id, key):
        return {
            "eventSource": "aws:sqs",
            "messageId": message_id,
            "body": json.dumps(
                {
                    "Records": [
                        {
                            "eventSource": "aws:s3",
                            "s3": {
                                "bucket": {"name": "legal-documents"},
                                "object": {"key": key},
                            },
                        }
                    ]
                }
            ),
        }

    result = ingestion_lambda.lambda_handler(
        {
            "Records": [
                envelope("ok-message", "incoming/files/doc/good.pdf"),
                envelope("bad-message", "incoming/files/doc/bad.pdf"),
            ]
        },
        None,
    )

    assert processed == ["incoming/files/doc/good.pdf"]
    assert result == {"batchItemFailures": [{"itemIdentifier": "bad-message"}]}
