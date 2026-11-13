"""PYTHONPATH=src python3 examples/quickstart/quickstart.py"""

from pathlib import Path

from policyscope.enforcement import Policy, fact


def main():
    grants = [fact("Grant", "reader", "guide")]
    reads = []
    documents = {"guide": "Synthetic guide body"}

    def read(document):
        reads.append(fact("Read", "reader", document))
        return documents[document]

    policy = Policy(
        Path(__file__).with_name("policy.dl"),
        facts=lambda context, data: grants + reads,
    )

    def tool(document):
        return policy.call(
            "reader", "read", {"resource": document}, lambda: read(document)
        )

    assert tool("guide") == "Synthetic guide body"
    assert tool("private-draft")["code"] == "UNAVAILABLE"
    grants.clear()
    assert tool("guide")["code"] == "UNAVAILABLE"
    assert policy.runtime.query("?- Read(A, D).")["rows"] == [["reader", "guide"]]
    assert len(reads) == 1
    print(
        "One guarded business call; denied and revoked requests never executed read()."
    )


if __name__ == "__main__":
    main()
