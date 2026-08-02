from uuid import uuid4

from graph import AgriculturalWorkflow
from schemas import WorkflowResponse

#Temporary cmd-line interface for testing independently of Streamlit

def print_result(
    result: WorkflowResponse,
) -> None:
    """
    Print the structured workflow response.
    """

    print("\nAGRICULTURUAL TREATMENT WORKFLOW")
    print("-" * 40)

    print("Thread:", result.thread_id)
    print("Turn:", result.turn_number)
    print("Status:", result.final_status)
    print("Message:", result.final_message)

    if result.triage is not None:
        print("\nTRIAGE")
        print("Issue type:", result.triage.issue_type)
        print("Next step:", result.triage.next_step)
        print("Reason:", result.triage.routing_reason)

        print("\nMISSING INFORMATION")

        if result.triage.missing_information:
            for item in result.triage.missing_information:
                print("-", item)
        else:
            print("- None")
    
    if result.request is not None:
        print("\nSTRUCTURED REQUEST")

        print(
            result.request.model_dump_json(
                indent=2,
            )
        )

    print("\nWORKFLOW TRACE")

    for step, event in enumerate(
        result.audit_log,
        start=1,
    ):
        print(f"{step}. {event}")

def main() -> None:
    workflow = AgriculturalWorkflow()

    thread_id = str(uuid4())

    print("Agricultural Field-Treatment Review")
    print("Type 'quit' to exit.")

    while True:
        question = input("\nRequest: ").strip()

        if question.lower() == "quit":
            break

        result = workflow.process_request(
            question=question,
            thread_id=thread_id,
        )

        print_result(result)

if __name__ == "__main__":
    main()