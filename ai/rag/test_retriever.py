
from ai.rag.retriever import search_knowledge_base_with_scores


TEST_CASES = [
    {
        "incident": "OOMKilled",
        "query": "Container terminated with OOMKilled and exit code 137. "
                 "Investigate memory limits, usage, and memory pressure.",
        "expected_file": "oomkilled_troubleshooting_runbook.md"
    },
    {
        "incident": "CrashLoopBackOff",
        "query": "Container repeatedly crashes and restarts. "
                 "Investigate previous logs, exit code, and restart events.",
        "expected_file": "crashloopbackoff_troubleshooting_runbook.md"
    },
    {
        "incident": "ImagePullBackOff",
        "query": "Kubernetes cannot pull a container image. "
                 "Check image name, tag, registry authentication, and events.",
        "expected_file": "imagepullbackoff_troubleshooting_runbook.md"
    },
    {
        "incident": "Pending Pods",
        "query": "Pod remains Pending because of scheduling constraints, "
                 "insufficient CPU or memory, taints, or persistent volume binding.",
        "expected_file": "pendingprobe_troubleshooting_runbook.md"
    },
    {
        "incident": "Probe Failures",
        "query": "Readiness, liveness, or startup probe is failing. "
                 "Investigate HTTP status, connection errors, ports, and timings.",
        "expected_file": "probefailure_troubleshooting_runbook.md"
    },
    {
        "incident": "CreateContainerConfigError",
        "query": "Container cannot start because its configuration references "
                 "a missing Secret, ConfigMap, or invalid environment variable.",
        "expected_file": "CreateContainerConfigError_troubleshooting_runbook.md"
    },
    {
        "incident": "Volume Mount Failures",
        "query": "Pod is stuck in ContainerCreating due to FailedMount, "
                 "FailedAttachVolume, PVC, or storage attachment issues.",
        "expected_file": "VolumeMountFailures_troubleshooting_runbook.md"
    }
]


def main():
    print("=" * 65)
    print("KubeTroubleshoot AI - RAG Retrieval Validation")
    print("=" * 65)

    passed = 0
    failed = 0

    for test_case in TEST_CASES:
        incident = test_case["incident"]
        expected_file = test_case["expected_file"]

        print(f"\nIncident: {incident}")
        print("-" * 50)

        try:
            results = search_knowledge_base_with_scores(
                test_case["query"],
                top_k=5
            )

            if not results:
                print("FAIL: No results returned.")
                failed += 1
                continue

            expected_found = False

            for rank, (document, distance) in enumerate(results, start=1):
                source = document.metadata.get("source", "Unknown source")
                filename = document.metadata.get(
                    "filename",
                    source.replace("\\", "/").split("/")[-1]
                )

                if filename == expected_file:
                    expected_found = True

                print(f"\nResult {rank}: {filename}")
                print(f"Distance: {distance:.4f}")
                print(f"Source: {source}")
                print(f"Content: {document.page_content[:250]}")

            if expected_found:
                print(f"\nPASS: Retrieved expected runbook {expected_file}")
                passed += 1
            else:
                print(f"\nFAIL: {expected_file} not found in top 5 results.")
                failed += 1

        except Exception as error:
            print(f"ERROR: {type(error).__name__}: {error}")
            failed += 1

    print("\n" + "=" * 65)
    print(f"Passed: {passed}/{len(TEST_CASES)}")
    print(f"Failed: {failed}/{len(TEST_CASES)}")
    print("=" * 65)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()




# from ai.rag.retriever import search_knowledge_base


# def main():

#     query = "Pod is failing with ImagePullBackOff"

#     results = search_knowledge_base(
#         query,
#         top_k=3
#     )

#     print("\n==============================")
#     print("RAG SEARCH RESULTS")
#     print("==============================")

#     for index, document in enumerate(results, start=1):

#         print(f"\n--- Result {index} ---")

#         print("Source:")
#         print(document.metadata.get("source"))

#         print("\nContent:")
#         print(document.page_content)


# if __name__ == "__main__":
#     main()