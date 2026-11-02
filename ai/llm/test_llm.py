from ai.llm.factory import get_llm


def main():

    llm = get_llm()

    prompt = """
You are a Kubernetes troubleshooting assistant.

Explain in simple terms:

What is CrashLoopBackOff?

Give:
1. Meaning
2. Common causes
3. Basic troubleshooting commands
in 3 lines
"""

    response = llm.generate(prompt)

    print("\n==============================")
    print("LLM RESPONSE")
    print("==============================")

    print(response)


if __name__ == "__main__":
    main()