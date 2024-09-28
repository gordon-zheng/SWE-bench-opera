import json
import argparse
from pickle import TRUE
import sys
import os
import subprocess
import shutil
import base64
from typing import List, Dict
from flask import Flask, request, jsonify

app = Flask(__name__)

def parse_arguments():
    """
    Parses command-line arguments.

    Returns:
        argparse.Namespace: The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Find instance_id by python_file and generate a JSON object with provided patch."
    )
    parser.add_argument(
        "issue_64",
        type=str,
        help="The The issue description."
    )
    parser.add_argument(
        "file_name_64",
        type=str,
        help="The name of the Python file to search for (e.g., example.py)."
    )
    parser.add_argument(
        "patch_64",
        type=str,
        help="The patch string to include in the model_patch field."
    )
    parser.add_argument(
        "clean_log",
        type=str,
        help="(TRUE or FALSE) to delete the verification logs after running the verify script."
    )
    return parser.parse_args()

def find_instance_id(file_name, issue, input_file_path="./complete_300_lite_input.txt"):
    """
    Searches for the instance_id corresponding to the given python_file.

    Args:
        file_name (str): The Python file name to search for.
        input_file_path (str): Path to the complete_300_lite_input.txt file.

    Returns:
        list: A list of matching instance_ids.
    """
     # Ensure file_name is relative by removing leading '/'
    if file_name.startswith("/"):
        original_file_name = file_name
        file_name = file_name.lstrip("/")
        print(f"Adjusted file_name from '{original_file_name}' to '{file_name}' to ensure it's relative.")

    matches = []
    if not os.path.isfile(input_file_path):
        print(f"Error: Input file '{input_file_path}' does not exist.", file=sys.stderr)
        return matches

    with open(input_file_path, 'r', encoding='utf-8') as infile:
        for line_number, line in enumerate(infile, start=1):
            line = line.strip()
            if not line:
                continue  # Skip empty lines
            try:
                data = json.loads(line)
                python_file = data.get('python_file', '')
                instance_id = data.get('instance_id', '')
                issue_in_data = data.get('issues_text', '')
                # due to the issues with extracting issues that might skip leading special characters, we need to remove some special characters from the issue strings
                issue = issue.replace('\n', '').replace('\r', '').replace('\t', '').replace(' ', '')
                issue_in_data = issue_in_data.replace('\n', '').replace('\r', '').replace('\t', '').replace(' ', '')
                if python_file == file_name and issue in issue_in_data:
                    matches.append(instance_id)
            except json.JSONDecodeError as e:
                print(f"Warning: Skipping invalid JSON on line {line_number}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"Error processing line {line_number}: {e}", file=sys.stderr)

    return matches

def generate_output_json(instance_id, patch):
    """
    Constructs the desired JSON object.

    Args:
        instance_id (str): The instance_id to include.
        patch (str): The patch string to include in model_patch.

    Returns:
        str: The JSON object as a string.
    """
    output_data = {
        "instance_id": instance_id,
        "model_name_or_path": "opera-ai",
        "text": "",
        "full_output": "",
        "model_patch": patch
    }
    return output_data


def write_to_file(json_string, output_file):
    """
    Writes the JSON string to the specified output file.

    Args:
        json_string (str): The JSON string to write.
        output_file (str): The path to the output file.
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as outfile:
            outfile.write(json_string + '\n')
        print(f"JSON object written to '{output_file}' (overwritten existing content).")
    except Exception as e:
        print(f"Error writing to file '{output_file}': {e}", file=sys.stderr)


def clean_log_directory():
    log_dir = log_dir = os.path.join('.', 'logs')
    """
    Deletes all files and folders inside the specified directory.

    Args:
        log_dir (str): The directory path to clean.
    """
    try:
        print(f"Deleting all contents inside '{log_dir}'...")
        if os.path.exists(log_dir):
            # Iterate over all items in the directory
            for filename in os.listdir(log_dir):
                file_path = os.path.join(log_dir, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)  # Remove file or symbolic link
                        print(f"Deleted file: {file_path}")
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)  # Remove directory and all its contents
                        print(f"Deleted directory: {file_path}")
                except Exception as e:
                    print(f"Failed to delete '{file_path}'. Reason: {e}", file=sys.stderr)
        else:
            print(f"Directory '{log_dir}' does not exist. No contents to delete.")
    except Exception as e:
        print(f"An error occurred while deleting contents of '{log_dir}': {e}", file=sys.stderr)
        # Depending on your requirements, you might want to exit or continue
        # sys.exit(1)


def run_verification():
    """
    Runs the verification script and captures its console output.

    Returns:
        str: The console output from the verification script.
    """
    command = [
        "python",
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        "princeton-nlp/SWE-bench_Lite",
        "--predictions_path",
        "./verify_one_instance.jsonl",
        "--max_workers",
        "4",
        "--run_id",
        "verify_one",
        # following command may not be needed
        "--clean",
        "TRUE",
        "--cache_level",
        "none",
        "--force_rebuild",
        "TRUE",
    ]

    try:
        print("Running verification script...")
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=True  # Raises CalledProcessError for non-zero exit codes
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_output = e.output.strip()
        print(f"Error during verification: {error_output}", file=sys.stderr)
        return error_output
    except FileNotFoundError:
        error_msg = "Verification script not found. Ensure that 'swebench' is installed and accessible."
        print(error_msg, file=sys.stderr)
        return error_msg
    except Exception as e:
        error_msg = f"An unexpected error occurred while running verification: {e}"
        print(error_msg, file=sys.stderr)
        return error_msg


def read_log_file(instance_id: str, file_name: str, file_extension: str) -> str:
    """
    Constructs the path to the specified log file and attempts to read its contents.

    Parameters:
        instance_id (str): The identifier for the specific instance.
        file_name (str): The name of the file to read (without extension).
        file_extension (str): The file extension (e.g., '.log').

    Returns:
        str: The contents of the log file if successful, 
             or an error message if the file cannot be read.
    """
    # Construct the base path to the log file
    base_path = os.path.join(
        '.', 
        'logs', 
        'run_evaluation', 
        'verify_one', 
        'opera-ai', 
        instance_id
    )
    # Combine the base path with the file name and extension
    log_file_path = os.path.join(base_path, file_name) + file_extension

    # Initialize the variable to hold the log contents
    log_contents = ""

    # Attempt to read the log file
    try:
        with open(log_file_path, 'r', encoding='utf-8') as log_file:
            log_contents = log_file.read().strip()
    except FileNotFoundError:
        log_contents = f"Log file '{log_file_path}' not found."
    except Exception as e:
        log_contents = f"Error reading file '{log_file_path}': {e}"

    return log_contents


def generate_verification_json(instance_id, python_file, verification_stdout):
    """
    Constructs the verification JSON object, including the run_instance_log.

    Args:
        instance_id (str): The instance_id.
        python_file (str): The python_file name.
        verification_stdout (str): The console output from verification.

    Returns:
        str: The JSON object as a string.
    """
    # retrieve the run_instance.log
    run_instance_log = read_log_file(instance_id, "run_instance", ".log")
    # retrieve the report.json
    test_report_json = read_log_file(instance_id, "report", ".json")
    # retrieve the test_output.txt
    test_output_txt = read_log_file(instance_id, "test_output", ".txt")
    # retrieve the eval.sh file
    test_eval_sh = read_log_file(instance_id, "eval", ".sh")


    # Determine fix_successful
    if "Instances resolved: 1" in verification_stdout:
        fix_successful = "TRUE"
    else:
        fix_successful = "FALSE"
    
    # Determine patch_applied
    if "'patch_successfully_applied': True" in run_instance_log:
        patch_applied = "TRUE"
    else:
        patch_applied = "FALSE"

    # Construct the verification data
    verification_data = {
        "instance_id": instance_id,
        "python_file": python_file,
        "verification_stdout": verification_stdout,
        "run_instance_log": run_instance_log,
        "test_report_json": test_report_json, 
        "test_output_txt": test_output_txt,
        "eval_sh": test_eval_sh,
        "fix_successful": fix_successful,
        "patch_applied": patch_applied,
    }
    return verification_data


def pretty_print_json(json_string, max_length=50):
    """
    Truncates each value in the JSON object to the specified maximum length.

    Args:
        json_string (str): The original JSON string.
        max_length (int): The maximum number of characters for each value.

    Returns:
        str: The truncated JSON string.
    """
    try:
        data = json.loads(json_string)
        truncated_data = {}
        for key, value in data.items():
            if isinstance(value, str):
                truncated_value = value[:max_length]
            else:
                # If the value is not a string, convert it to string and truncate
                truncated_value = str(value)[:max_length]
            truncated_data[key] = truncated_value
        print("======================")
        print("{")
        for key, value in truncated_data.items():
            print(f"   {key}: {value}")
        print("}")
        return
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON for truncation: {e}", file=sys.stderr)
        return json_string  # Return the original if decoding fails
    except Exception as e:
        print(f"Unexpected error during JSON truncation: {e}", file=sys.stderr)
        return json_string  # Return the original if any other error occurs


def extract_based64_string(base64_str):
    base64_bytes = base64_str.encode('utf-8')
    input_bytes = base64.b64decode(base64_bytes)
    return input_bytes.decode('utf-8')


def get_failed_test_files_with_content(json_str: str) -> Dict[str, List[Dict[str, str]]]:
    """
    Parses a JSON string representing test results, retrieves the file paths of failed tests,
    reads their contents, and returns a JSON structure with file names and contents.

    Parameters:
        json_str (str): A string containing the JSON data.

    Returns:
        Dict[str, List[Dict[str, str]]]: A dictionary with a key "failed_tests" containing
                                         a list of dictionaries with "test_file_name" and "content".
    """
    try:
        # Parse the JSON string into a Python dictionary
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON data: {e}")

    failed_files = set()

    # Iterate over all top-level keys in the JSON data
    for key, value in data.items():
        # Access the 'tests_status' dictionary
        tests_status = value.get("tests_status", {})
        
        # Iterate over each status category (e.g., "FAIL_TO_PASS", "PASS_TO_PASS", etc.)
        for status_category, status_values in tests_status.items():
            # Get the list of failed tests in the current category
            failures = status_values.get("failure", [])
            
            # Iterate over each failed test identifier
            for test_identifier in failures:
                # Split the test identifier to separate file path and test method
                parts = test_identifier.split("::")
                if len(parts) >= 1:
                    file_path = parts[0]
                    failed_files.add(file_path)
                else:
                    # Handle cases where the test identifier does not follow the expected format
                    continue

    # Prepare the list to hold file information
    failed_tests_info = []

    for file_path in failed_files:
        # Initialize content
        content = ""
        try:
            # Ensure the file path is safe and exists
            if not os.path.isfile(file_path):
                content = f"File '{file_path}' does not exist."
            else:
                # Read the file content
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
        except Exception as e:
            # Handle any other exceptions during file reading
            content = f"Error reading file '{file_path}': {e}"

        # Append the file information to the list
        failed_tests_info.append({
            "test_file_name": file_path,
            "content": content
        })

    # Construct the final JSON structure
    result = {
        "failed_tests": failed_tests_info
    }

    return result


def verify_patch(file_name_b64, patch_b64, issue_b64, clean_log=True):
    try:
        file_name = extract_based64_string(file_name_b64)
        patch = extract_based64_string(patch_b64)
        issue = extract_based64_string(issue_b64)
        
        matching_instance_ids = find_instance_id(file_name, issue)
    
        if not matching_instance_ids:
            error_msg = f"No instance_id found for python_file '{file_name}'."
            return {"error": error_msg}, 400
        elif len(matching_instance_ids) > 1:
            # Log a warning; here we'll just include it in the response
            warning_msg = f"Multiple instance_ids found for python_file '{file_name}'. Using the first match."
            instance_id = matching_instance_ids[0]
        else:
            instance_id = matching_instance_ids[0]
            warning_msg = None
    
        # Use the first matching instance_id
        output_json = generate_output_json(instance_id, patch)
        print(f"==== processing {instance_id}")
        write_to_file(json.dumps(output_json), "./verify_one_instance.jsonl")
        
        # Run verification and capture the output
        verification_stdout = run_verification()
        
        # Generate the verification JSON structure
        verification_json = generate_verification_json(instance_id, file_name, verification_stdout)
        # get the failed unit test file (not working currently)
        # report_json = verification_json["test_report_json"]
        
        # failed_test_files = get_failed_test_files_with_content(report_json)
   
        response = {
            "run_api_jsonl": output_json,
            "verification_json": verification_json
        }
        if warning_msg:
            response["warning"] = warning_msg
            
        # Clean up
        if clean_log:
            clean_log_directory()
        
        return response, 200
    except ValueError as ve:
        return {"error": str(ve)}, 400
    except Exception as e:
        return {"error": str(e)}, 500


# New verify_patch route
@app.route('/verify_patch', methods=['POST'])
def verify_patch_endpoint():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
        
        file_name_b64 = data.get('file_name_64')
        patch_b64 = data.get('patch_64')
        issue_b64 = data.get('issue_64')
        clean_log = data.get('clean_log')
        if not clean_log:
            clean_log = True
        elif clean_log.upper() == "TRUE":
            clean_log = True
        elif clean_log.upper() == "FALSE":
            clean_log = False
        
        if not file_name_b64 or not patch_b64:
            return jsonify({"error": "Both 'file_name' and 'patch' fields are required"}), 400
        
        result, status_code = verify_patch(file_name_b64, patch_b64, issue_b64, clean_log)
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
