# utils/log_condensor.py

import os
import openai
import textwrap
import sys
from typing import List

class LogCondenser:
    def __init__(self, api_key: str = None, model: str = "gpt-4o-mini", max_tokens: int = 98304):
        """
        Initialize the LogParser with the necessary OpenAI API key and model.

        Args:
            api_key (str, optional): OpenAI API key. If not provided, it will look for the OPENAI_API_KEY environment variable.
            model (str, optional): OpenAI model to use. Defaults to "gpt-4".
            max_tokens (int, optional): Maximum tokens for the API response. Defaults to 98460.
        """
        if api_key:
            openai.api_key = api_key
        else:
            openai.api_key = os.getenv("OPENAI_API_KEY")
        
        if not openai.api_key:
            raise ValueError("OpenAI API key must be provided either as a parameter or via the OPENAI_API_KEY environment variable.")
        
        self.model = model
        self.max_tokens = max_tokens

    def chunk_text(self, text: str, max_tokens: int = 98304) -> List[str]:
        """
        Split text into chunks of approximately max_tokens tokens.

        Args:
            text (str): The input text to split.
            max_tokens (int, optional): Approximate maximum number of tokens per chunk. Defaults to 98460.

        Returns:
            List[str]: A list of text chunks.
        """
        # Approximate conversion from tokens to characters (assuming 4 chars per token)
        max_chars = max_tokens * 4
        lines = text.split('\n')
        chunks = []
        current_chunk = ''
        for line in lines:
            if len(current_chunk) + len(line) + 1 > max_chars:
                chunks.append(current_chunk)
                current_chunk = line + '\n'
            else:
                current_chunk += line + '\n'
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    def prepare_prompt(self, log_chunk: str) -> str:
        """
        Prepare the prompt to send to the OpenAI API.

        Args:
            log_chunk (str): A chunk of the log text.

        Returns:
            str: The formatted prompt.
        """
        prompt_template = textwrap.dedent("""
            **Task:** Extract error information from logs.

            **Instructions (follow *exactly*):**

            1. **Extract only the TWO most important errors** from the logs.
                - Errors to consider:
                    - 'traceback'
                    - 'AssertionError' or 'assertion error'
                    - 'ValidationError' or 'validation error'
                    - 'TypeError' or 'type error'
                    - 'ValueError' or 'value error'
                    - 'FAIL' or 'FAILURES'
            2. **For each error, include:**
                - The error message.
                - **Up to 25 lines** of context before the error message.
            3. **Do NOT include more than TWO errors**, even if more are present.
            4. **Limit the total response to approximately 30 lines.**
            5. **Provide ONLY the extracted raw log sections.** Do not add explanations or summaries.

            **Logs:**
            {}
        """).format(log_chunk)
        return prompt_template

    def extract_errors(self, log_content: str) -> str:
        """
        Extract relevant error information from the log content.

        Args:
            log_content (str): The complete log as a string.

        Returns:
            str: The extracted error information.
        """
        chunks = self.chunk_text(log_content)
        results = []

        for i, chunk in enumerate(chunks):
            prompt = self.prepare_prompt(chunk)
            try:
                response = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant who strictly follows the user's instructions."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1500,
                    temperature=0,
                )
                extracted_info = response.choices[0].message.content
                if extracted_info:
                    results.append(extracted_info)
            except Exception as e:
                print(f"Error processing chunk {i+1}: {e}")
                continue

        # Combine and ensure only the top two errors are retained
        combined_result = ''.join(results)
        # Optionally, further processing can be done here to ensure only two errors are present
        return combined_result

def main():
    if len(sys.argv) != 2:
        print("Usage: python log_parser.py <logfile>")
        sys.exit(1)

    logfile = sys.argv[1]

    # Check if the file exists
    if not os.path.isfile(logfile):
        print(f"Error: The file '{logfile}' does not exist.")
        sys.exit(1)

    # Read the log file
    try:
        with open(logfile, 'r') as f:
            log_content = f.read()
    except Exception as e:
        print(f"Error reading file '{logfile}': {e}")
        sys.exit(1)

    # Initialize LogParser (ensure to set your API key securely)
    try:
        parser = LogCondenser()
    except ValueError as ve:
        print(f"Initialization Error: {ve}")
        sys.exit(1)

    # Extract errors
    extracted_errors = parser.extract_errors(log_content)

    # Print the extracted errors
    print("\nExtracted Information:")
    print(extracted_errors)

if __name__ == "__main__":
    main()