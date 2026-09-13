"""CLI entry point for Student Chief of Staff."""

from slack_bolt import response

from src.agent.chief_of_staff import run_agent
from src.runtime.orchestrator import RuntimeOrchestrator


def main() -> None:
    """Start monitoring before accepting interactive requests."""

    runtime = RuntimeOrchestrator()
    runtime.start()

    print("\nStudent Chief of Staff")
    print("Monitoring Gmail and Calendar in the background.")
    print("Type 'exit' or 'quit' to stop.")

    try:
        while True:
            message = input("\nYou: ").strip()

            if not message:
                continue

            if message.lower() in {"exit", "quit"}:
                break

            if message.lower() == "status":
                print(runtime.status())
                continue

            # Strands already streams the coordinator response to the terminal.
            # Printing the returned response again duplicates every answer.
            response = run_agent(message)
            print(f"\nChief of Staff: {response}")

    except KeyboardInterrupt:
        pass

    finally:
        runtime.stop()
        print("\nGoodbye!")


if __name__ == "__main__":
    main()