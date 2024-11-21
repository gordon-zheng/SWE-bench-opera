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
        source_code: List[str], snippet: List[str], debug_print = False
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

    # Step 2: Verify that the first line of snippet exists in source_code
    first_line = normalized_snippet[0]
    first_line_positions = [
        i for i, line in enumerate(normalized_source_code) if line == first_line
    ]
    # Step 2a: Verify that the last line of snippet exists in source_code
    last_line = normalized_snippet[-1]
    last_line_positions = [
        i for i, line in enumerate(normalized_source_code) if line == last_line
    ]
    # Step 2b: generate appropate error if context lines are not at the top and bottom
    if not first_line_positions and not last_line_positions:
        raise ValueError("The first and last lines of the snippet does not exist in the source code.")        
    elif not first_line_positions:
        raise ValueError("The first line of the snippet does not exist in the source code.")
    elif not last_line_positions:
        raise ValueError("The last line of the snippet does not exist in the source code.")

    # Step 3: Initialize context groups and matches
    first_group_end = 0  # Index in the snippet, initally the first group is just the first line in the snippet
    last_group_start = len(snippet) - 1  # Index in the snippet, initally the last group is just the last line in the snippet
    first_group = normalized_snippet[:1] # first group is just the first line in the begaining, but in a list of 1 line
    last_group = normalized_snippet[-1:] # last group is just the last line in the begaining, but in a list of 1 line

    # Initial matches for context groups
    first_group_matches_index = find_group_matches(first_group, normalized_source_code) # find all the matches for the single start line
    last_group_matches_index = find_group_matches(last_group, normalized_source_code) # find all the matches for the single last line

    # Ensure matches are in correct order
    first_group_matches_index = [
        # filter out first_group_matches that exist after the last_group_match in the source code (ie first_index CANNOT be > any of the last_index)
        pos for pos in first_group_matches_index if any(lp >= pos for lp in last_group_matches_index)
    ]
    last_group_matches_index = [
        # filter out first_group_matches that exist after the last_group_match in the source code (ie last_index CANNOT be < any of the first_index)
        pos for pos in last_group_matches_index if any(fp <= pos for fp in first_group_matches_index)
    ]

    # Step 4: Alternating expansion of context groups first group going down, and last group going up, 1 line at a time for both group
    while True:
        is_first_group_unique = len(first_group_matches_index) == 1 # is there only 1 starting index match for the first_match_group in source code?
        is_last_group_unique = len(last_group_matches_index) == 1 # is there only 1 end index match for the last_match_group in source code?

        debug_message_str = (
            f"Looping: first_group_matches_index: {first_group_matches_index}, "
            f"fg_size: {first_group_end + 1}, " # note since the first group always start at index 0 on snippet, first_group_end + 1 also denote size
            f"last_group_matches_index: {last_group_matches_index}, "
            f"lg_size: {len(snippet) - last_group_start}" # note since the last group always ends at end of snippet, we just subtract the 2 index for the last group
        )
        if debug_print:
            print(debug_message_str)

        # Check if both groups are unique and in correct order
        if is_first_group_unique and is_last_group_unique:
            if first_group_matches_index[0] <= last_group_matches_index[0]:
                # we found both unique start and unique end context group, so we are DONE with the while loop
                break
            else:
                # while we found unique start and end context group, somehow they are flipped in order of apparence in the source code
                raise ValueError("First group match occurs after last group match.")

        # Check for overlap
        if first_group_end >= last_group_start:
            raise ValueError("Context groups have overlapped without achieving uniqueness.")

        progress = False  # Flag to detect progress, if we CANNOT make any progress in a single loop, then we consider no uniqueness match possible

        # Expand first group by adding the next line
        if not is_first_group_unique and first_group_end + 1 < last_group_start:
            # more then 1 possible first match, and more room to expend the first context group
            potential_first_group_end = first_group_end + 1 
            potential_first_group = normalized_snippet[: potential_first_group_end + 1]
            # expand the start_group in the snippet 1 more line down, to see if can still find matches
            fg_expanded_matches = find_group_matches(potential_first_group, normalized_source_code)
            # filter out any matches in the first group that is after all the possible last group
            fg_expanded_matches = [ fp for fp in fg_expanded_matches if any(lp >= fp for lp in last_group_matches_index) ]
            # if after expanded the first group we still find matches, we keep the expanded group in our next match run.
            if fg_expanded_matches:
                first_group_end = potential_first_group_end
                first_group = potential_first_group
                first_group_matches_index = fg_expanded_matches
                progress = True

        # Update uniqueness of first group after expansion and filtering
        is_first_group_unique = len(first_group_matches_index) == 1

        # If first_group is NOW unique, filter last_group matches, to check if the last_group is now unique after first_group changes
        if is_first_group_unique and not is_last_group_unique:
            first_match_pos = first_group_matches_index[0] # since the first_group is now unique, there is only 1 index.
            lg_filtered_matches = [ lp for lp in last_group_matches_index if lp >= first_match_pos ]
            # check if any of the possible last_matches are elimited, if so we consider as progress made.
            if lg_filtered_matches != last_group_matches_index:
                last_group_matches_index = lg_filtered_matches
                progress = True
            is_last_group_unique = len(last_group_matches_index) == 1

        # Expand last group by adding the previous line
        if not is_last_group_unique and last_group_start - 1 > first_group_end:
            # more then 1 possible last match, and more room to expend upward on the last group
            potential_last_group_start = last_group_start - 1
            potential_last_group = normalized_snippet[potential_last_group_start:]
            # expand the last_group in the snippet 1 more line up, to see if can still find matches
            lg_expanded_matches = find_group_matches(potential_last_group, normalized_source_code)
            # filter out any matches in the last group that is before all the possible first group
            lg_expanded_matches = [ lp for lp in lg_expanded_matches if any(fp <= lp for fp in first_group_matches_index) ]
            # if after expanded the last group we still find matches, we keep the expanded group in our next match run.
            if lg_expanded_matches:
                last_group_start = potential_last_group_start
                last_group = potential_last_group
                last_group_matches_index = lg_expanded_matches
                progress = True

        # Update uniqueness of last group after expansion and filtering
        is_last_group_unique = len(last_group_matches_index) == 1

        # If last_group is NOW unique, filter first_group matches, to check if the first_group is now unique after last_group changes
        if is_last_group_unique and not is_first_group_unique:
            last_match_pos = last_group_matches_index[0] # since the last_group is now unique, there is only 1 index.
            fg_filtered_matches = [ fp for fp in first_group_matches_index if fp <= last_match_pos ]
             # check if any of the possible first_matches are elimited, if so we consider as progress made.
            if fg_filtered_matches != first_group_matches_index:
                first_group_matches_index = fg_filtered_matches
                progress = True
            is_first_group_unique = len(first_group_matches_index) == 1

        # If no progress is made, raise an error
        if not progress:
            raise ValueError("Cannot find unique context group matches with the existing snippet code.")
        
        # end of the While True loop

    # Step 5: Proceed to merge after unique matches are found
    first_group_match_pos = first_group_matches_index[0]
    last_group_match_pos = last_group_matches_index[0]

    # Calculate lengths of the context groups
    first_group_length = first_group_end + 1
    last_group_length = len(snippet) - last_group_start

    start_match = difflib.Match(
        a = 0,  # Start index in snippet for the first group, which is always 0 on the snippet, or else error would have been thrown
        b = first_group_match_pos,  # Start index in source code for the first group
        size = first_group_length,  # Length of the first group
    )

    end_match = difflib.Match(
        a = last_group_start,  # Start index in snippet for the last group
        b = last_group_match_pos,  # Start index in source code for the last group
        size = last_group_length,  # Length of the last group
    )

    # Step 6: Perform the merge
    middle_part = snippet[first_group_end + 1 : last_group_start]
    insertion_start = first_group_match_pos + first_group_length
    insertion_end = last_group_match_pos
    new_source_code = (
        source_code[:insertion_start] + middle_part + source_code[insertion_end:]
    )

    # Return the Match objects and the new source code
    return start_match, end_match, new_source_code
