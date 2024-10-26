import sys
import difflib
import re
import logging
import copy

def normalize_indentation(lines):
    normalized_lines = []
    for line in lines:
        # Replace tabs with four spaces
        normalized_line = line.replace('\t', '    ')
        normalized_lines.append(normalized_line)
    return normalized_lines

def parse_diff(diff_lines):
    hunks = []
    hunk = []
    hunk_line_nums = []
    in_hunk = False
    diff_line_num = 0  # Line number in the diff file
    for line in diff_lines:
        diff_line_num += 1
        if line.startswith('@@'):
            if hunk:
                hunks.append((hunk, hunk_line_nums))
                hunk = []
                hunk_line_nums = []
            in_hunk = True
            hunk.append(line)
            hunk_line_nums.append(diff_line_num)
        elif in_hunk:
            hunk.append(line)
            hunk_line_nums.append(diff_line_num)
    if hunk:
        hunks.append((hunk, hunk_line_nums))
    if len(hunks) == 0:
        raise ValueError(f"==== Patching Error: Patch is empty or invalid")
    return hunks

def strip_whitespace(line):
    # Normalize whitespace for comparison
    return ' '.join(line.strip().split())

def get_patch_with_line_number(diff_lines):
    """
    Adds line numbers to each line in the provided list of strings without consistent spacing.

    Args:
        diff_lines (list of str): The original lines of the file.

    Returns:
        str: A single string with line numbers added to each line.
    """
    # Add line numbers to each line
    numbered_lines = [
        f"{i + 1} {line}"  # Remove any trailing newline characters
        for i, line in enumerate(diff_lines)
    ]
    # Join all lines into a single string with newline characters
    return "".join(numbered_lines)

def apply_fuzzy_matching_patch(original_file_name:str, diff_file_name:str):
    try:
        with open(original_file_name, 'r', encoding='utf-8') as f:
            original_lines = f.readlines()
        with open(diff_file_name, 'r', encoding='utf-8') as f:
            raw_diff_lines = f.readlines()
    except FileNotFoundError as e:
        print(f"File not found: {e.filename}")
        raise ValueError(f"==== Patching Error: Issue writing patch file to System")
    
    # Normalize indentation
    original_lines = normalize_indentation(original_lines)
    diff_lines = normalize_indentation(copy.deepcopy(raw_diff_lines))
    # Parse the diff file into hunks
    hunks = parse_diff(diff_lines)
    
    line_difference = 0
    patched_lines = original_lines.copy()
    for hunk, hunk_line_nums in hunks:
        # Parse hunk header
        header = hunk[0].strip()
        m = re.match(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', header)
        if not m:
            raise ValueError(f"==== Patching Error: Invalid hunk header: {header}")

        # Extract hunk lines and their corresponding diff file line numbers
        hunk_lines = hunk[1:]
        hunk_line_numbers = hunk_line_nums[1:]  # Exclude header line number

        # Prepare context and change lines
        hunk_context = []
        new_content = []
        hunk_line_indices = []  # Line numbers in the hunk (1-based)
        hunk_line_positions = []  # Positions in the diff file

        num_context_line = 0
        hunk_line_differnce = 0
        for idx, line in enumerate(hunk_lines):
            diff_file_line_num = hunk_line_numbers[idx]
            # Handle the special line indicating no newline at EOF
            if line.startswith('\\ No newline at end of file'):
                continue  # Skip this line
            if line.startswith(' '):
                # Context line
                hunk_context.append(line[1:])
                new_content.append(line[1:])
                hunk_line_indices.append(idx + 1)
                hunk_line_positions.append(diff_file_line_num)
                num_context_line += 1
            elif line.startswith('-'):
                # Removed line
                hunk_context.append(line[1:])
                hunk_line_indices.append(idx + 1)
                hunk_line_positions.append(diff_file_line_num)
                hunk_line_differnce += 1
                num_context_line += 1
            elif line.startswith('+'):
                # Added line
                new_content.append(line[1:])
                hunk_line_differnce -= 1
            elif line == '\n':
                # this is empty line, which should only occure at the end of the patch file
                continue
                # Added lines do not contribute to context matching
            else:
                # Unexpected line in hunk
                raise Exception(f"Unexpected line in hunk at diff line {diff_file_line_num}: {line}")
            
            # Reject any patch that doesn't provide atleast one context line (matching line or "-" line) for patching purpose
            if num_context_line < 1:
                error_txt = "No context lines provided in patch, CAN NOT apply patch\n"
                error_txt += "\nCurrent Diff Patch Content\n"
                error_txt += get_patch_with_line_number(raw_diff_lines)
                print(error_txt)
                raise ValueError(f"==== Patching ERROR:\n{error_txt}")
                

        hunk_context_stripped = [strip_whitespace(line) for line in hunk_context]

        # Find where to apply the hunk in the original file
        found = False
        best_match_ratio = 0
        best_match_start = None

        for i in range(len(patched_lines) - len(hunk_context) + 1):
            # Extract a window from the original lines
            window = patched_lines[i:i+len(hunk_context)]
            window_stripped = [strip_whitespace(line) for line in window]

            # Compute matching ratio
            matcher = difflib.SequenceMatcher(None, hunk_context_stripped, window_stripped)
            ratio = matcher.ratio()
            if ratio > best_match_ratio:
                best_match_ratio = ratio
                best_match_start = i

            # If all lines match, apply the hunk
            if hunk_context_stripped == window_stripped:
                # Apply changes
                patched_lines[i:i+len(hunk_context)] = new_content
                found = True
                line_difference += hunk_line_differnce
                break

        if not found:
            # Provide detailed debugging information
            error_msg = f"Failed to apply patch hunk: {header}\n"
            org_code_failure_section = []
            diff_patch_failure_section = []
            
            if best_match_start is not None:
                error_msg += f"Best fuzzy match with original file at match ratio {best_match_ratio:.2f}\n"
                # Show which lines matched and which didn't
                window = patched_lines[best_match_start:best_match_start+len(hunk_context)]
                window_stripped = [strip_whitespace(line) for line in window]
                temp_error_msg = ""
                last_hunk_line_stripped = None
                for idx, (hunk_line, orig_line) in enumerate(zip(hunk_context_stripped, window_stripped)):
                    hunk_line_num = hunk_line_indices[idx]
                    diff_file_line_num = hunk_line_positions[idx]
                    hunk_line_stripped = strip_whitespace(hunk_line)
                    orig_line_stripped = strip_whitespace(orig_line)
                    if hunk_line_stripped != orig_line_stripped:
                        # the scenerio generally show up when the patching process break during "-" line, which lead to the mismatch
                        off_by_one = last_hunk_line_stripped == orig_line_stripped
                        orig_file_line_index = best_match_start + line_difference + idx + (1 if off_by_one else 0)
                        raw_issue_diff_line = raw_diff_lines[diff_file_line_num - 1].rstrip()
                        temp_error_msg = "A hunk line does not match the original code\n" #f"Hunk line {hunk_line_num} does not match original file:\n"
                        temp_error_msg += f"  Original code line {orig_file_line_index + 1}: '{original_lines[orig_file_line_index].rstrip()}'\n"
                        temp_error_msg += f"  But the Diff says: '{raw_issue_diff_line}' at line {diff_file_line_num}\n"
                        if not off_by_one:
                            # if the issue is not off by one problem, which mean it is not a "-" change issue, but contenxt line
                            # issue, for those issue, we should show the first line of the context mismatch, so we exit for loop.
                            break 
                    last_hunk_line_stripped = hunk_line_stripped
                error_msg += temp_error_msg
                
                org_code_failure_start_line = best_match_start + line_difference + (1 if off_by_one else 0)
                diff_failure_start_line = hunk_line_positions[0]
                for i in range(0, len(hunk_lines)):
                    if len(raw_diff_lines) >= (diff_failure_start_line + i - 1):
                        diff_patch_failure_section.append(raw_diff_lines[diff_failure_start_line + i - 1].rstrip())
                    else:
                        diff_patch_failure_section.append("EOF")
                    if len(original_lines) > (org_code_failure_start_line + i - 1):
                        org_code_failure_section.append(original_lines[org_code_failure_start_line + i - 1].rstrip())
                    else:
                        org_code_failure_section.append("EOF")
            else:
                error_msg += "No similar lines found in original file, in the patch file\n"
            
            if org_code_failure_section:
                org_code_failure_section = '\n'.join(org_code_failure_section)
                diff_patch_failure_section = '\n'.join(diff_patch_failure_section)
                print("\n<source_code_issue_section>\n" + f"{org_code_failure_section}" + "\n<\source_code_issue_section>\n\n")
                print("<diff_issue_section>\n" + f"{diff_patch_failure_section}" + "\n<\diff_issue_section>\n")
            else:
                print("Patch is so messed up, fuzzy match ratio is at 0.0")
            
            error_msg += "\nCurrent Diff Patch Content\n"
            error_msg += get_patch_with_line_number(raw_diff_lines)
            raise ValueError(f"==== Patching ERROR:\n{error_msg}")
    
    # turn the list of the files lines into a string represeting the whole content
    patched_content = "".join(patched_lines)
    print(f"Fuzzy match patching successful")
    return patched_content

def main():
    if len(sys.argv) != 4:
        print("Usage: python apply_patch.py original_file diff_file output_file")
        sys.exit(1)

    original_file = sys.argv[1]
    diff_file = sys.argv[2]
    output_file = sys.argv[3]

    # Apply the patch
    try:
        patched_lines = apply_fuzzy_matching_patch(original_file, diff_file)
    except Exception as e:
        print(f"{e}")
        sys.exit(1)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(patched_lines)

if __name__ == '__main__':
    # Set logging level to ERROR to minimize output
    logging.basicConfig(level=logging.ERROR, format='%(levelname)s: %(message)s')
    main()
