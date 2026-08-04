from uuid import uuid4

from workflow.graph import AgriculturalWorkflow


def print_trace(state: dict) -> None:
    print("\nWORKFLOW TRACE")

    for index, event in enumerate(
        state.get("audit_log", []),
        start=1,
    ):
        print(f"{index}. {event}")


def main() -> None:
    workflow = AgriculturalWorkflow()

    # The same thread is used for follow-up information belonging to
    # one treatment request.
    thread_id = str(uuid4())

    print("Agricultural Field-Treatment Review")
    print("Type 'quit' to exit.")

    while True:
        question = input("\nRequest: ").strip()

        if question.lower() == "quit":
            break

        state = workflow.start(
            question=question,
            thread_id=thread_id,
        )

        if state.get("__interrupt__"):
            print("\nPLAN READY FOR HUMAN REVIEW")

            if state.get("plan"):
                print(state["plan"].model_dump_json(indent=2))

            if state.get("review"):
                print(state["review"].model_dump_json(indent=2))

            while True:
                decision = (
                    input("\nApprove simulated work order? (yes/no): ").strip().lower()
                )

                if decision in {
                    "yes",
                    "no",
                }:
                    break

                print("Please enter 'yes' or 'no'.")

            state = workflow.resume_human_review(
                decision=("approved" if decision == "yes" else "rejected"),
                thread_id=thread_id,
            )

        print(
            "\nStatus:",
            state.get("final_status"),
        )

        print(
            "Message:",
            state.get("final_message"),
        )

        missing_information = state.get(
            "missing_information",
            [],
        )

        if missing_information:
            print(
                "Missing information:",
                ", ".join(missing_information),
            )

        if state.get("plan"):
            print("\nPLAN")

            print(state["plan"].model_dump_json(indent=2))

        if state.get("review"):
            print("\nREVIEW")

            print(state["review"].model_dump_json(indent=2))

        if state.get("work_order"):
            print("\nWORK ORDER")

            print(state["work_order"].model_dump_json(indent=2))

        print_trace(state)

        # Keep the thread active only when the workflow is waiting for
        # follow-up information. Terminal outcomes receive a fresh
        # thread so checkpoint data does not leak into the next request.
        if state.get("final_status") != "needs_information":
            thread_id = str(uuid4())


if __name__ == "__main__":
    main()
