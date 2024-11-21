import difflib
from typing import List, Tuple

def normalize_line(line: str) -> str:
    return line.strip()

def find_group_matches(conxtext_group: List[str], source_code: List[str]) -> List[int]:
    """
        Finds all starting indices in source where the conxtext_group of lines matches in the source_code lines.
        
        Return 
            list of only the start index of the matching group, the end index of the group and length of the group is not needed.
    """
    context_group_length = len(conxtext_group)
    matching_indexes = []
    for i in range(0, len(source_code) - context_group_length + 1):
        if source_code[i : i + context_group_length] == conxtext_group:
             matching_indexes.append(i)
    return matching_indexes

def ndiff_unique_merge_snippet_into_source(
        source_code: List[str], snippet: List[str], debug_print=False
) -> Tuple[difflib.Match, difflib.Match, List[str]]:
    """
    Merges a code snippet into the source code by uniquely identifying the insertion point
    using context lines from the snippet.

    Args:
        source_code (List[str]): The source code where the snippet should be merged.
        snippet (List[str]): The code snippet to be merged.

    Returns:
        Tuple[difflib.Match, difflib.Match, List[str]]: A tuple containing the start and end matches as difflib.Match objects,
        and the new source code with the snippet merged.

    Raises:
        ValueError: If the snippet cannot be uniquely merged due to missing or ambiguous context.
    """

    # Step 1: Normalize all lines in the snippet and source_code
    normalized_snippet = [normalize_line(line) for line in snippet]
    normalized_source_code = [normalize_line(line) for line in source_code]

    # Step 1a: Check if the entire snippet already exists in the source code
    snippet_str = '\n'.join(normalized_snippet)
    source_code_str = '\n'.join(normalized_source_code)
    if snippet_str in source_code_str:
        raise ValueError("The entire snippet already exists in the source code.")

    # Step 2: Initialize first group (starting context)
    first_group_start = 0
    while first_group_start < len(normalized_snippet):
        first_line = normalized_snippet[first_group_start]
        if first_line in normalized_source_code:
            break
        first_group_start += 1
    else:
        raise ValueError("Could not find any matching context lines in the snippet and the source code.")

    first_group_end = first_group_start
    first_group = normalized_snippet[first_group_start:first_group_end + 1]
    first_group_matches_index = find_group_matches(first_group, normalized_source_code)

    # Step 2a: Initialize last group (ending context)
    last_group_end = len(normalized_snippet) - 1
    while last_group_end >= 0:
        last_line = normalized_snippet[last_group_end]
        if last_line in normalized_source_code:
            break
        last_group_end -= 1
    else:
        raise ValueError("No lines in the snippet exist in the source code for ending context.")

    last_group_start = last_group_end
    last_group = normalized_snippet[last_group_start:last_group_end + 1]
    last_group_matches_index = find_group_matches(last_group, normalized_source_code)

    # Step 2b: Ensure valid context group positions
    if first_group_start > last_group_start:
        raise ValueError("Starting context occurs after ending context in the snippet.")

    # Ensure matches are in correct order
    first_group_matches_index = [
        pos for pos in first_group_matches_index if any(lp >= pos for lp in last_group_matches_index)
    ]
    last_group_matches_index = [
        pos for pos in last_group_matches_index if any(fp <= pos for fp in first_group_matches_index)
    ]

    if not first_group_matches_index or not last_group_matches_index:
        raise ValueError("Cannot find valid context group matches in the source code.")

    # Step 3: Alternating expansion of context groups
    while True:
        is_first_group_unique = len(first_group_matches_index) == 1
        is_last_group_unique = len(last_group_matches_index) == 1

        if debug_print:
            print(
                f"Looping: first_group_matches_index: {first_group_matches_index}, "
                f"fg_size: {first_group_end - first_group_start + 1}, "
                f"last_group_matches_index: {last_group_matches_index}, "
                f"lg_size: {last_group_end - last_group_start + 1}"
            )

        # Check if both groups are unique and in correct order
        if is_first_group_unique and is_last_group_unique:
            if first_group_matches_index[0] <= last_group_matches_index[0]:
                # Unique context groups found; exit the loop
                break
            else:
                raise ValueError("First group match occurs after last group match in the source code.")

        # Check for overlap
        if first_group_end >= last_group_start:
            raise ValueError("Context groups have overlapped without achieving uniqueness.")

        progress = False  # Flag to detect progress

        # Expand first group by adding the next line
        if not is_first_group_unique and first_group_end + 1 < last_group_start:
            potential_first_group_end = first_group_end + 1
            potential_first_group = normalized_snippet[first_group_start: potential_first_group_end + 1]
            fg_expanded_matches = find_group_matches(potential_first_group, normalized_source_code)
            fg_expanded_matches = [fp for fp in fg_expanded_matches if any(lp >= fp for lp in last_group_matches_index)]
            if fg_expanded_matches:
                first_group_end = potential_first_group_end
                first_group = potential_first_group
                first_group_matches_index = fg_expanded_matches
                progress = True

        # Update uniqueness of first group after expansion and filtering
        is_first_group_unique = len(first_group_matches_index) == 1

        # If first group is unique, filter last group matches
        if is_first_group_unique and not is_last_group_unique:
            first_match_pos = first_group_matches_index[0]
            lg_filtered_matches = [lp for lp in last_group_matches_index if lp >= first_match_pos]
            if lg_filtered_matches != last_group_matches_index:
                last_group_matches_index = lg_filtered_matches
                progress = True
            is_last_group_unique = len(last_group_matches_index) == 1

        # Expand last group by adding the previous line
        if not is_last_group_unique and last_group_start - 1 > first_group_end:
            potential_last_group_start = last_group_start - 1
            potential_last_group = normalized_snippet[potential_last_group_start:last_group_end + 1]
            lg_expanded_matches = find_group_matches(potential_last_group, normalized_source_code)
            lg_expanded_matches = [lp for lp in lg_expanded_matches if any(fp <= lp for fp in first_group_matches_index)]
            if lg_expanded_matches:
                last_group_start = potential_last_group_start
                last_group = potential_last_group
                last_group_matches_index = lg_expanded_matches
                progress = True

        # Update uniqueness of last group after expansion and filtering
        is_last_group_unique = len(last_group_matches_index) == 1

        # If last group is unique, filter first group matches
        if is_last_group_unique and not is_first_group_unique:
            last_match_pos = last_group_matches_index[0]
            fg_filtered_matches = [fp for fp in first_group_matches_index if fp <= last_match_pos]
            if fg_filtered_matches != first_group_matches_index:
                first_group_matches_index = fg_filtered_matches
                progress = True
            is_first_group_unique = len(first_group_matches_index) == 1

        # If no progress is made, raise an error
        if not progress:
            raise ValueError("Cannot find unique context group matches with the existing snippet code.")
        
    # end of the While True loop

    # Step 3a: Do we need to do context group greedy expansion for the first and last group to include all the lines in both context group?
    # TODO: Maybe

    # Step 4: Proceed to merge after unique matches are found
    first_group_match_pos = first_group_matches_index[0]
    last_group_match_pos = last_group_matches_index[0]

    # Calculate lengths of the context groups
    first_group_length = first_group_end - first_group_start + 1
    last_group_length = last_group_end - last_group_start + 1

    start_match = difflib.Match(
        a=first_group_start,  # Start index in snippet for the first group
        b=first_group_match_pos,  # Start index in source code for the first group
        size=first_group_length,  # Length of the first group
    )

    end_match = difflib.Match(
        a=last_group_start,  # Start index in snippet for the last group
        b=last_group_match_pos,  # Start index in source code for the last group
        size=last_group_length,  # Length of the last group
    )

    # Step 5: Perform the merge
    # Identify snippet parts
    snippet_before_first_context = snippet[:first_group_start]
    middle_part = snippet[first_group_end + 1: last_group_start]
    snippet_after_last_context = snippet[last_group_end + 1:]

    # Identify source code parts
    source_before_first_context = source_code[:first_group_match_pos]
    first_context = source_code[first_group_match_pos:first_group_match_pos + first_group_length]
    last_context = source_code[last_group_match_pos:last_group_match_pos + last_group_length]
    source_after_last_context = source_code[last_group_match_pos + last_group_length:]

    # Construct the new source code
    new_source_code = (
        source_before_first_context +
        snippet_before_first_context +
        first_context +
        middle_part +
        last_context +
        snippet_after_last_context +
        source_after_last_context
    )

    # Return the Match objects and the new source code
    return start_match, end_match, new_source_code
