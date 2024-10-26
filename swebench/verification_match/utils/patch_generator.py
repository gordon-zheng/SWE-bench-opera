import sys
import difflib
import subprocess
import tempfile
import os
from typing import List


def remove_line_numbers(code_with_line_number: List[str]) -> List[str]:
    # Do nothing for now, since it is not needed.
    return code_with_line_number

def process_snippet_into_source(snippet_lines: List[str], source_lines: List[str], patch_code_name: str) -> str:
    """
    Processes the snippet and source lines to generate a patch, apply it, and validate the result.
    This function can be called by other scripts.

    :param snippet_lines: List of strings representing the lines of the snippet code.
    :param source_lines: List of strings representing the lines of the source code.
    :param patch_code_name: The name of the output file after applying the patch.
    """
    # Generate the modified source code
    snippet_lines = remove_line_numbers(snippet_lines)
    source_lines = remove_line_numbers(source_lines)
    modified_source_lines, safe_matching = merge_snippet_into_source(source_lines, snippet_lines)

    if not safe_matching:
        error_text = "The first line and the last line of the code snippet are not context lines," 
        error_text += " we need to add more context line to the begaining and the end of the code snippet," 
        error_text += " in order to update the source code correctly"
        print(error_text)
        # technically we can generate a patch with the modified_source_line code at this point, but because
        # of the context line issue, we have only low confidence that the patch generated actually matched the intention
        # of the code snippet given 
        # - for example the first line(s) on the snippet could be alteration of existing line of the source code
        # raise RuntimeError(error_text)

    # Generate the unified diff
    diff = difflib.unified_diff(
        source_lines,
        modified_source_lines,
        fromfile=patch_code_name,
        tofile=patch_code_name,
        lineterm=''
    )

    diff_text = ''.join(s if s.endswith('\n') else s + '\n' for s in diff)

    # Write the diff to patch.diff
    with open('patch.diff', 'w') as f:
        f.write(diff_text)
    print("Unified diff patch written to 'patch.diff'.")

    if True: # those 2 below step are use to validate that the final code after the snippet patch has been applied is 
             # a syntatically correct python code (it will complie) 
        # Apply the patch to the source code to create new_code.py
        apply_patch(diff_text, source_lines, patch_code_name)
    if False:
        # Validate the new code
        validate_code(patch_code_name)
        
    return diff_text

def merge_snippet_into_source(source_lines: List[str], snippet_lines: List[str]) -> tuple(List[str], bool):
    """
    Merges the snippet into the source code based on the first and last matching lines.
    Returns the modified source code lines and a boolean indicating if the first and last matching
    lines are at the start and end of the snippet (safe matching).

    :param source_lines: List of strings representing the lines of the source code.
    :param snippet_lines: List of strings representing the lines of the snippet code.
    :return: Tuple containing the modified source code lines and a boolean for safe matching.
    """
    # Create a SequenceMatcher instance
    matcher = difflib.SequenceMatcher(None, source_lines, snippet_lines)

    # Get matching blocks
    matching_blocks = matcher.get_matching_blocks()

    # Filter out zero-length matches at the end
    matching_blocks = [block for block in matching_blocks if block.size > 0]

    if not matching_blocks:
        error_txt = "No matching lines found. Appending more context line to the begainning and the end of the code snippet."
        print(error_txt)
        raise RuntimeError(error_txt)

    # Identify first and last matching blocks
    first_match = matching_blocks[0]
    last_match = matching_blocks[-1]
    
    print(f"Num of matches: {len(matching_blocks)}")

    # Build the modified source code
    modified_source_lines = []

    # Step 1: Copy source code before first matching line
    modified_source_lines.extend(source_lines[:first_match.a])

    # Step 2: Copy snippet code before first matching line
    modified_source_lines.extend(snippet_lines[:first_match.b])

    # Step 3: Copy the first matching line
    modified_source_lines.append(source_lines[first_match.a])

    # Step 4: Copy snippet code between first and last matching lines
    snippet_middle_start = first_match.b + 1
    snippet_middle_end = last_match.b
    if snippet_middle_start < snippet_middle_end:
        modified_source_lines.extend(snippet_lines[snippet_middle_start:snippet_middle_end])

    # Step 5: Copy the last matching line (if different from the first)
    if last_match.a != first_match.a or last_match.size > 1:
        # copy over the entire matching block on the last match, instead of just the first line of the matching context
        modified_source_lines.extend(source_lines[last_match.a : last_match.a + last_match.size])

    # Step 6: Copy remaining snippet code after last matching line
    modified_source_lines.extend(snippet_lines[last_match.b + last_match.size:])

    # Step 7: Copy remaining source code after last matching line
    modified_source_lines.extend(source_lines[last_match.a + last_match.size:])

    # Determine if the first matching line is the first line of the snippet
    first_line_match = (first_match.b == 0)
    # Determine if the last matching line is the last line of the snippet
    last_line_match = (last_match.b + last_match.size == len(snippet_lines))
    # If both condition above is met, then we have high confidence that the changes generated is correct
    # according to the snippet code given.
    safe_matching = first_line_match and last_line_match

    return modified_source_lines, safe_matching

def apply_patch(diff_text: str, source_lines: List[str], output_file: str) -> None:
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
            error_txt = f"The patch that was generated has Errors: {patch_process.stderr}"
            print(error_txt)
            raise RuntimeError(error_txt)
        else:
            print(f"Patch applied successfully, '{output_file}' created.")
    except FileNotFoundError:
        print("Error: The 'patch' command is not found. Please install it or adjust the script.")
        sys.exit(1)
    finally:
        # Remove the temporary source file
        os.unlink(temp_source_file_name)

def validate_code(filename: str) -> None:
    """
    Validates the modified code by checking for syntax errors.

    :param filename: The name of the file to validate.
    """
    try:
        with open(filename, 'r') as f:
            code = f.read()
        compile(code, filename, 'exec')
        print(f"The '{filename}' file is syntactically correct.")
    except SyntaxError as e:
        error_msg = f"The code snippet we are inserting contain syntext error:\n {e}"
        print(error_msg)
        raise e

def main():
    if len(sys.argv) != 4:
        print("Usage: python script.py <snippet_file> <source_file> <source_code_file_name>")
        sys.exit(1)

    snippet_file = sys.argv[1]
    source_file = sys.argv[2]
    patch_code_name = sys.argv[3]

    # Read the code snippet and source code
    with open(snippet_file, 'r') as f:
        snippet_lines = f.readlines()

    with open(source_file, 'r') as f:
        source_lines = f.readlines()

    # Call the processing function
    print(process_snippet_into_source(snippet_lines, source_lines, patch_code_name))

if __name__ == "__main__":
    main()
