import json
import re

def extract_patching_failures(run_instance_log):
    """
    Extracts all patching failure sections from the run_instance_log string,
    including the ">>>>> Patch Apply Failed:" statement up to the next "INFO" log.

    Args:
        run_instance_log (str): The log string from the JSON.

    Returns:
        list: A list of extracted patching failure messages with "INFO ..." appended.
    """
    # Define a regex pattern to capture all sections starting with '>>>>> Patch Apply Failed:'
    # and ending before the next 'INFO' log line.
    # The pattern uses a positive lookahead to stop before the next 'INFO' log.
    pattern = re.compile(
        r"(>>>>> Patch Apply Failed:.*?)(?=\n\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} - INFO - )",
        re.DOTALL
    )

    # Find all matches in the log
    matches = pattern.findall(run_instance_log)

    # Clean up each extracted failure message and append "INFO ..."
    patch_failures = [f"{match.strip()}\nINFO ..." for match in matches]

    # remove the if statement if you don't want to print it out directly. 
    if patch_failures:
        print("=== Patching Failure Details ===\n")
        for idx, failure in enumerate(patch_failures, start=1):
            print(f"--- Failure {idx} ---")
            print(failure)
            print()
    return patch_failures

def main():
    # Example JSON data (as provided by the user)
    json_data = r'''
    {
        "run_instance_log": "2024-09-28 15:03:56,599 - INFO - Environment image sweb.env.x86_64.5d1fda9d55d65d8a4e5bdb:latest found for pytest-dev__pytest-7373\nBuilding instance image sweb.eval.x86_64.pytest-dev__pytest-7373:latest for pytest-dev__pytest-7373\n2024-09-28 15:04:07,914 - INFO - Creating container for pytest-dev__pytest-7373...\n2024-09-28 15:04:07,970 - INFO - Container for pytest-dev__pytest-7373 created: 00075ca269fc60678bc7640793f92480f57057089ce2a48997b85faa5c739202\n2024-09-28 15:04:08,279 - INFO - Container for pytest-dev__pytest-7373 started: 00075ca269fc60678bc7640793f92480f57057089ce2a48997b85faa5c739202\n2024-09-28 15:04:08,283 - INFO - Intermediate patch for pytest-dev__pytest-7373 written to logs/run_evaluation/verify_one/opera-ai/pytest-dev__pytest-7373/patch.diff, now applying to container...\n2024-09-28 15:04:08,491 - INFO - Failed to apply patch to container, trying again...\n2024-09-28 15:04:08,531 - INFO - >>>>> Patch Apply Failed:\npatching file src/_pytest/mark/evaluate.py\npatch: **** malformed patch at line 18:  \n\n\n2024-09-28 15:04:08,536 - INFO - Traceback (most recent call last):\n  File \"/mnt/c/Users/gordo/OneDrive/Documents/Machine_Learning/SWE-bench-opera/swebench/harness/run_evaluation.py\", line 134, in run_instance\n    raise EvaluationError(\nEvaluationError: Evaluation error for pytest-dev__pytest-7373: >>>>> Patch Apply Failed:\npatching file src/_pytest/mark/evaluate.py\npatch: **** malformed patch at line 18:  \n\n\nCheck (logs/run_evaluation/verify_one/opera-ai/pytest-dev__pytest-7373/run_instance.log) for more information.\n\n2024-09-28 15:04:08,536 - INFO - Attempting to stop container sweb.eval.pytest-dev__pytest-7373.verify_one...\n2024-09-28 15:04:27,535 - INFO - Attempting to remove container sweb.eval.pytest-dev__pytest-7373.verify_one...\n2024-09-28 15:04:27,559 - INFO - Container sweb.eval.pytest-dev__pytest-7373.verify_one removed.\n2024-09-28 15:04:27,560 - INFO - Attempting to remove image sweb.eval.x86_64.pytest-dev__pytest-7373:latest...\n2024-09-28 15:04:27,583 - INFO - Image sweb.eval.x86_64.pytest-dev__pytest-7373:latest removed."
    }
    '''

    # Load the JSON data
    try:
        data = json.loads(json_data)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}")
        return

    # Extract the run_instance_log
    run_instance_log = data.get("run_instance_log", "")
    if not run_instance_log:
        print("No 'run_instance_log' found in the JSON data.")
        return

    # Extract the patching failure sections
    patch_failures = extract_patching_failures(run_instance_log)

    # Display the results
    if not patch_failures:
        print("No patching failures found in the log.")

if __name__ == "__main__":
    main()
