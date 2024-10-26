import json
import sys
import os
import subprocess
import shutil
import base64
import re
import tempfile
from typing import Tuple, List
from flask import Flask, request, jsonify
from extract_and_patch_test_file import process_log_file
import importlib.util
from pathlib import Path
from utils.diff_fixer import apply_fuzzy_matching_patch
from utils.log_condenser import LogCondenser

# Dynamically load 'diff_generator' module and import 'create_patch'
module_name = 'diff_generator'
module_path = Path(__file__).resolve().parent.parent / 'diff_generator' / 'diff_generator.py'
spec = importlib.util.spec_from_file_location(module_name, module_path)
diff_generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diff_generator)
create_patch = diff_generator.create_patch
fix_patch_file_path = diff_generator.fix_patch_file_path

app = Flask(__name__)


class PatchVerifier:
    """
    A class to verify patches by applying them to code, running verification,
    and generating verification results.
    """
    def __init__(self, model_name="opera-ai"):
        """
        Initialize the PatchVerifier with the specified model name.

        Args:
            model_name (str): The name of the model.
        """
        self.model_name = model_name
        self.temp_dir = "temp"
        # Ensure temp directory exists
        os.makedirs(self.temp_dir, exist_ok=True)
        
    def find_instance_id(self, file_name: str, issue: str, input_file_path: str = "./complete_300_lite_input.txt") -> List[str]:
        """
        Searches for the instance_id corresponding to the given python_file and issue.

        Args:
            file_name (str): The Python file name to search for.
            issue (str): The issue description to match.
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
        
        # Truncate the issue text to be 200 characters or less
        if len(issue) > 200:
            issue = issue[:200]

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
                    # Remove special characters from the issue strings
                    issue_clean = re.sub(r'[\n\r\t ]', '', issue)
                    issue_in_data_clean = re.sub(r'[\n\r\t ]', '', issue_in_data)
                    if python_file == file_name and issue_clean in issue_in_data_clean:
                        matches.append(instance_id)
                except json.JSONDecodeError as e:
                    print(f"Warning: Skipping invalid JSON on line {line_number}: {e}", file=sys.stderr)
                except Exception as e:
                    print(f"Error processing line {line_number}: {e}", file=sys.stderr)

        return matches

    def extract_base64_string(self, base64_str: str) -> str:
        """
        Decodes a base64 encoded string.

        Args:
            base64_str (str): The base64 encoded string.

        Returns:
            str: The decoded string.
        """
        base64_bytes = base64_str.encode('utf-8')
        input_bytes = base64.b64decode(base64_bytes)
        return input_bytes.decode('utf-8')

    def remove_line_number(self, code_text: str) -> str:
        """
        Removes line numbers from the code text if they exist.

        Args:
            code_text (str): The code text possibly containing line numbers.

        Returns:
            str: The code text without line numbers.
        """
        # Remove the first line number if it exists
        if code_text.startswith('1 '):
            code_text = code_text[2:]
        code_without_line_numbers = re.sub(r'\n\d+ ', '\n', code_text)
        return code_without_line_numbers

    def write_to_file(self, string_content: str, output_file: str):
        """
        Writes the string content to the specified output file.

        Args:
            string_content (str): The content to write.
            output_file (str): The path to the output file.
        """
        try:
            with open(output_file, 'w', encoding='utf-8') as outfile:
                outfile.write(string_content + '\n')
            print(f"Written file to '{output_file}' (overwritten existing content).")
        except Exception as e:
            print(f"Error writing to file '{output_file}': {e}", file=sys.stderr)

    def get_old_code(self, instance_id_to_find: str, source_json_file: str = "./complete_300_lite_input.txt") -> Tuple[str, str]:
        """
        Gets the old code that needs to be fixed from the input prompts.

        Args:
            instance_id_to_find (str): The instance ID to find.
            source_json_file (str): The source JSON file to search in.

        Returns:
            tuple: A tuple containing the old code and the python file path.

        Raises:
            FileNotFoundError: If the old code is not found.
        """
        old_code = None
        with open(source_json_file, 'r', encoding='utf-8') as infile:
            for line_number, line in enumerate(infile, start=1):
                line = line.strip()
                if not line:
                    continue  # Skip empty lines
                try:
                    data = json.loads(line)
                    instance_id = data.get('instance_id', '')
                    if instance_id == instance_id_to_find:
                        old_code = data.get('file_content', '')
                        python_file_path = data.get('python_file', '')
                        break
                except json.JSONDecodeError as e:
                    print(f"Warning: Skipping invalid JSON on line {line_number}: {e}", file=sys.stderr)
                except Exception as e:
                    print(f"Error processing line {line_number}: {e}", file=sys.stderr)
        
        if old_code is None:
            error_text = f"Error, old_code not found for {instance_id_to_find}"
            print(error_text)
            raise FileNotFoundError(error_text)
        
        return old_code, python_file_path

    def generate_output_jsonl(self, instance_id: str, patch: str) -> dict:
        """
        Constructs the desired JSON object that is used in the jsonl file.

        Args:
            instance_id (str): The instance ID to include.
            patch (str): The patch string to include in model_patch.

        Returns:
            dict: The JSON object.
        """
        output_data = {
            "instance_id": instance_id,
            "model_name_or_path": self.model_name,
            "text": "",
            "full_output": "",
            "model_patch": patch
        }
        return output_data

    def clean_log_directory(self, instance_id: str):
        """
        Deletes all files and folders inside the specified log directory.

        Args:
            instance_id (str): The instance ID whose log directory to clean.
        """
        log_dir = os.path.join('.', 'logs', 'run_evaluation', 'verify_one', self.model_name, instance_id)
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

    def run_verification(self, verification_file_name: str) -> str:
        """
        Runs the verification script and captures its console output.

        Args:
            verification_file_name (str): The verification file name.

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
            f"{verification_file_name}",
            "--max_workers",
            "4",
            "--run_id",
            "verify_one",
            "--clean",
            "TRUE",
            "--cache_level",
            "none",
            # "--force_rebuild",
            # "TRUE",
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

    def read_log_file(self, instance_id: str, file_name: str, file_extension: str) -> Tuple[str, bool]:
        """
        Constructs the path to the specified log file and attempts to read its contents.

        Args:
            instance_id (str): The identifier for the specific instance.
            file_name (str): The name of the file to read (without extension).
            file_extension (str): The file extension (e.g., '.log').

        Returns:
            tuple: (str, bool) The contents of the log file if successful, 
                     or an error message if the file cannot be read.
                     The boolean indicates if the file was loaded successfully.
        """
        # Construct the base path to the log file
        base_path = os.path.join(
            '.', 
            'logs', 
            'run_evaluation', 
            'verify_one', 
            self.model_name, 
            instance_id
        )
        # Combine the base path with the file name and extension
        log_file_path = os.path.join(base_path, file_name) + file_extension

        # Initialize the variable to hold the log contents
        log_contents = ""
        log_file_loaded = True

        # Attempt to read the log file
        try:
            with open(log_file_path, 'r', encoding='utf-8') as log_file:
                log_contents = log_file.read().strip()
        except FileNotFoundError:
            log_contents = f"Log file '{log_file_path}' not found."
            log_file_loaded = False
        except Exception as e:
            log_contents = f"Error reading file '{log_file_path}': {e}"
            log_file_loaded = False

        return log_contents, log_file_loaded

    def extract_relevant_error(self, instance_id: str, verification_stdout: str) -> str:
        """
        Extracts the relevant error message for why the verification run failed from all the logs and console messages.

        Args:
            instance_id (str): The instance ID.
            verification_stdout (str): The standard output from the verification run.

        Returns:
            str: The error log segment.
        """
        # Check the content of those files to try to isolate the error segment.
        test_output_txt, test_output_exist = self.read_log_file(instance_id, "test_output", ".txt")

        error_log = ""
        # If the test_output.txt doesn't exist, something has gone wrong in the verification run
        if not test_output_exist:
            print(f"==== ERROR: no test_output.text exist for {instance_id}, here is the verification_stdout:\n{verification_stdout}")
            error_log = verification_stdout
        else:
            content_parts = re.split(r'Checking patch ', test_output_txt)
            rest_of_string = f"Checking patch {content_parts[-1].strip()}"
            content_parts = re.split(r'\+ git checkout', rest_of_string)
            error_log = content_parts[0]
            
        # check if the error log is too long, if so condense the log
        lines = error_log.splitlines()
        if len(lines) > 80:
            print(f"Error log file is too long, condensing the error log.")
            error_log = LogCondenser().extract_errors(error_log)
            # write out the new error log to file for debugging later
            condense_error_log_path = os.path.join(self.temp_dir, f"{instance_id}_condense_error_log.txt")
            self.write_to_file(error_log, condense_error_log_path)

        return error_log

    def generate_verification_json(self, instance_id: str, python_file: str, error_msg_segment: str, patch_applied: bool = True) -> dict:
        """
        Constructs the verification JSON object, including the run_instance_log.

        Args:
            instance_id (str): The instance ID.
            python_file (str): The python_file name.
            error_msg_segment (str): The error message segment for debugging.
            patch_applied (bool): Indicates whether the patch was applied successfully.

        Returns:
            dict: The verification data.
        """
        
        test_report_json, _ = self.read_log_file(instance_id, "report", ".json")

        # Determine fix_successful
        fix_successful = "FALSE"
        if "\"resolved\": true" in test_report_json:
            fix_successful = "TRUE"
        patched_str = "TRUE" if patch_applied else "FALSE"

        # Construct the verification data
        verification_data = {
            "instance_id": instance_id,
            "python_file": python_file,
            "error_msg_segment": error_msg_segment,
            "patch_applied": patched_str,
            "fix_successful": fix_successful,
        }
        print(f"==== Result: {instance_id}, patch_applied: {patched_str}, fix_successful: {fix_successful}")
        return verification_data

    def check_if_patch_can_be_applied(self, diff_text: str, source_lines: List[str], output_file: str="new_code.py") -> Tuple[bool, str]:
        """
        Applies the patch to the source lines and writes the result to the output file.

        :param diff_text: The unified diff text.
        :param source_lines: List of strings representing the lines of the source code.
        :param output_file: The name of the output file after applying the patch.
        """
        # Write the source_lines to a temporary file
        with tempfile.NamedTemporaryFile('w+', delete=False) as temp_source_file:
            temp_source_file_name = temp_source_file.name
            temp_source_file.writelines(source_lines)
        
        try:
            patch_process = subprocess.run(
                ['patch', temp_source_file_name, '-o', output_file],
                input=diff_text,
                capture_output=True,
                text=True
            )
            if patch_process.returncode != 0:
                error_txt = f"The patch that was generated has Errors:\n {patch_process.stderr}"
                print(error_txt)
                return False, error_txt
            else:
                return True, ""
        except FileNotFoundError:
            print("Error: The 'patch' command is not found. Please install it or adjust the script.")
            sys.exit(1)
        finally:
            # Remove the temporary source file
            os.unlink(temp_source_file_name)


    def verify_patch(self, instance_id: str, diff_patch_64: str, get_unit_test: bool = False):
        """
        Verifies the provided patch by applying it to the old code, running verification,
        and generating the verification JSON.

        Args:
            instance_id (str): The instance ID.
            diff_patch_64 (str): The base64 encoded diff patch.
            get_unit_test (bool): Whether to generate the unit test.

        Returns:
            tuple: A tuple containing the response dictionary and the status code.
        """
        file_name = None  # Initialize file_name
        try:
            if not instance_id:
                error_msg = f"'instance_id' is required"
                return {"error": error_msg}, 400
            
            print(f"==== processing {instance_id}")
            # Always clean logs before processing the prompt
            self.clean_log_directory(instance_id)

            diff_patch_content = self.extract_base64_string(diff_patch_64)
            # Remove the line numbers from the diff_patch_content if line numbers exist
            diff_patch_content = self.remove_line_number(diff_patch_content)
            # Write the diff_patch sent by the caller to file system for debugging usage later 
            user_input_file_path = os.path.join(self.temp_dir, f"{instance_id}_input.diff")
            self.write_to_file(diff_patch_content, user_input_file_path)
        
            old_file_content, file_name = self.get_old_code(instance_id)
            # Generate the new file content by fuzzy patching the old file
            # Write out old file content to system, so it can be processed by fuzzy matching
            old_file_path = os.path.join(self.temp_dir, f"{instance_id}_old.py")
            with open(old_file_path, 'wb') as f:
                f.write(old_file_content.encode("utf-8"))
            # removing the fuzzy patch process since the new patch shouldn't break anymore.
            # print(f"Attempting to fuzzy patch")
            # new_file_content = apply_fuzzy_matching_patch(old_file_path, user_input_file_path)
            # patch = create_patch(file_name, old_file_content.encode('utf-8'), new_file_content.encode('utf-8'), instance_id)
            patch = fix_patch_file_path(diff_patch_content, file_name)
            patched_successful, patch_error_msg = self.check_if_patch_can_be_applied(patch, old_file_content, os.path.join(self.temp_dir, f"{instance_id}_new.py"))
            if not patched_successful:
                return {
                    "verification_json": self.generate_verification_json(instance_id, file_name or "", str(patch_error_msg), False)
                }, 200

            # Generate the output JSONL
            output_jsonl = self.generate_output_jsonl(instance_id, patch)
            verification_file_name = os.path.join(self.temp_dir, f"{instance_id}_verify_one_instance.jsonl")
            self.write_to_file(json.dumps(output_jsonl), verification_file_name)
            
            # Run verification and capture the output
            verification_stdout = self.run_verification(verification_file_name)
            
            # Get the relevant error message from the different log files
            test_error_segment = self.extract_relevant_error(instance_id, verification_stdout)

            # Generate the verification JSON structure
            verification_json = self.generate_verification_json(instance_id, file_name, test_error_segment, True)
       
            response = {
                "verification_json": verification_json
            }
            if get_unit_test:                    
                # Create the unit test of the processed instance
                try:
                    unit_test_content = process_log_file(instance_id)
                except Exception as e:
                    unit_test_content = f"{e}"
                response["unit_test"] = unit_test_content
            
            return response, 200
        except ValueError as ve:
            return {
                "verification_json": self.generate_verification_json(instance_id, file_name or "", str(ve), False)
            }, 200
        except Exception as e:
            return {"error": str(e)}, 400


# Flask route for verifying patches
@app.route('/verify_patch', methods=['POST'])
def verify_patch_endpoint():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON payload"}), 400
        
        instance_id = data.get('instance_id')
        diff_patch_64 = data.get('diff_patch_64')
        get_unit_test = data.get('get_unit_test', False)

        if isinstance(get_unit_test, str):
            get_unit_test = get_unit_test.upper() == "TRUE"

        if not instance_id or not diff_patch_64:
            return jsonify({"error": "Both 'instance_id' and 'diff_patch_64' fields are required"}), 400

        patch_verifier = PatchVerifier(model_name="opera-ai")
        result, status_code = patch_verifier.verify_patch(instance_id, diff_patch_64, get_unit_test)
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, threaded=True)
